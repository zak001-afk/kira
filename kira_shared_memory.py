"""
KIRA Shared Memory Module — Shared (non-personal) knowledge via Supabase.

This module is the ONLY path through which KIRA talks to Supabase.

Privacy model
-------------
LOCAL ONLY (kira_memory.py / kira_memory.db):
  - Conversations
  - User names and identity facts
  - Personal preferences
  - Tasks, reminders and todos
  - Private notes

SHARED (this module -> Supabase `shared_knowledge` table):
  - Public web research (search summaries, learned web pages)
  - General, non-personal factual knowledge

SECURITY
--------
KIRA only ever uses the PUBLIC anon key (`SUPABASE_ANON_KEY`).
The Supabase `service_role` key bypasses Row Level Security and must
never be used or stored by KIRA. If a `SUPABASE_SERVICE_ROLE_KEY` is
detected in the environment it is IGNORED and a warning is logged.
Never put the service_role key in `.env`, code, or logs.

Setup
-----
1. Run SUPABASE_SCHEMA.sql in the Supabase SQL editor.
2. Copy `.env.example` to `.env` and fill in SUPABASE_URL and
   SUPABASE_ANON_KEY (Project Settings -> API -> anon public key).

The module degrades gracefully: when Supabase is not configured or the
`supabase` package is missing, every call becomes a safe no-op and KIRA
keeps working fully offline with its local memory.
"""

import os
import re
import logging

logger = logging.getLogger("kira.shared_memory")

TABLE_NAME = os.environ.get(
    "SUPABASE_SHARED_TABLE",
    "shared_knowledge",
)

# ---------------------------------------------------------------------
# Environment loading (python-dotenv is optional)
# ---------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        override=False,
    )
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    create_client = None
    SUPABASE_AVAILABLE = False

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()

# SECURITY: never use or expose the service_role key. If one is present
# in the environment, ignore it completely and warn the user.
if os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip():
    logger.warning(
        "SUPABASE_SERVICE_ROLE_KEY detected in the environment. "
        "KIRA NEVER uses the service_role key — it is ignored. "
        "Remove it from your environment/.env and use SUPABASE_ANON_KEY only."
    )

# ---------------------------------------------------------------------
# Lazy client handling
# ---------------------------------------------------------------------
_client = None
_client_attempted = False


def is_enabled() -> bool:
    """True when Supabase shared knowledge is configured and usable."""
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def _get_client():
    """
    Return a lazily-created Supabase client, or None.

    Only the PUBLIC anon key is ever passed to the client. Never the
    service_role key.
    """
    global _client, _client_attempted

    if _client is not None:
        return _client

    if _client_attempted:
        return None

    _client_attempted = True

    if not is_enabled():
        logger.info(
            "Supabase shared knowledge disabled: set SUPABASE_URL and "
            "SUPABASE_ANON_KEY in .env (see .env.example)."
        )
        return None

    if not SUPABASE_AVAILABLE:
        logger.info(
            "Supabase shared knowledge disabled: the 'supabase' package "
            "is not installed. Install with: pip install supabase"
        )
        return None

    try:
        # NOTE: anon (public) key only — never the service_role key.
        _client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        logger.info("Supabase shared knowledge enabled for table '%s'.", TABLE_NAME)
    except Exception as exc:
        logger.warning("Supabase client creation failed: %s", exc)
        _client = None

    return _client


def _reset_client():
    """Allow tests / config reloads to re-create the client."""
    global _client, _client_attempted
    _client = None
    _client_attempted = False


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _clean_text(value, max_length=2000) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value[:max_length]


def _search_words(query, max_words=5) -> list:
    """Split a query into sanitized words usable in ilike filters."""
    words = re.findall(r"[A-Za-zÀ-ÿ0-9_\-]+", str(query or ""))
    return [word for word in words if len(word) >= 2][:max_words]


def _normalize_row(row) -> dict:
    if not isinstance(row, dict):
        return {}
    return {
        "kind": str(row.get("kind", "") or ""),
        "topic": str(row.get("topic", "") or ""),
        "title": str(row.get("title", "") or ""),
        "content": str(row.get("content", "") or ""),
        "source_url": str(row.get("source_url", "") or ""),
        "updated_at": str(row.get("updated_at", "") or ""),
    }


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def save_shared_knowledge(
    kind: str,
    topic: str,
    content: str,
    title: str = "",
    source_url: str = "",
) -> bool:
    """
    Upsert one shared (non-personal) knowledge entry.

    Callers must only pass PUBLIC web knowledge here — never personal
    conversations, names, preferences, tasks or private notes.

    Returns True when the entry was accepted by Supabase.
    """
    kind = _clean_text(kind, 50).lower() or "web_research"
    topic = _clean_text(topic, 120)
    content = _clean_text(content, 4000)
    title = _clean_text(title, 300)
    source_url = _clean_text(source_url, 1000)

    if not topic or not content:
        return False

    if not is_enabled():
        return False

    client = _get_client()
    if client is None:
        return False

    try:
        client.table(TABLE_NAME).upsert(
            {
                "kind": kind,
                "topic": topic,
                "title": title,
                "content": content,
                "source_url": source_url,
            },
            on_conflict="kind,topic",
        ).execute()
        logger.info("Shared knowledge saved: [%s] %s", kind, topic)
        return True
    except Exception as exc:
        logger.warning("Shared knowledge save failed for '%s': %s", topic, exc)
        return False


def search_shared_knowledge(query: str, limit: int = 5) -> list:
    """
    Search shared knowledge across topic, title and content.

    Returns a list of dicts (possibly empty). Never raises.
    """
    query = str(query or "").strip()

    if not query or not is_enabled():
        return []

    client = _get_client()
    if client is None:
        return []

    words = _search_words(query)
    if not words:
        return []

    try:
        request = client.table(TABLE_NAME).select(
            "kind,topic,title,content,source_url,updated_at"
        )

        # Every word must match at least one searchable field.
        for word in words:
            request = request.or_(
                f"topic.ilike.%{word}%,title.ilike.%{word}%,content.ilike.%{word}%"
            )

        request = request.order("updated_at", desc=True).limit(
            max(1, min(int(limit), 20))
        )

        response = request.execute()
        rows = getattr(response, "data", None) or []

        return [_normalize_row(row) for row in rows if row]
    except Exception as exc:
        logger.warning("Shared knowledge search failed for '%s': %s", query, exc)
        return []


def get_shared_knowledge(kind: str, topic: str):
    """
    Fetch one shared knowledge entry by (kind, topic), or None.
    """
    kind = _clean_text(kind, 50).lower()
    topic = _clean_text(topic, 120)

    if not kind or not topic or not is_enabled():
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        response = (
            client.table(TABLE_NAME)
            .select("kind,topic,title,content,source_url,updated_at")
            .eq("kind", kind)
            .eq("topic", topic)
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        if rows:
            return _normalize_row(rows[0])
        return None
    except Exception as exc:
        logger.warning("Shared knowledge fetch failed for '%s': %s", topic, exc)
        return None
