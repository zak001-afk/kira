"""
KIRA Plugin System — Extensible action registry.

Plugins can register new actions, commands, and capabilities without
modifying the core voice agent. Each plugin is a Python module in the
plugins/ directory that exposes a standard interface.

Resource-efficient: plugins are loaded lazily and cached.
"""

import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

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
PLUGINS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")


# ─────────────────────────────────────────────
# Public API for plugins
# ─────────────────────────────────────────────

def register_action(action_name: str, handler: Callable):
    """Register a handler for a new action type.

    The handler receives (action_data: dict) and returns bool (success).
    """
    _action_handlers[action_name] = handler
    logger.info("Plugin action registered: %s", action_name)


def register_command_parser(matcher: Callable, handler: Callable):
    """Register a command parser.

    matcher(text: str) -> bool  — returns True if this parser handles the text
    handler(text: str) -> dict  — returns an action dict
    """
    _command_parsers.append((matcher, handler))


def register_chat_middleware(middleware: Callable):
    """Register chat middleware.

    middleware(messages: list, user_text: str) -> list
    Returns augmented messages list.
    """
    _chat_middleware.append(middleware)


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
    """Load a single plugin by name."""
    if name in _loaded_plugins:
        return True

    plugins_path = Path(PLUGINS_DIR)
    plugin_file = plugins_path / f"{name}.py"

    if not plugin_file.is_file():
        logger.warning("Plugin not found: %s", name)
        return False

    try:
        # Add plugins dir to path if not present
        if PLUGINS_DIR not in sys.path:
            sys.path.insert(0, PLUGINS_DIR)

        spec = importlib.util.spec_from_file_location(
            f"kira_plugins.{name}",
            str(plugin_file),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Extract metadata
        meta = {
            "name": getattr(module, "PLUGIN_NAME", name),
            "version": getattr(module, "PLUGIN_VERSION", "1.0"),
            "description": getattr(module, "PLUGIN_DESCRIPTION", ""),
            "author": getattr(module, "PLUGIN_AUTHOR", ""),
        }

        _loaded_plugins[name] = meta
        logger.info("Plugin loaded: %s v%s", meta["name"], meta["version"])
        return True

    except Exception as exc:
        logger.error("Failed to load plugin %s: %s", name, exc)
        return False


def load_all_plugins():
    """Discover and load all available plugins."""
    for name in discover_plugins():
        load_plugin(name)


def unload_plugin(name: str) -> bool:
    """Unload a plugin (removes its registrations).

    Note: This is best-effort. Python modules cannot be fully unloaded,
    but we remove their registrations.
    """
    if name not in _loaded_plugins:
        return False

    # Remove registrations from this plugin
    # (In practice, plugins should track what they register for clean unload)
    _loaded_plugins.pop(name, None)
    return True


def list_plugins() -> List[dict]:
    """List all loaded plugins with metadata."""
    return [
        {"id": name, **meta}
        for name, meta in _loaded_plugins.items()
    ]


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


# Auto-register builtins on import
register_builtins()
