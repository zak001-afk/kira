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
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    agent: str
    description: str
    args: dict            # arg name -> {"type": type, "required": bool}
    handler: object
    consequential: bool = False


_REGISTRY = {}
_ACTIVITY = deque(maxlen=200)
_LOCK = threading.Lock()
_BUILTINS_READY = False


def register_tool(name, agent, description, args, handler, consequential=False):
    if agent not in AGENTS:
        raise ValueError(f"Unknown agent '{agent}'. Agents: {', '.join(AGENTS)}.")
    with _LOCK:
        _REGISTRY[str(name)] = ToolSpec(name=str(name), agent=agent, description=description,
                                        args=dict(args or {}), handler=handler,
                                        consequential=bool(consequential))


def unregister_tool(name):
    """Test/plugin hygiene; built-ins are simply re-registered on demand."""
    with _LOCK:
        _REGISTRY.pop(str(name), None)


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
        result = kira_tools.ToolResult(action=spec.name, ok=False, error_code="approval_required",
                                       error=f"'{spec.name}' needs your confirmation before it runs.",
                                       extra={"approval_id": approval_id, "agent": spec.agent})
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


# Keyless public information tools (kira_info): no API keys anywhere.

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
