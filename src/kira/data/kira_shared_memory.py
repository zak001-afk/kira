"""
KIRA Shared Memory Module — shared (NON-personal) knowledge via Supabase.

This module is the ONLY path through which KIRA talks to Supabase.

Privacy model
-------------
LOCAL ONLY — never leaves the machine (``kira_memory.py`` / ``kira_memory.db``):
  - conversations
  - names and identity facts
  - personal preferences
  - tasks, reminders and todos
  - private notes

SHARED — stored in the Supabase ``shared_knowledge`` table:
  - public web research (search summaries)  -> kind ``web_research``
  - learned public web pages                -> kind ``web_page``
  - shared project knowledge (build steps,  -> kind ``project_knowledge``
    architecture notes, conventions, ...)

Nothing else: the kind whitelist below is enforced here *and* by a CHECK
constraint in SUPABASE_SCHEMA.sql.

``save_shared_knowledge()`` refuses anything that looks personal
(see :func:`_personal_reason`), and any term registered through
:func:`set_private_terms` — KIRA registers the user's name and identity
facts from *local* memory so they can never be published by accident.

Security
--------
KIRA only ever uses the PUBLIC anon/publishable key
(``SUPABASE_ANON_KEY`` in ``.env``).

The Supabase ``service_role`` key bypasses Row Level Security and is
NEVER used, read, forwarded, or logged by this module:

  - any ``SUPABASE_*SERVICE*`` / ``*SECRET*`` / ``*ADMIN*`` environment
    variable is ignored and reported once as a warning;
  - if ``SUPABASE_ANON_KEY`` itself contains a service_role / secret key
    (detected via the JWT ``role`` claim or the ``sb_secret_`` prefix),
    the client refuses to be created.

Setup
-----
1. Run ``SUPABASE_SCHEMA.sql`` in the Supabase SQL editor.
2. Copy ``.env.example`` to ``.env`` and fill in ``SUPABASE_URL`` and
   ``SUPABASE_ANON_KEY`` (Dashboard -> Project Settings -> API keys).

Degrades gracefully: without configuration or without the ``supabase``
package every call is a safe no-op and KIRA keeps working fully offline
with its local memory.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
from kira import paths

logger = logging.getLogger("kira.shared_memory")

MODULE_DIR = paths.ROOT
ENV_PATH = os.path.join(MODULE_DIR, ".env")

DEFAULT_TABLE_NAME = "shared_knowledge"
DEFAULT_SEARCH_RPC = "search_shared_knowledge"

# Knowledge kinds accepted by both this module and SUPABASE_SCHEMA.sql.
KIND_WEB_RESEARCH = "web_research"
KIND_WEB_PAGE = "web_page"
KIND_PROJECT = "project_knowledge"
ALLOWED_KINDS = frozenset(
    {
        KIND_WEB_RESEARCH,
        KIND_WEB_PAGE,
        KIND_PROJECT,
    }
)

# Field limits (kept in sync with the CHECK constraints in the schema).
MAX_TOPIC_LENGTH = 160
MAX_TITLE_LENGTH = 300
MAX_CONTENT_LENGTH = 4000
MAX_SOURCE_URL_LENGTH = 1000
MAX_TAG_LENGTH = 40
MAX_TAGS = 10
MAX_SEARCH_WORDS = 6

SERVICE_ROLE_WARNING = (
    "A Supabase service_role/secret key was detected in the environment. "
    "KIRA NEVER uses the service_role key (it bypasses Row Level Security) — "
    "it is ignored. Remove it from your environment/.env and use "
    "SUPABASE_ANON_KEY (the public anon/publishable key) only."
)

# ---------------------------------------------------------------------------
# Environment loading (python-dotenv is optional)
# ---------------------------------------------------------------------------
DOTENV_AVAILABLE = False

try:  # pragma: no cover - exercised through the module configuration
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=False)
    DOTENV_AVAILABLE = True
except ImportError:
    load_dotenv = None
except Exception as exc:  # pragma: no cover - defensive
    load_dotenv = None
    logger.debug("Could not load %s: %s", ENV_PATH, exc)

try:  # pragma: no cover - exercised through the module configuration
    from supabase import create_client as _create_client

    SUPABASE_AVAILABLE = True
except ImportError:
    _create_client = None
    SUPABASE_AVAILABLE = False


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def _truthy(value: str, default: bool = True) -> bool:
    value = str(value or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on", "enabled", "enable"}


TABLE_NAME = (
    _env("KIRA_SHARED_KNOWLEDGE_TABLE", DEFAULT_TABLE_NAME) or DEFAULT_TABLE_NAME
)
SEARCH_RPC = (
    _env("KIRA_SHARED_KNOWLEDGE_RPC", DEFAULT_SEARCH_RPC) or DEFAULT_SEARCH_RPC
)
SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_ANON_KEY = _env("SUPABASE_ANON_KEY")
SHARING_ENABLED = _truthy(_env("KIRA_SHARED_KNOWLEDGE"), default=True)


def _warn_about_service_role_env_vars() -> list:
    """
    Report (once) any service_role/secret/admin Supabase env vars.

    The values are never read into memory, never used, never logged.
    """
    suspicious = [
        name
        for name in os.environ
        if re.match(r"^SUPABASE_.*(SERVICE|SECRET|ADMIN)", name, re.IGNORECASE)
    ]

    if suspicious:
        logger.warning(
            "%s Detected: %s",
            SERVICE_ROLE_WARNING,
            ", ".join(sorted(suspicious)),
        )

    return sorted(suspicious)


SERVICE_ROLE_ENV_VARS = _warn_about_service_role_env_vars()

# ---------------------------------------------------------------------------
# Key safety checks — the service_role key must never be used
# ---------------------------------------------------------------------------
_SECRET_KEY_PREFIXES = ("sb_secret_", "service_role")


def _jwt_role(token: str) -> str:
    """Best-effort read of the ``role`` claim of a Supabase JWT key."""
    try:
        parts = str(token or "").split(".")
        if len(parts) != 3:
            return ""
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return str(data.get("role", "") or "").strip().lower()
    except Exception:
        return ""


def key_looks_like_service_role(key: str) -> bool:
    """True when a key is (or looks like) a service_role / secret key."""
    key = str(key or "").strip()
    if not key:
        return False
    lowered = key.lower()
    if lowered.startswith(_SECRET_KEY_PREFIXES):
        return True
    return _jwt_role(key) == "service_role"


# ---------------------------------------------------------------------------
# Local-only private terms (e.g. the user's name) used as a publishing guard
# ---------------------------------------------------------------------------
_private_terms = set()
_private_terms_lock = threading.Lock()


def set_private_terms(terms) -> int:
    """
    Register local-only terms (user name, identity facts, ...).

    Any shared-knowledge payload containing a registered term is refused so
    personal data stays in ``kira_memory.db``.

    Returns the number of registered terms.
    """
    cleaned = set()

    for term in terms or []:
        text = re.sub(r"\s+", " ", str(term or "")).strip().casefold()
        if len(text) >= 3:
            cleaned.add(text)

    with _private_terms_lock:
        _private_terms.clear()
        _private_terms.update(cleaned)

    return len(cleaned)


def get_private_terms() -> list:
    """Return the registered local-only terms (never the values themselves)."""
    with _private_terms_lock:
        return sorted(_private_terms)


def _term_present(text: str) -> bool:
    haystack = str(text or "").casefold()
    if not haystack:
        return False

    with _private_terms_lock:
        terms = tuple(_private_terms)

    for term in terms:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", haystack):
            return True

    return False


# ---------------------------------------------------------------------------
# Privacy guard — refuse anything that looks personal
# ---------------------------------------------------------------------------
_PERSONAL_PATTERNS = (
    ("identity", r"\bmy (?:full |first |last |nick ?)?name\b"),
    ("identity", r"\bi(?:'m| am) \d{1,3}\b"),
    ("identity", r"\bi (?:was )?born\b"),
    ("identity", r"\bi (?:live|reside) (?:in|at)\b"),
    ("identity", r"\bi work (?:at|for|as)\b"),
    (
        "family",
        r"\bmy (?:wife|husband|partner|girlfriend|boyfriend|son|daughter|"
        r"child|kid|mother|father|mom|dad|parents|brother|sister|family|"
        r"pet|dog|cat)\b",
    ),
    ("preference", r"\bmy (?:favorite|favourite|preferred|least favorite)\b"),
    ("preference", r"\bi (?:prefer|like|love|hate|dislike|enjoy)\b"),
    ("preference", r"\bremember (?:that )?my\b"),
    (
        "private",
        r"\bmy (?:birthday|age|address|home|house|apartment|salary|job|boss|"
        r"manager|schedule|calendar|appointment|notes?|journal|diary|"
        r"messages?|email|phone|number)\b",
    ),
    (
        "credential",
        r"\b(?:password|passwd|passphrase|api[ _-]?key|access[ _-]?token|"
        r"secret|credentials?|private[ _-]?key|recovery[ _-]?code)\b",
    ),
    ("credential", r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    ("contact", r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}"),
    ("contact", r"\+?\d[\d\s().\-]{8,}\d"),
    ("private", r"\b(?:confidential|do not share|keep (?:this )?local|between us)\b"),
)

_PERSONAL_REGEXES = tuple(
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in _PERSONAL_PATTERNS
)


def _personal_reason(*fields) -> str:
    """
    Return a short reason when any field looks personal, else ``""``.

    Used by :func:`save_shared_knowledge` to keep private data local.
    """
    text = " ".join(str(field or "") for field in fields)

    for label, regex in _PERSONAL_REGEXES:
        if regex.search(text):
            return f"looks like personal data ({label})"

    if _term_present(text):
        return "contains a locally registered private term"

    return ""


# ---------------------------------------------------------------------------
# Lazy client handling
# ---------------------------------------------------------------------------
_client = None
_client_attempted = False
_client_error = ""
_client_lock = threading.RLock()


def is_configured() -> bool:
    """True when SUPABASE_URL and SUPABASE_ANON_KEY are present."""
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def is_enabled() -> bool:
    """True when shared knowledge is configured, enabled and safe to use."""
    if not SHARING_ENABLED:
        return False
    if not is_configured():
        return False
    if not SUPABASE_AVAILABLE:
        # Configured but not usable: pip install supabase
        return False
    # Never enable the client with a service_role/secret key.
    return not key_looks_like_service_role(SUPABASE_ANON_KEY)


def status() -> dict:
    """Configuration summary (no network call, no secrets)."""
    configured = is_configured()
    enabled = is_enabled()

    reason = _client_error
    if not configured:
        reason = (
            "SUPABASE_URL and/or SUPABASE_ANON_KEY are not set "
            "(copy .env.example to .env)"
        )
    elif not SHARING_ENABLED:
        reason = "disabled by KIRA_SHARED_KNOWLEDGE"
    elif key_looks_like_service_role(SUPABASE_ANON_KEY):
        reason = "refused: the configured key is a service_role/secret key"
    elif not SUPABASE_AVAILABLE:
        reason = "the 'supabase' package is not installed (pip install supabase)"

    return {
        "configured": configured,
        "enabled": enabled,
        "installed": SUPABASE_AVAILABLE,
        "dotenv": DOTENV_AVAILABLE,
        "table": TABLE_NAME,
        "url": SUPABASE_URL,
        "reason": reason,
    }


def _get_client():
    """
    Return a lazily-created Supabase client, or None.

    Only the PUBLIC anon/publishable key is ever passed to the client.
    A service_role/secret key is refused even if it was placed in
    ``SUPABASE_ANON_KEY`` by mistake.
    """
    global _client, _client_attempted, _client_error

    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client

        if _client_attempted:
            return None

        _client_attempted = True

        if not SHARING_ENABLED:
            _client_error = "shared knowledge disabled by KIRA_SHARED_KNOWLEDGE"
            logger.info("Supabase shared knowledge disabled by configuration.")
            return None

        if not is_configured():
            _client_error = "SUPABASE_URL / SUPABASE_ANON_KEY not configured"
            logger.info(
                "Supabase shared knowledge disabled: set SUPABASE_URL and "
                "SUPABASE_ANON_KEY in .env (see .env.example)."
            )
            return None

        if key_looks_like_service_role(SUPABASE_ANON_KEY):
            _client_error = (
                "refused: the configured key is a service_role/secret key"
            )
            logger.error(SERVICE_ROLE_WARNING)
            return None

        if not SUPABASE_AVAILABLE:
            _client_error = "the 'supabase' package is not installed"
            logger.info(
                "Supabase shared knowledge disabled: install with "
                "'pip install supabase'."
            )
            return None

        try:
            # NOTE: anon (public) key only — never the service_role key.
            _client = _create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
            _client_error = ""
            logger.info(
                "Supabase shared knowledge enabled (table '%s').", TABLE_NAME
            )
        except Exception as exc:
            _client_error = str(exc)
            logger.warning("Supabase client creation failed: %s", exc)
            _client = None

        return _client


def reset_client():
    """Drop the cached client (used after configuration changes and in tests)."""
    global _client, _client_attempted, _client_error

    with _client_lock:
        _client = None
        _client_attempted = False
        _client_error = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean(value, max_length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_length]


def normalize_kind(kind) -> str:
    """Return a supported kind, or ``""`` when the kind is not allowed."""
    text = re.sub(r"[^a-z_]", "", str(kind or "").strip().lower())
    return text if text in ALLOWED_KINDS else ""


def topic_from_query(query) -> str:
    """Build a stable, upsert-friendly topic key from a search query."""
    text = _clean(query, MAX_TOPIC_LENGTH).lower()
    text = re.sub(r"[^a-z0-9À-ÿ]+", "_", text).strip("_")
    return text[:MAX_TOPIC_LENGTH]


def _search_words(query, max_words: int = MAX_SEARCH_WORDS) -> list:
    """Split a query into sanitized words usable in PostgREST ilike filters."""
    words = re.findall(r"[A-Za-zÀ-ÿ0-9_\-]+", str(query or ""))
    cleaned = []
    for word in words:
        if len(word) < 2:
            continue
        if word.lower() not in {item.lower() for item in cleaned}:
            cleaned.append(word)
    return cleaned[:max_words]


def _normalize_tags(tags) -> list:
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = [tags]

    cleaned = []
    for tag in tags:
        text = _clean(tag, MAX_TAG_LENGTH).lower()
        if text and text not in cleaned:
            cleaned.append(text)

    return cleaned[:MAX_TAGS]


def _normalize_row(row) -> dict:
    if not isinstance(row, dict):
        return {}

    tags = row.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    return {
        "kind": str(row.get("kind", "") or ""),
        "topic": str(row.get("topic", "") or ""),
        "title": str(row.get("title", "") or ""),
        "content": str(row.get("content", "") or ""),
        "source_url": str(row.get("source_url", "") or ""),
        "tags": [str(tag) for tag in tags],
        "updated_at": str(row.get("updated_at", "") or ""),
    }


def format_shared_knowledge(items, limit: int = 3) -> str:
    """Format shared knowledge rows as a short bullet list (or ``""``)."""
    lines = []

    for item in list(items or [])[: max(1, int(limit))]:
        title = _clean(item.get("title", ""), MAX_TITLE_LENGTH)
        topic = _clean(item.get("topic", ""), MAX_TOPIC_LENGTH).replace("_", " ")
        content = _clean(item.get("content", ""), 400)
        source_url = _clean(item.get("source_url", ""), MAX_SOURCE_URL_LENGTH)

        headline = title or topic or "shared entry"
        line = f"- {headline}: {content}"
        if source_url:
            line += f" (source: {source_url})"
        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API — writing shared knowledge
# ---------------------------------------------------------------------------
def save_shared_knowledge(
    kind: str,
    topic: str,
    content: str,
    title: str = "",
    source_url: str = "",
    tags=None,
) -> bool:
    """
    Upsert one shared, NON-personal knowledge entry.

    Callers must only pass public web research, learned public web pages or
    shared project knowledge — never conversations, names, preferences,
    tasks or private notes.

    Returns True when Supabase accepted the entry. Returns False (without
    raising) when shared knowledge is disabled, when the content looks
    personal, or when the request fails.
    """
    normalized_kind = normalize_kind(kind)
    if not normalized_kind:
        logger.warning(
            "Shared knowledge refused: unsupported kind %r (allowed: %s).",
            kind,
            ", ".join(sorted(ALLOWED_KINDS)),
        )
        return False

    topic = _clean(topic, MAX_TOPIC_LENGTH)
    title = _clean(title, MAX_TITLE_LENGTH)
    content = _clean(content, MAX_CONTENT_LENGTH)
    source_url = _clean(source_url, MAX_SOURCE_URL_LENGTH)
    tags = _normalize_tags(tags)

    if not topic or not content:
        return False

    # PRIVACY: personal data never leaves the machine.
    reason = _personal_reason(topic, title, content)
    if reason:
        logger.warning(
            "Shared knowledge refused: %s. The entry stays local.", reason
        )
        return False

    if not is_enabled():
        return False

    client = _get_client()
    if client is None:
        return False

    payload = {
        "kind": normalized_kind,
        "topic": topic,
        "title": title,
        "content": content,
        "source_url": source_url,
    }
    if tags:
        payload["tags"] = tags

    try:
        client.table(TABLE_NAME).upsert(
            payload,
            on_conflict="kind,topic",
        ).execute()
        logger.info("Shared knowledge saved: [%s] %s", normalized_kind, topic)
        return True
    except Exception as exc:
        message = str(exc)
        hint = ""

        if "row-level security" in message.lower() or "policy" in message.lower():
            hint = (
                " Run the latest SUPABASE_SCHEMA.sql: KIRA upserts shared "
                "entries and the anon role needs the insert and update "
                "policies to do that."
            )

        logger.warning(
            "Shared knowledge save failed for '%s': %s%s", topic, message, hint
        )
        return False


def save_web_research(
    query: str,
    content: str,
    title: str = "",
    source_url: str = "",
    tags=None,
) -> bool:
    """Share a public web-research summary (search results)."""
    return save_shared_knowledge(
        kind=KIND_WEB_RESEARCH,
        topic=topic_from_query(query),
        title=title or f"Web search results for '{_clean(query, 200)}'",
        content=content,
        source_url=source_url,
        tags=tags,
    )


def save_web_page(
    url: str,
    title: str,
    content: str,
    tags=None,
) -> bool:
    """Share knowledge learned from a public web page."""
    topic = _clean(url, MAX_TOPIC_LENGTH).lower()
    topic = re.sub(r"^https?://", "", topic)
    topic = re.sub(r"[^a-z0-9À-ÿ]+", "_", topic).strip("_")

    return save_shared_knowledge(
        kind=KIND_WEB_PAGE,
        topic=topic or "web_page",
        title=title or url,
        content=content,
        source_url=url,
        tags=tags,
    )


def save_project_knowledge(
    topic: str,
    content: str,
    title: str = "",
    source_url: str = "",
    tags=None,
) -> bool:
    """Share non-personal project knowledge (architecture, conventions, ...)."""
    return save_shared_knowledge(
        kind=KIND_PROJECT,
        topic=topic,
        title=title,
        content=content,
        source_url=source_url,
        tags=tags,
    )


# ---------------------------------------------------------------------------
# Public API — reading shared knowledge
# ---------------------------------------------------------------------------
_SELECT_COLUMNS = "kind,topic,title,content,source_url,tags,updated_at"


def _search_via_rpc(query: str, limit: int, kind: str):
    """
    Search through the SQL function from SUPABASE_SCHEMA.sql.

    Returns a list on success, or None when the RPC is unavailable so the
    caller can fall back to plain filters.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        response = client.rpc(
            SEARCH_RPC,
            {
                "p_query": query,
                "p_limit": limit,
                "p_kind": kind or None,
            },
        ).execute()
    except Exception as exc:
        logger.debug("Shared knowledge RPC search unavailable: %s", exc)
        return None

    rows = getattr(response, "data", None)
    if rows is None:
        return None

    return [_normalize_row(row) for row in rows if row]


def _search_with_filters(query: str, limit: int, kind: str):
    """PostgREST ilike fallback: every word must match some field."""
    client = _get_client()
    if client is None:
        return []

    words = _search_words(query)
    if not words:
        return []

    try:
        request = client.table(TABLE_NAME).select(_SELECT_COLUMNS)

        if kind:
            request = request.eq("kind", kind)

        for word in words:
            request = request.or_(
                "topic.ilike.%{0}%,title.ilike.%{0}%,content.ilike.%{0}%".format(
                    word
                )
            )

        response = (
            request.order("updated_at", desc=True)
            .limit(max(1, min(int(limit), 20)))
            .execute()
        )

        rows = getattr(response, "data", None) or []
        return [_normalize_row(row) for row in rows if row]
    except Exception as exc:
        logger.warning(
            "Shared knowledge search failed for '%s': %s", query, exc
        )
        return []


def search_shared_knowledge(query: str, limit: int = 5, kind: str = "") -> list:
    """
    Search shared knowledge across topic, title and content.

    Returns a list of dicts (possibly empty). Never raises.
    """
    query = _clean(query, 300)

    if not query or not is_enabled():
        return []

    limit = max(1, min(int(limit or 5), 20))
    kind = normalize_kind(kind) if kind else ""

    rows = _search_via_rpc(query, limit, kind)
    if rows is not None:
        return rows[:limit]

    return _search_with_filters(query, limit, kind)


def get_shared_knowledge(kind: str, topic: str):
    """Fetch one shared knowledge entry by (kind, topic), or None."""
    normalized_kind = normalize_kind(kind)
    topic = _clean(topic, MAX_TOPIC_LENGTH)

    if not normalized_kind or not topic or not is_enabled():
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        response = (
            client.table(TABLE_NAME)
            .select(_SELECT_COLUMNS)
            .eq("kind", normalized_kind)
            .eq("topic", topic)
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        return _normalize_row(rows[0]) if rows else None
    except Exception as exc:
        logger.warning("Shared knowledge fetch failed for '%s': %s", topic, exc)
        return None


def build_shared_context(query: str, limit: int = 3) -> str:
    """
    Build a system-prompt block with shared knowledge, or ``""``.

    Only non-personal shared entries are ever returned; the text explicitly
    tells the model these facts are shared and are not user memories.
    """
    items = search_shared_knowledge(query, limit=limit)
    if not items:
        return ""

    body = format_shared_knowledge(items, limit=limit)
    if not body:
        return ""

    return (
        "SHARED KNOWLEDGE (non-personal, from the shared KIRA knowledge base):\n"
        "These are public web research or shared project facts. They are NOT "
        "the user's personal memories and must not be treated as such.\n"
        f"{body}"
    )


__all__ = [
    "ALLOWED_KINDS",
    "KIND_PROJECT",
    "KIND_WEB_PAGE",
    "KIND_WEB_RESEARCH",
    "SUPABASE_AVAILABLE",
    "TABLE_NAME",
    "build_shared_context",
    "format_shared_knowledge",
    "get_private_terms",
    "get_shared_knowledge",
    "is_configured",
    "is_enabled",
    "key_looks_like_service_role",
    "normalize_kind",
    "reset_client",
    "save_project_knowledge",
    "save_shared_knowledge",
    "save_web_page",
    "save_web_research",
    "search_shared_knowledge",
    "set_private_terms",
    "status",
]
