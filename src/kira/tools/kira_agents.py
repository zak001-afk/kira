"""KIRA's controller foundation: specialist agents, tool registry, activity.

Architecture rules enforced here:

- Every tool belongs to ONE specialist agent (research / memory / windows).
- Tools are registered with a declared argument schema; arguments are
  validated BEFORE the handler runs. Unknown tools and bad arguments are
  structured failures, never tracebacks.
- Tools return data (kira_tools.ToolResult). They never speak and never
  touch the UI; interfaces decide presentation.
- Every run is recorded in an activity feed with METADATA ONLY (agent, tool,
  ok, elapsed, error code). Queries, titles and results are deliberately NOT
  stored: the feed powers truthful UI displays, not surveillance.
- ``consequential=True`` marks tools that change something outside KIRA
  (files, shared knowledge, the desktop). Enforcement of an approval step is
  a later increment; the flag is the contract for it.
"""
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import os
import threading
import time
import uuid

import kira_tools

AGENTS = {
    "research": "Web research and the shared (non-personal) knowledge base.",
    "memory": "Controlled access to LOCAL memory. Nothing here leaves the machine.",
    "windows": "Tasks, reminders and Windows desktop helpers.",
    "plugins": "Capabilities contributed by plugins/ extensions. Manageable at runtime.",
    "programming": "Create full projects and apply code changes inside the KIRA code workspace.",
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    agent: str
    description: str
    args: dict            # arg name -> {"type": type, "required": bool}
    handler: object
    consequential: bool = False
    accepts_extra: bool = False   # forward unknown args instead of dropping them
    owner: str = ""               # plugin id when the tool came from plugins/


_REGISTRY = {}
_TOOL_OWNER = {}      # tool name -> owner id ("" for built-ins)
_ACTIVITY = deque(maxlen=200)
_LOCK = threading.Lock()
_BUILTINS_READY = False


def register_tool(name, agent, description, args, handler, consequential=False,
                  accepts_extra=False, owner=""):
    if agent not in AGENTS:
        raise ValueError(f"Unknown agent '{agent}'. Agents: {', '.join(AGENTS)}.")
    with _LOCK:
        _REGISTRY[str(name)] = ToolSpec(name=str(name), agent=agent, description=description,
                                        args=dict(args or {}), handler=handler,
                                        consequential=bool(consequential),
                                        accepts_extra=bool(accepts_extra),
                                        owner=str(owner or ""))
        _TOOL_OWNER[str(name)] = str(owner or "")


def unregister_tool(name):
    """Test/plugin hygiene; built-ins are simply re-registered on demand."""
    with _LOCK:
        _REGISTRY.pop(str(name), None)
        _TOOL_OWNER.pop(str(name), None)


def unregister_tools_of(owner):
    """Remove every tool contributed by one plugin (unload/reload)."""
    owner = str(owner or "")
    if not owner:
        return []
    with _LOCK:
        names = [name for name, spec in _REGISTRY.items() if spec.owner == owner]
        for name in names:
            _REGISTRY.pop(name, None)
            _TOOL_OWNER.pop(name, None)
    return sorted(names)


def validate_args(spec, raw):
    """Return (kwargs, error). Unknown keys are dropped, never forwarded."""
    raw = dict(raw or {})
    kwargs = {}
    for arg_name, rules in spec.args.items():
        expected = rules.get("type", str)
        required = bool(rules.get("required", False))
        if arg_name not in raw or raw[arg_name] is None or str(raw[arg_name]).strip() == "":
            if required:
                return None, f"Missing required argument '{arg_name}' for tool '{spec.name}'."
            continue
        value = raw[arg_name]
        if not isinstance(value, expected):
            try:
                value = expected(value)
            except (TypeError, ValueError):
                return None, (f"Argument '{arg_name}' of tool '{spec.name}' must be "
                              f"{expected.__name__}, got {type(value).__name__}.")
        kwargs[arg_name] = value
    if spec.accepts_extra:
        # Tools that declare no schema (typical simple plugins) receive every
        # argument they were given, as-is.
        for arg_name, value in raw.items():
            if arg_name not in kwargs:
                kwargs[arg_name] = value
    return kwargs, None


# ── Approval gate for consequential tools ────────────────────────────────────

APPROVAL_TTL_SECONDS = 180
_PENDING_APPROVALS = {}
_FALSE_VALUES = {"0", "false", "off", "no"}


def approvals_required() -> bool:
    """Consequential tools require approval unless explicitly disabled."""
    return os.environ.get("KIRA_REQUIRE_APPROVAL", "1").strip().lower() not in _FALSE_VALUES


def _prune_approvals():
    deadline = time.monotonic() - APPROVAL_TTL_SECONDS
    for key in [k for k, v in _PENDING_APPROVALS.items() if v["created"] < deadline]:
        _PENDING_APPROVALS.pop(key, None)


def resolve_approval(approval_id, approve, source="api"):
    """Execute (or discard) a previously gated tool call. Returns a ToolResult."""
    with _LOCK:
        _prune_approvals()
        entry = _PENDING_APPROVALS.pop(str(approval_id), None)
    if entry is None:
        return kira_tools.ToolResult(action="approval", ok=False, error_code="unknown_approval",
                                     error="That confirmation has expired or does not exist.")
    spec = entry["spec"]
    if not approve:
        result = kira_tools.ToolResult(action=spec.name, ok=False, error_code="approval_rejected",
                                       error="The action was cancelled before it ran.")
        _record(spec, result, source)
        return result
    result = kira_tools.run_tool(spec.name, spec.handler, **entry["kwargs"])
    _record(spec, result, source)
    return result


def run(name, raw_args=None, source="api", approved=False):
    """Validate, gate, execute and record one tool call. Always a ToolResult.

    Consequential tools do not run immediately: the call is parked and a
    ``ToolResult`` with ``error_code == "approval_required"`` and an
    ``approval_id`` comes back. The interface asks the user, then calls
    ``resolve_approval``. Pass ``approved=True`` only when the user already
    confirmed through the calling interface.
    """
    ensure_builtins()
    spec = _REGISTRY.get(str(name))
    if spec is None:
        return kira_tools.ToolResult(action=str(name), ok=False, error_code="unknown_tool",
                                     error=f"No tool named '{name}' is registered.")
    kwargs, error = validate_args(spec, raw_args)
    if error:
        result = kira_tools.ToolResult(action=spec.name, ok=False,
                                       error=error, error_code="invalid_args")
        _record(spec, result, source)
        return result
    if spec.consequential and approvals_required() and not approved:
        approval_id = uuid.uuid4().hex[:12]
        with _LOCK:
            _prune_approvals()
            _PENDING_APPROVALS[approval_id] = {"spec": spec, "kwargs": kwargs,
                                               "created": time.monotonic()}
        extra = {"approval_id": approval_id, "agent": spec.agent}
        if spec.name == "code_apply_edit":
            # The approval card shows WHAT will change: attach a read-only
            # diff when the target file exists and the old block is unique.
            try:
                import kira_code
                preview = kira_code.preview_edit(kwargs.get("path", ""),
                                                 kwargs.get("old", ""),
                                                 kwargs.get("new", ""))
                if preview.get("diff"):
                    extra["diff"] = preview["diff"]
            except Exception:
                pass
        result = kira_tools.ToolResult(action=spec.name, ok=False, error_code="approval_required",
                                       error=f"'{spec.name}' needs your confirmation before it runs.",
                                       extra=extra)
        _record(spec, result, source)
        return result
    result = kira_tools.run_tool(spec.name, spec.handler, **kwargs)
    _record(spec, result, source)
    return result


def _record(spec, result, source):
    with _LOCK:
        _ACTIVITY.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "agent": spec.agent,
            "tool": spec.name,
            "ok": bool(result.ok),
            "elapsed_ms": int(result.elapsed_ms),
            "error_code": result.error_code or "",
            "source": str(source),
        })


def tool_catalog():
    """Public, serializable view of every registered tool (planner, API
    docs): names, descriptions and arg specs — never the handlers."""
    ensure_builtins()
    with _LOCK:
        specs = list(_REGISTRY.values())
    return [{
        "name": spec.name,
        "agent": spec.agent,
        "description": spec.description,
        "consequential": spec.consequential,
        "accepts_extra": spec.accepts_extra,
        "owner": spec.owner,
        "args": {name: {"type": rules.get("type", str).__name__,
                        "required": bool(rules.get("required", False))}
                 for name, rules in spec.args.items()},
    } for spec in sorted(specs, key=lambda item: item.name)]


def recent_activity(limit=30):
    with _LOCK:
        items = list(_ACTIVITY)
    return items[-int(limit):][::-1]  # newest first


def agents_snapshot():
    """Real registry state for the UI's agent panels — no invented activity."""
    ensure_builtins()
    with _LOCK:
        specs = list(_REGISTRY.values())
        last_by_agent = {}
        for entry in _ACTIVITY:
            last_by_agent[entry["agent"]] = entry["time"]
    snapshot = []
    for agent_id, description in AGENTS.items():
        tools = sorted(s.name for s in specs if s.agent == agent_id)
        snapshot.append({
            "id": agent_id,
            "description": description,
            "tools": tools,
            "consequential_tools": sorted(s.name for s in specs
                                          if s.agent == agent_id and s.consequential),
            "last_activity": last_by_agent.get(agent_id),
            "plugin_tools": sorted(s.name for s in specs
                                   if s.agent == agent_id and s.owner),
        })
    return snapshot


# ── Built-in specialist tools (lazy imports keep dependencies optional) ──────

def _search_shared_knowledge(query, limit=3):
    import kira_web
    return kira_web.search_shared_knowledge(query, limit=limit)


def _web_learn(topic):
    import kira_web
    return kira_web.search_and_learn(topic)


def _web_search(query, num_results=5):
    import kira_web
    return kira_web.search_web(query, num_results=max(1, min(int(num_results or 5), 10)))


def _atlas_research(query, max_wait=240, language=""):
    """Deep research delegated to the Atlas agent (E:\\research-agent).

    Runs ``atlas_cli.py`` with Atlas' own venv in a subprocess: the Atlas
    server does NOT need to be running, and KIRA's environment stays
    untouched. Returns the synthesis (+ sources footer) as ``response``.

    ``language`` (fr, en, ar…) is forced on the synthesis: Atlas must answer
    in the language the user asked in, even when every source is English.
    """
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    from kira import paths

    query = str(query or "").strip()
    if not query:
        return {"ok": False, "error": "Requête de recherche vide.",
                "error_code": "bad_request"}
    lang = str(language or "").strip().lower()[:2]

    atlas_dir = Path(os.environ.get("ATLAS_DIR")
                     or paths.PROJECT_ROOT.parent / "research-agent")
    cli = atlas_dir / "atlas_cli.py"
    if not cli.is_file():
        return {"ok": False, "error": f"Agent Atlas introuvable : {cli}",
                "error_code": "atlas_missing"}
    python = atlas_dir / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        python = Path(sys.executable)  # secours : interpréteur courant

    command = [str(python), str(cli), query]
    if lang:
        command += ["--lang", lang]

    proc = subprocess.run(
        command,
        cwd=str(atlas_dir), capture_output=True,
        encoding="utf-8", errors="replace",
        timeout=max(30, int(max_wait)))

    # La dernière ligne « { ... } » est le payload (les journaux précèdent).
    payload = {}
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except ValueError:
                payload = {}
            break

    if proc.returncode != 0 or not payload.get("ok"):
        error = str(payload.get("error") or "").strip()
        if not error:
            error = ((proc.stderr or "").strip()[-400:]
                     or "Atlas n'a pas pu mener la recherche.")
        return {"ok": False, "error": error, "error_code": "atlas_failed"}

    answer = str(payload.get("answer") or "").strip()
    if not answer:
        return {"ok": False, "error": "Atlas n'a renvoyé aucune réponse.",
                "error_code": "atlas_empty"}

    answer = _ensure_atlas_language(answer, lang)

    sources = list(payload.get("sources") or [])
    # Réponse propre type ChatGPT : ni crochets [1], ni liste de liens —
    # les sources restent disponibles dans les données du résultat.
    return {"ok": True, "response": answer,
            "sources": sources,
            "interpretation": str(payload.get("interpretation") or ""),
            "atlas_elapsed": payload.get("elapsed")}


# Keyless public information tools (kira_info): no API keys anywhere.


def _ensure_atlas_language(text, language):
    """Garde-fou final : la synthèse Atlas doit être dans la langue demandée.

    Détection locale (aucun coût, ~0 ms) ; une traduction UNE seule fois n'est
    lancée que si la réponse est franchement dans la mauvaise langue. Si la
    traduction échoue, on garde la réponse d'origine plutôt que de perdre la
    recherche.
    """
    if not language:
        return text
    try:
        from kira.core import kira_language

        def model_call(messages=(), options=None):
            import kira_ai
            reply = kira_ai.chat(list(messages), timeout=20,
                                 options=options or {})
            if not getattr(reply, "ok", False):
                raise RuntimeError(getattr(reply, "error", None) or "translation failed")
            return {"message": {"content": reply.text}}

        return kira_language.ensure_reply_language(text, language, model_call)
    except Exception:
        return text

def _get_weather(city):
    import kira_info
    return kira_info.get_weather(city)


def _get_holidays(country="", year=0):
    import kira_info
    return kira_info.get_holidays(country, year)


def _convert_currency(amount, from_currency, to_currency):
    import kira_info
    return kira_info.convert_currency(amount, from_currency, to_currency)


def _tell_joke(language="en"):
    import kira_info
    return kira_info.tell_joke(language)


def _fun_fact():
    import kira_info
    return kira_info.fun_fact()


def _wiki_summary(topic, language="en"):
    import kira_info
    return kira_info.wiki_summary(topic, language)


def _translate_text(text, target_language, source_language=""):
    import kira_info
    return kira_info.translate_text(text, target_language, source_language)


def _crypto_price(coin, currency="usd"):
    import kira_info
    return kira_info.crypto_price(coin, currency)


def _prayer_times(city=""):
    import kira_info
    return kira_info.prayer_times(city)


def _song_search(query, limit=3):
    import kira_info
    return kira_info.song_search(query, limit)


def _daily_quote():
    import kira_info
    return kira_info.daily_quote()


def _share_project_knowledge(topic, content):
    import kira_web
    return kira_web.share_project_knowledge(topic, content)


def _add_reminder(title, due_at=""):
    import kira_tasks
    return kira_tasks.add_task(title=title, task_type="reminder", due_at=due_at)


def _add_todo(title):
    import kira_tasks
    return kira_tasks.add_task(title=title, task_type="todo")


def _list_tasks():
    import kira_tasks
    return kira_tasks.list_tasks(completed=False, limit=10)


def _clear_completed_tasks():
    import kira_tasks
    return kira_tasks.clear_completed()


def _recall_memory(query, limit=5):
    """LOCAL memory search. Results must never be forwarded to a cloud model
    without explicit user approval (see kira_ai's privacy rules)."""
    import kira_memory
    return kira_memory.search_messages(query, limit=limit)


# Programming agent (kira_code): everything is jailed to one workspace root
# (KIRA_CODE_DIR or kira_workspace/). Reads are open; writes, deletes and
# command runs are consequential and pass the user's approval gate.

def _scaffold_project(name, template=""):
    import kira_code
    return kira_code.scaffold_project(name, template=template)


def _code_write_file(path, content=""):
    import kira_code
    return kira_code.write_file(path, content=content)


def _code_read_file(path):
    import kira_code
    return kira_code.read_file(path)


def _code_list_dir(path=""):
    import kira_code
    return kira_code.list_dir(path)


def _code_list_projects():
    import kira_code
    return kira_code.list_projects()


def _code_preview_edit(path, old, new=""):
    import kira_code
    return kira_code.preview_edit(path, old, new)


def _code_search_code(query, path="", extension=""):
    import kira_code
    return kira_code.search_code(query, path=path, extension=extension)


def _code_apply_edit(path, old, new=""):
    import kira_code
    return kira_code.apply_edit(path, old, new)


def _code_run_command(command):
    import kira_code
    return kira_code.run_command(command)


def _code_delete_path(path):
    import kira_code
    return kira_code.delete_path(path)


def _code_build(request, project=""):
    import kira_build
    return kira_build.code_build(request, project)


def _code_preview_build(request, project=""):
    import kira_build
    return kira_build.plan_build(request, project)


def _search_docs(query, limit=4):
    import kira_docs
    return kira_docs.search_docs(query, limit)


def _add_note(path, content=""):
    import kira_docs
    return kira_docs.add_document(path, content)


def _list_documents():
    import kira_docs
    return kira_docs.list_documents()


def _run_diagnostic():
    import kira_health
    return kira_health.run_health_check()


def _backup_memory(keep=5):
    import kira_ops
    return kira_ops.backup_memory(keep)


def _list_backups():
    import kira_ops
    return kira_ops.list_backups()


def _generate_plugin(name, description):
    import kira_ops
    return kira_ops.generate_plugin(name, description)


def _morning_briefing():
    import kira_scheduler
    text, data = kira_scheduler.briefing("fr")
    return {"ok": True, "text": text, "data": data, "response": text}


def ensure_builtins():
    global _BUILTINS_READY
    if _BUILTINS_READY:
        return
    _BUILTINS_READY = True
    register_tool("search_shared_knowledge", "research",
                  "Search the shared (Supabase) knowledge base.",
                  {"query": {"type": str, "required": True},
                   "limit": {"type": int, "required": False}},
                  _search_shared_knowledge)
    register_tool("share_project_knowledge", "research",
                  "Publish non-personal project knowledge to the shared base.",
                  {"topic": {"type": str, "required": True},
                   "content": {"type": str, "required": True}},
                  _share_project_knowledge, consequential=True)
    register_tool("web_learn", "research",
                  "Research a topic on the public web and keep the summary as knowledge. "
                  "Sharing is filtered by the shared-memory privacy gates.",
                  {"topic": {"type": str, "required": True}},
                  _web_learn)
    register_tool("web_search", "research",
                  "Search the public web; top results as structured data (max 10).",
                  {"query": {"type": str, "required": True},
                   "num_results": {"type": int, "required": False}},
                  _web_search)
    register_tool("atlas_research", "research",
                  "Deep web research with the Atlas agent: multi-source search, "
                  "reads the best pages, then a full sourced synthesis with a clear "
                  "conclusion. Use for any 'research on X' / 'fais une recherche "
                  "sur X' request instead of a plain web_search.",
                  {"query": {"type": str, "required": True},
                   "language": {"type": str, "required": False}},
                  _atlas_research)
    register_tool("get_weather", "research",
                  "Current weather and today/tomorrow forecast for a city (keyless Open-Meteo).",
                  {"city": {"type": str, "required": True}},
                  _get_weather)
    register_tool("get_holidays", "research",
                  "Public holidays for a country (ISO code or common name) and year (keyless Nager.Date).",
                  {"country": {"type": str, "required": False},
                   "year": {"type": int, "required": False}},
                  _get_holidays)
    register_tool("convert_currency", "research",
                  "Convert an amount between currencies, e.g. EUR to TND (keyless daily rates).",
                  {"amount": {"type": float, "required": True},
                   "from_currency": {"type": str, "required": True},
                   "to_currency": {"type": str, "required": True}},
                  _convert_currency)
    register_tool("tell_joke", "research",
                  "One safe joke (EN/FR/DE/ES/PT/CS) from a keyless service.",
                  {"language": {"type": str, "required": False}},
                  _tell_joke)
    register_tool("fun_fact", "research",
                  "One random true fun fact (English) from a keyless service.",
                  {}, _fun_fact)
    register_tool("crypto_price", "research",
                  "Live crypto price in usd/eur/tnd (CoinGecko, keyless).",
                  {"coin": {"type": str, "required": True},
                   "currency": {"type": str, "required": False}},
                  _crypto_price)
    register_tool("prayer_times", "research",
                  "Today's prayer times + Hijri date for a city (Aladhan, keyless).",
                  {"city": {"type": str, "required": False}},
                  _prayer_times)
    register_tool("song_search", "research",
                  "Find songs on iTunes (keyless): title, artist, album, 30s preview.",
                  {"query": {"type": str, "required": True},
                   "limit": {"type": int, "required": False}},
                  _song_search)
    register_tool("daily_quote", "research",
                  "One inspirational quote (ZenQuotes, keyless).",
                  {}, _daily_quote)
    register_tool("wiki_summary", "research",
                  "Lead summary of the best-matching Wikipedia article (keyless, EN/FR/AR editions).",
                  {"topic": {"type": str, "required": True},
                   "language": {"type": str, "required": False}},
                  _wiki_summary)
    register_tool("translate_text", "research",
                  "Translate a short text between languages (keyless MyMemory).",
                  {"text": {"type": str, "required": True},
                   "target_language": {"type": str, "required": True},
                   "source_language": {"type": str, "required": False}},
                  _translate_text)
    register_tool("add_reminder", "windows",
                  "Add a reminder task, optionally with a due time.",
                  {"title": {"type": str, "required": True},
                   "due_at": {"type": str, "required": False}},
                  _add_reminder)
    register_tool("add_todo", "windows",
                  "Add a todo task.",
                  {"title": {"type": str, "required": True}},
                  _add_todo)
    register_tool("list_tasks", "windows",
                  "List pending tasks.", {}, _list_tasks)
    register_tool("clear_completed_tasks", "windows",
                  "Delete completed tasks.", {}, _clear_completed_tasks,
                  consequential=True)
    register_tool("recall_memory", "memory",
                  "Search LOCAL conversation memory. Local only.",
                  {"query": {"type": str, "required": True},
                   "limit": {"type": int, "required": False}},
                  _recall_memory)
    register_tool("scaffold_project", "programming",
                  "Create a full project in the code workspace. "
                  "Templates: python (default), web, node, empty.",
                  {"name": {"type": str, "required": True},
                   "template": {"type": str, "required": False}},
                  _scaffold_project, consequential=True)
    register_tool("code_list_projects", "programming",
                  "List the projects in the code workspace (name, files, modified).",
                  {}, _code_list_projects)
    register_tool("code_preview_edit", "programming",
                  "Preview (read-only) the diff an edit would apply to a workspace file.",
                  {"path": {"type": str, "required": True},
                   "old": {"type": str, "required": True},
                   "new": {"type": str, "required": False}},
                  _code_preview_edit)
    register_tool("code_write_file", "programming",
                  "Create, overwrite or append to one text file in the code workspace. "
                  "Python/JSON syntax is checked before saving.",
                  {"path": {"type": str, "required": True},
                   "content": {"type": str, "required": False},
                   "mode": {"type": str, "required": False}},
                  _code_write_file, consequential=True)
    register_tool("code_read_file", "programming",
                  "Read one text file from the code workspace (no binaries).",
                  {"path": {"type": str, "required": True}},
                  _code_read_file)
    register_tool("code_list_dir", "programming",
                  "List a folder of the code workspace.",
                  {"path": {"type": str, "required": False}},
                  _code_list_dir)
    register_tool("code_search", "programming",
                  "Regex search across workspace text files (skips node_modules, .git, venvs).",
                  {"query": {"type": str, "required": True},
                   "path": {"type": str, "required": False},
                   "extension": {"type": str, "required": False}},
                  _code_search_code)
    register_tool("code_apply_edit", "programming",
                  "Replace ONE exact text block in a workspace file (read the file first).",
                  {"path": {"type": str, "required": True},
                   "old": {"type": str, "required": True},
                   "new": {"type": str, "required": False}},
                  _code_apply_edit, consequential=True)
    register_tool("code_run_command", "programming",
                  "Run one whitelisted command (python, node, npm, pip, pytest) in the workspace.",
                  {"command": {"type": str, "required": True}},
                  _code_run_command, consequential=True)
    register_tool("code_delete_path", "programming",
                  "Delete a file or folder inside the code workspace.",
                  {"path": {"type": str, "required": True}},
                  _code_delete_path, consequential=True)
    register_tool("code_preview_build", "programming",
                  "Plan (read-only) which files KIRA would generate for a build request.",
                  {"request": {"type": str, "required": True},
                   "project": {"type": str, "required": False}},
                  _code_preview_build)
    register_tool("code_build", "programming",
                  "Generate a full custom project from one sentence: plan files, write them "
                  "with syntax checks and a self-fix round, then run the entry file.",
                  {"request": {"type": str, "required": True},
                   "project": {"type": str, "required": False}},
                  _code_build, consequential=True)
    register_tool("search_docs", "memory",
                  "Search the user's LOCAL documents (kira_docs/). Nothing leaves the machine.",
                  {"query": {"type": str, "required": True},
                   "limit": {"type": int, "required": False}},
                  _search_docs)
    register_tool("add_note", "memory",
                  "Save a note into the local documents folder (kira_docs/).",
                  {"path": {"type": str, "required": True},
                   "content": {"type": str, "required": False}},
                  _add_note, consequential=True)
    register_tool("list_documents", "memory",
                  "List the documents stored in kira_docs/.",
                  {}, _list_documents)
    register_tool("run_diagnostic", "research",
                  "Run one harmless health probe per agent and report green/red per system.",
                  {}, _run_diagnostic)
    register_tool("backup_memory", "memory",
                  "Create a rotating backup of the local memory database.",
                  {"keep": {"type": int, "required": False}},
                  _backup_memory, consequential=True)
    register_tool("list_backups", "memory",
                  "List the memory database backups.",
                  {}, _list_backups)
    register_tool("generate_plugin", "plugins",
                  "Generate a new KIRA plugin (plugins/<name>.py) from a description and load it.",
                  {"name": {"type": str, "required": True},
                   "description": {"type": str, "required": True}},
                  _generate_plugin, consequential=True)
    register_tool("morning_briefing", "research",
                  "Morning briefing: weather, pending tasks and upcoming holidays.",
                  {}, _morning_briefing)
