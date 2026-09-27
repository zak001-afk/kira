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
import threading

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


def run(name, raw_args=None, source="api"):
    """Validate, execute and record one tool call. Always returns a ToolResult."""
    ensure_builtins()
    spec = _REGISTRY.get(str(name))
    if spec is None:
        return kira_tools.ToolResult(action=str(name), ok=False, error_code="unknown_tool",
                                     error=f"No tool named '{name}' is registered.")
    kwargs, error = validate_args(spec, raw_args)
    if error:
        result = kira_tools.ToolResult(action=spec.name, ok=False,
                                       error=error, error_code="invalid_args")
    else:
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
