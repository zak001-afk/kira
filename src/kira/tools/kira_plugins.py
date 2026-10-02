"""
KIRA Plugin System — Extensible action registry.

Plugins can register new actions, commands, and capabilities without
modifying the core voice agent. Each plugin is a Python module in the
plugins/ directory that exposes a standard interface.

Resource-efficient: plugins are loaded lazily and cached.

Managed bridge (this module + kira_agents):
- Every action a plugin registers becomes a TOOL of the "plugins" agent in
  kira_agents' registry, so the planner, /api/agents and the approval gate
  see exactly one world: agents -> tools.
- A plugin may declare optional metadata at module level:
    PLUGIN_AGENT          — which specialist agent owns its tools
                            (default "plugins"; unknown ids fall back to it)
    PLUGIN_DESCRIPTIONS   — {action_name: description}
    PLUGIN_ARGS           — {action_name: {arg: {"type": t, "required": b}}}
    PLUGIN_CONSEQUENTIAL  — iterable of action names that change the outside
                            world (they then require user approval)
  Undeclared actions accept any arguments (forwarded as-is) and are treated
  as read-only.
- Unloading a plugin removes exactly the tools, parsers and middleware it
  contributed; nothing else is touched.
"""

import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from kira import paths

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────

# Registered action handlers: action_name -> handler_func
_action_handlers: Dict[str, Callable] = {}

# Registered command parsers: list of (pattern_or_func, handler)
_command_parsers: List[tuple] = []

# Registered chat middleware: list of callables that can augment chat context
_chat_middleware: List[Callable] = []

# Loaded plugin metadata
_loaded_plugins: Dict[str, dict] = {}

# Plugin directory
PLUGINS_DIR = os.path.join(paths.ROOT, "plugins")

# ─────────────────────────────────────────────
# Per-plugin bookkeeping (who registered what)
# ─────────────────────────────────────────────

_LOADING: Optional[str] = None  # plugin id whose module is currently executing

# plugin id -> {action_name: handler}
_PLUGIN_ACTIONS: Dict[str, Dict[str, Callable]] = {}
# plugin id -> [(matcher, handler), ...]
_PLUGIN_PARSERS: Dict[str, List[tuple]] = {}
# plugin id -> [middleware, ...]
_PLUGIN_MIDDLEWARE: Dict[str, List[Callable]] = {}


# ─────────────────────────────────────────────
# Public API for plugins
# ─────────────────────────────────────────────

def register_action(action_name: str, handler: Callable):
    """Register a handler for a new action type.

    The handler receives (action_data: dict) and returns bool (success).
    When called while a plugin module is loading (the normal case), the
    action is attributed to that plugin and bridged into the agent registry.
    """
    _action_handlers[action_name] = handler
    if _LOADING:
        _PLUGIN_ACTIONS.setdefault(_LOADING, {})[action_name] = handler
    logger.info("Plugin action registered: %s", action_name)


def register_command_parser(matcher: Callable, handler: Callable):
    """Register a command parser.

    matcher(text: str) -> bool  — returns True if this parser handles the text
    handler(text: str) -> dict  — returns an action dict
    """
    _command_parsers.append((matcher, handler))
    if _LOADING:
        _PLUGIN_PARSERS.setdefault(_LOADING, []).append((matcher, handler))


def register_chat_middleware(middleware: Callable):
    """Register chat middleware.

    middleware(messages: list, user_text: str) -> list
    Returns augmented messages list.
    """
    _chat_middleware.append(middleware)
    if _LOADING:
        _PLUGIN_MIDDLEWARE.setdefault(_LOADING, []).append(middleware)


def get_action_handler(action_name: str) -> Optional[Callable]:
    """Look up a registered action handler."""
    return _action_handlers.get(action_name)


def get_all_action_handlers() -> Dict[str, Callable]:
    """Return all registered action handlers."""
    return dict(_action_handlers)


def try_parse_command(text: str) -> Optional[dict]:
    """Try all registered command parsers. Returns first match or None."""
    for matcher, handler in _command_parsers:
        try:
            if matcher(text):
                return handler(text)
        except Exception:
            continue
    return None


def augment_chat_context(messages: list, user_text: str) -> list:
    """Run all chat middleware to augment the message context."""
    result = list(messages)
    for middleware in _chat_middleware:
        try:
            result = middleware(result, user_text)
        except Exception:
            continue
    return result


# ─────────────────────────────────────────────
# Plugin Loader
# ─────────────────────────────────────────────

def discover_plugins() -> List[str]:
    """Find all plugin modules in the plugins directory."""
    plugins = []
    plugins_path = Path(PLUGINS_DIR)

    if not plugins_path.is_dir():
        return plugins

    for py_file in sorted(plugins_path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        plugins.append(py_file.stem)

    return plugins


def load_plugin(name: str) -> bool:
    """Load a single plugin by name (idempotent)."""
    if name in _loaded_plugins:
        return True

    plugins_path = Path(PLUGINS_DIR)
    plugin_file = plugins_path / f"{name}.py"

    if not plugin_file.is_file():
        logger.warning("Plugin not found: %s", name)
        return False

    global _LOADING
    try:
        # Add plugins dir to path if not present
        if PLUGINS_DIR not in sys.path:
            sys.path.insert(0, PLUGINS_DIR)

        spec = importlib.util.spec_from_file_location(
            f"kira_plugins.{name}",
            str(plugin_file),
        )
        module = importlib.util.module_from_spec(spec)
        _LOADING = name
        try:
            spec.loader.exec_module(module)
        finally:
            _LOADING = None

        # Extract metadata
        meta = {
            "name": getattr(module, "PLUGIN_NAME", name),
            "version": getattr(module, "PLUGIN_VERSION", "1.0"),
            "description": getattr(module, "PLUGIN_DESCRIPTION", ""),
            "author": getattr(module, "PLUGIN_AUTHOR", ""),
        }

        _loaded_plugins[name] = meta
        logger.info("Plugin loaded: %s v%s", meta["name"], meta["version"])

        # Bridge the plugin's actions into the managed agent registry.
        _sync_plugin_tools(name, module)
        return True

    except Exception as exc:
        logger.error("Failed to load plugin %s: %s", name, exc)
        return False


def load_all_plugins():
    """Discover and load all available plugins."""
    for name in discover_plugins():
        load_plugin(name)


def unload_plugin(name: str) -> bool:
    """Unload a plugin: remove its registrations and its managed tools.

    The Python module itself cannot be fully unloaded; a reload therefore
    re-executes the file (load_plugin always execs), which is fine because
    every registration path here is ownership-tracked and idempotent.
    """
    if name not in _loaded_plugins:
        return False

    # Give the plugin a chance to clean up (best-effort, optional hook).
    try:
        plugins_path = Path(PLUGINS_DIR)
        plugin_file = plugins_path / f"{name}.py"
        # No re-execution: only call unload() if the module object is alive.
        module = sys.modules.get(f"kira_plugins.{name}")
        if module is not None and hasattr(module, "unload"):
            module.unload()
    except Exception as exc:
        logger.warning("Plugin %s unload() hook failed: %s", name, exc)

    # Remove command parsers contributed by this plugin.
    for pair in _PLUGIN_PARSERS.pop(name, []):
        try:
            _command_parsers.remove(pair)
        except ValueError:
            pass

    # Remove chat middleware contributed by this plugin.
    for middleware in _PLUGIN_MIDDLEWARE.pop(name, []):
        try:
            _chat_middleware.remove(middleware)
        except ValueError:
            pass

    # Remove managed tools contributed by this plugin.
    removed_tools = _agents_unregister(name)

    _loaded_plugins.pop(name, None)
    _PLUGIN_ACTIONS.pop(name, None)
    logger.info("Plugin unloaded: %s (tools removed: %s)", name, removed_tools)
    return True


def reload_plugin(name: str) -> bool:
    """Reload one plugin: unload, forget, then load fresh from disk."""
    unload_plugin(name)
    sys.modules.pop(f"kira_plugins.{name}", None)
    return load_plugin(name)


def reload_all_plugins():
    """Re-discover and reload every plugin (API: POST /api/plugins/reload)."""
    for name in discover_plugins():
        reload_plugin(name)
    return list_plugins()


def list_plugins() -> List[dict]:
    """List all loaded plugins with metadata and their contributed tools."""
    result = []
    for name, meta in _loaded_plugins.items():
        actions = sorted(_PLUGIN_ACTIONS.get(name, {}))
        tools = []
        try:
            import kira_agents
            tools = sorted(spec["name"] for spec in kira_agents.tool_catalog()
                           if spec.get("owner") == name)
        except Exception:
            pass
        result.append({"id": name, "actions": actions, "tools": tools, **meta})
    return result


# ─────────────────────────────────────────────
# Bridge into the agent registry (kira_agents)
# ─────────────────────────────────────────────

def _agents_unregister(owner: str) -> List[str]:
    """Remove the managed tools of one plugin; empty list if unavailable."""
    try:
        import kira_agents
        return kira_agents.unregister_tools_of(owner)
    except Exception:
        return []


def _wrap_action_handler(handler: Callable) -> Callable:
    """Adapt the plugin contract (one ``action_data`` dict) to the tool
    contract (typed keyword arguments)."""
    def wrapper(**kwargs):
        return handler(dict(kwargs))
    wrapper.__name__ = getattr(handler, "__name__", "plugin_action")
    wrapper.__doc__ = getattr(handler, "__doc__", "")
    wrapper.consequential = getattr(handler, "consequential", False)
    return wrapper


def _sync_plugin_tools(name: str, module: object):
    """Expose the plugin's registered actions as tools of the agent registry.

    Rules:
    - Owner is the plugin id; reloads unregister the old tools first.
    - Agent defaults to "plugins"; PLUGIN_AGENT must name a real agent.
    - PLUGIN_ARGS gives a strict schema; without it the tool accepts and
      forwards any arguments (typical simple plugins take one dict).
    - PLUGIN_CONSEQUENTIAL marks outward-changing actions (approval gate).
    - Name collisions with tools owned by someone else get the plugin id
      as a prefix, so a plugin can never shadow a built-in tool.
    """
    actions = _PLUGIN_ACTIONS.get(name, {})
    if not actions:
        return

    try:
        import kira_agents
    except ImportError:
        logger.warning("kira_agents unavailable; plugin %s stays action-only", name)
        return

    # A stale load (crashed mid-way, or actions changed) starts clean.
    _agents_unregister(name)

    plugin_agent = str(getattr(module, "PLUGIN_AGENT", "") or "plugins")
    if plugin_agent not in kira_agents.AGENTS:
        logger.warning("Plugin %s asked for unknown agent '%s'; using 'plugins'.",
                       name, plugin_agent)
        plugin_agent = "plugins"

    descriptions = getattr(module, "PLUGIN_DESCRIPTIONS", {}) or {}
    args_schemas = getattr(module, "PLUGIN_ARGS", {}) or {}
    consequential_names = set(getattr(module, "PLUGIN_CONSEQUENTIAL", ()) or ())

    plugin_title = str(_loaded_plugins.get(name, {}).get("name", name))
    registered: List[str] = []

    for action_name, handler in actions.items():
        tool_name = action_name
        existing = kira_agents.tool_catalog()
        taken = {spec["name"] for spec in existing}
        if tool_name in taken:
            tool_name = f"{name}_{action_name}"
            logger.info("Tool '%s' already registered; plugin %s gets '%s'.",
                        action_name, name, tool_name)

        description = str(descriptions.get(action_name) or
                          getattr(handler, "__doc__", "") or
                          f"Plugin action '{action_name}' from {plugin_title}.").strip()

        raw_args = args_schemas.get(action_name)
        has_schema = isinstance(raw_args, dict) and len(raw_args) > 0
        args_schema = dict(raw_args) if has_schema else {}

        try:
            kira_agents.register_tool(
                tool_name, plugin_agent, description, args_schema,
                _wrap_action_handler(handler),
                consequential=(action_name in consequential_names
                               or bool(getattr(handler, "consequential", False))),
                accepts_extra=not has_schema,
                owner=name,
            )
            registered.append(tool_name)
        except Exception as exc:
            logger.error("Plugin %s tool '%s' failed to register: %s",
                         name, action_name, exc)

    logger.info("Plugin %s contributes tools: %s", name, registered)


# ─────────────────────────────────────────────
# Built-in plugin: System Monitor
# ─────────────────────────────────────────────

def _builtin_system_monitor():
    """Register built-in system monitoring actions."""

    def handle_disk_info(action_data: dict) -> bool:
        try:
            import psutil
            usage = psutil.disk_usage("/")
            return True
        except Exception:
            return False

    def handle_network_info(action_data: dict) -> bool:
        try:
            import psutil
            counters = psutil.net_io_counters()
            return True
        except Exception:
            return False

    def handle_process_list(action_data: dict) -> bool:
        try:
            import psutil
            procs = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
                try:
                    info = proc.info
                    procs.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return True
        except Exception:
            return False

    register_action("disk_info", handle_disk_info)
    register_action("network_info", handle_network_info)
    register_action("process_list", handle_process_list)


def _builtin_calculator():
    """Register built-in calculator action."""

    def handle_calculate(action_data: dict) -> bool:
        expression = str(action_data.get("expression", ""))
        if not expression:
            return False

        # Safe evaluation — only math operations
        import math
        allowed_names = {
            "abs": abs, "round": round, "min": min, "max": max,
            "sum": sum, "pow": pow, "int": int, "float": float,
            "pi": math.pi, "e": math.e, "sqrt": math.sqrt,
            "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "log": math.log, "log10": math.log10, "ceil": math.ceil,
            "floor": math.floor,
        }

        try:
            # Block dangerous operations
            if any(bad in expression for bad in ["import", "exec", "eval", "open", "__"]):
                return False

            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return True
        except Exception:
            return False

    register_action("calculate", handle_calculate)


def register_builtins():
    """Register all built-in plugin actions."""
    _builtin_system_monitor()
    _builtin_calculator()


# Auto-register builtins on import (ownerless: not attributable to a plugin
# file, so they stay in the legacy action registry only).
register_builtins()
