"""
KIRA Plugin: File Manager

Provides file system operations: create, read, search, and manage files.
"""

import os
import shutil
import glob
from pathlib import Path

PLUGIN_NAME = "File Manager"
PLUGIN_VERSION = "1.1"
PLUGIN_DESCRIPTION = "Create, read, search, and manage files and folders."
PLUGIN_AUTHOR = "KIRA"

# Managed-registry metadata: where the tools live, their schemas, and which
# ones change the outside world (delete_file requires the user's approval).
PLUGIN_AGENT = "windows"
PLUGIN_DESCRIPTIONS = {
    "create_file": "Create a new text file (optionally with content) in the KIRA files directory.",
    "read_file": "Read a file from the KIRA files directory.",
    "search_files": "Search files by glob pattern in the KIRA files directory.",
    "list_files": "List files in the KIRA files directory.",
    "delete_file": "Delete a file or folder from the KIRA files directory.",
}
PLUGIN_ARGS = {
    "create_file": {"target": {"type": str, "required": True},
                    "text": {"type": str, "required": False}},
    "read_file": {"target": {"type": str, "required": True}},
    "search_files": {"query": {"type": str, "required": False}},
    "list_files": {},
    "delete_file": {"target": {"type": str, "required": True}},
}
PLUGIN_CONSEQUENTIAL = ("delete_file",)

# Home directory for KIRA-managed files
KIRA_FILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kira_files")


def _ensure_files_dir():
    os.makedirs(KIRA_FILES_DIR, exist_ok=True)
    return KIRA_FILES_DIR


def create_file(action_data: dict) -> bool:
    """Create a new file with optional content."""
    name = str(action_data.get("target", "")).strip()
    content = str(action_data.get("text", "")).strip()

    if not name:
        return False

    base = _ensure_files_dir()
    filepath = os.path.join(base, name)

    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False


def read_file(action_data: dict) -> bool:
    """Read a file from the KIRA files directory."""
    name = str(action_data.get("target", "")).strip()
    if not name:
        return False

    filepath = os.path.join(KIRA_FILES_DIR, name)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            f.read()
        return True
    except Exception:
        return False


def search_files(action_data: dict) -> bool:
    """Search for files by pattern in KIRA files directory."""
    pattern = str(action_data.get("query", "*")).strip()
    base = _ensure_files_dir()

    try:
        results = glob.glob(os.path.join(base, "**", pattern), recursive=True)
        return len(results) > 0
    except Exception:
        return False


def list_files(action_data: dict) -> bool:
    """List files in KIRA files directory."""
    base = _ensure_files_dir()
    try:
        os.listdir(base)
        return True
    except Exception:
        return False


def delete_file(action_data: dict) -> bool:
    """Delete a file from KIRA files directory."""
    name = str(action_data.get("target", "")).strip()
    if not name:
        return False

    filepath = os.path.join(KIRA_FILES_DIR, name)
    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
            return True
        elif os.path.isdir(filepath):
            shutil.rmtree(filepath)
            return True
    except Exception:
        pass
    return False


# ─────────────────────────────────────────────
# Plugin Registration (called by kira_plugins)
# ─────────────────────────────────────────────

def register(kira_plugins_module):
    """Register this plugin's actions with the KIRA plugin system."""
    kira_plugins_module.register_action("create_file", create_file)
    kira_plugins_module.register_action("read_file", read_file)
    kira_plugins_module.register_action("search_files", search_files)
    kira_plugins_module.register_action("list_files", list_files)
    kira_plugins_module.register_action("delete_file", delete_file)


# Auto-register if plugin system is available
try:
    import kira_plugins
    register(kira_plugins)
except ImportError:
    pass
