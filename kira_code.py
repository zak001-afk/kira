"""KIRA's coding hands: create full projects and edit code, on request.

The programming agent's tools live here. The design copies the house rules:

- Tools RETURN data (plain dicts the registry wraps in ToolResult). They never
  speak and never touch the UI.
- Every write path is jailed inside ONE workspace root. The root is resolved
  once per call from KIRA_CODE_DIR (absolute path allowed) or defaults to
  ``kira_workspace/`` next to the project — a per-request job directory, kept
  out of version control alongside kira_files/.
- Failures are structured ({ok: False, error, error_code}), never tracebacks.
- Which tools need the user's confirmation before running is decided in
  kira_agents (consequential=True); this module just does the work.
- Binaries and vendored directories are skipped by search and tree listings so
  results stay small and truthful.

Lazy imports everywhere; nothing here runs at import time.
"""

from pathlib import Path
import os
import re
import shutil
import subprocess
import sys

# ── Workspace jail ───────────────────────────────────────────────────────────

_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".idea",
              ".vscode", "build", "dist", ".pytest_cache", ".mypy_cache"}
_TEXT_EXTENSIONS = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json",
                    ".html", ".css", ".md", ".txt", ".yml", ".yaml", ".toml",
                    ".ini", ".cfg", ".sh", ".bat", ".ps1", ".sql", ".xml",
                    ".csv", ".env", ".gitignore", ".rs", ".go", ".java", ".c",
                    ".h", ".cpp", ".hpp", ".cs", ".php", ".rb"}
_MAX_TEXT_BYTES = 512 * 1024          # refuse to read monsters wholesale
_MAX_SEARCH_MATCHES = 40
_MAX_RUN_SECONDS = 30
_MAX_RUN_OUTPUT = 16 * 1024


def workspace_root():
    """One sandbox root for every write. KIRA_CODE_DIR (absolute) wins."""
    configured = str(os.environ.get("KIRA_CODE_DIR", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parent / "kira_workspace").resolve()


def resolve_path(relative, must_exist=False):
    """relative -> absolute path inside the workspace, or a structured error.

    Refuses absolute paths, Windows drives and any '..' escape. Returns
    (Path, None) on success or (None, {ok, error, error_code}).
    """
    relative = str(relative or "").strip().strip("\"'").replace("\\", "/")
    if not relative or relative in {".", "/"}:
        return None, {"ok": False, "error": "A path inside the workspace is required.",
                      "error_code": "path_required"}
    if len(relative) > 2 and relative[1] == ":":
        return None, {"ok": False, "error": f"Absolute drive paths are not allowed: {relative}",
                      "error_code": "path_outside_workspace"}
    if relative.startswith("/") or relative.startswith("~"):
        return None, {"ok": False, "error": f"Absolute paths are not allowed: {relative}",
                      "error_code": "path_outside_workspace"}
    candidate = (workspace_root() / relative).resolve()
    root = workspace_root()
    if candidate != root and root not in candidate.parents:
        return None, {"ok": False, "error": f"Path escapes the workspace: {relative}",
                      "error_code": "path_outside_workspace"}
    if must_exist and not candidate.exists():
        return None, {"ok": False, "error": f"Not found in the workspace: {relative}",
                      "error_code": "not_found"}
    return candidate, None


def _is_text_file(path):
    if path.suffix.lower() in _TEXT_EXTENSIONS:
        return True
    if path.name.lower() in {".env", ".gitignore"}:
        return True
    try:
        with open(path, "rb") as handle:
            return b"\x00" not in handle.read(1024)
    except OSError:
        return False


def _entry_info(path, relative_to):
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {"path": path.relative_to(relative_to).as_posix(),
            "size": size, "dir": path.is_dir()}


# ── Tools ────────────────────────────────────────────────────────────────────

def scaffold_project(name, template="", content=""):
    """Create kira_workspace/<name>/ with a starter skeleton, return data."""
    name = str(name or "").strip().strip("\"'/\\")
    if not name or name in {".", ".."} or any(part in name for part in ("/", "\\", ":")):
        return {"ok": False, "error": "A simple project name is required.",
                "error_code": "invalid_name"}
    root = workspace_root()
    project = (root / name).resolve()
    if project != root and root not in project.parents:
        return {"ok": False, "error": f"Path escapes the workspace: {name}",
                "error_code": "path_outside_workspace"}
    if project.exists():
        return {"ok": False, "error": f"'{name}' already exists in the workspace.",
                "error_code": "already_exists"}
    try:
        project.mkdir(parents=True)
        files = {}
        files["README.md"] = f"# {name}\n"
        files[".gitignore"] = "__pycache__/\n*.py[cod]\n.venv/\nnode_modules/\n.env\n"
        if template == "python":
            files["main.py"] = ('def main():\n    print("Hello from %s!")\n\n\n'
                                'if __name__ == "__main__":\n    main()\n' % name)
        elif template == "web":
            files["index.html"] = ("<!DOCTYPE html>\n<html>\n<head>\n"
                                   '  <meta charset="utf-8">\n  <title>%s</title>\n'
                                   '  <link rel="stylesheet" href="style.css">\n'
                                   "</head>\n<body>\n  <h1>%s</h1>\n"
                                   '  <script src="script.js"></script>\n</body>\n</html>\n'
                                   % (name, name))
            files["style.css"] = "body { font-family: sans-serif; margin: 2rem; }\n"
            files["script.js"] = 'console.log("%s ready");\n' % name
        elif template == "node":
            files["package.json"] = ('{\n  "name": "%s",\n  "version": "1.0.0",\n'
                                     '  "main": "index.js",\n  "scripts": {"start": "node index.js"}\n}\n'
                                     % name)
            files["index.js"] = 'console.log("%s ready");\n' % name
        elif template == "empty":
            files = {}
        else:
            # Default: a runnable Python starter, useful without more setup.
            files["main.py"] = ('def main():\n    print("Hello from %s!")\n\n\n'
                                'if __name__ == "__main__":\n    main()\n' % name)
        for relative, text in files.items():
            target = (project / relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        created = sorted(f"{name}/{relative}" for relative in files)
        return {"ok": True, "project": name, "template": template or "python",
                "path": str(project), "created": created,
                "response": f"Project '{name}' created ({template or 'python'}): "
                            + ", ".join(created)}
    except OSError as error:
        return {"ok": False, "error": str(error), "error_code": "scaffold_failed"}


def write_file(path, content=""):
    """Create or overwrite one text file inside the workspace."""
    target, failure = resolve_path(path)
    if failure:
        return failure
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content or ""), encoding="utf-8")
        return {"ok": True, "path": target.relative_to(workspace_root()).as_posix(),
                "bytes": target.stat().st_size,
                "response": f"Written: {target.name} ({target.stat().st_size} bytes)"}
    except OSError as error:
        return {"ok": False, "error": str(error), "error_code": "write_failed"}


def read_file(path):
    """Read a workspace text file. Binary and oversized files are refused."""
    target, failure = resolve_path(path, must_exist=True)
    if failure:
        return failure
    if target.is_dir():
        return {"ok": False, "error": f"'{path}' is a directory; use list_dir.",
                "error_code": "is_directory"}
    if not _is_text_file(target):
        return {"ok": False, "error": f"'{path}' looks binary; not reading it.",
                "error_code": "binary_file"}
    try:
        if target.stat().st_size > _MAX_TEXT_BYTES:
            return {"ok": False, "error": f"'{path}' is larger than 512 KB.",
                    "error_code": "file_too_large"}
        return {"ok": True, "path": target.relative_to(workspace_root()).as_posix(),
                "content": target.read_text(encoding="utf-8", errors="replace"),
                "response": target.read_text(encoding="utf-8", errors="replace")}
    except (OSError, UnicodeError) as error:
        return {"ok": False, "error": str(error), "error_code": "read_failed"}


def list_dir(path=""):
    """List one workspace directory (files first, directories second)."""
    target, failure = resolve_path(path or "")
    if failure:
        return failure
    if not target.exists():
        return {"ok": False, "error": f"Not found in the workspace: {path}",
                "error_code": "not_found"}
    if not target.is_dir():
        return {"ok": False, "error": f"'{path}' is a file.", "error_code": "not_a_directory"}
    try:
        entries = [_entry_info(child, target) for child in sorted(target.iterdir())]
        entries.sort(key=lambda entry: (entry["dir"], entry["path"].lower()))
        return {"ok": True, "path": target.relative_to(workspace_root()).as_posix(),
                "entries": entries, "count": len(entries),
                "response": f"{len(entries)} entries in {path or 'the workspace root'}"}
    except OSError as error:
        return {"ok": False, "error": str(error), "error_code": "list_failed"}


def search_code(query, path="", extension=""):
    """Regex search over workspace text files (gitignore-style dirs skipped)."""
    query = str(query or "").strip()
    if not query:
        return {"ok": False, "error": "A search pattern is required.",
                "error_code": "query_required"}
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error as error:
        return {"ok": False, "error": f"Invalid pattern: {error}", "error_code": "invalid_pattern"}
    base, failure = resolve_path(path or "")
    if failure:
        return failure
    if not base.exists() or not base.is_dir():
        return {"ok": False, "error": f"Not found in the workspace: {path}",
                "error_code": "not_found"}
    suffix = str(extension or "").strip().lower()
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    matches, scanned = [], 0
    for current, directories, names in os.walk(base):
        directories[:] = [d for d in directories if d not in _SKIP_DIRS]
        for name in names:
            candidate = Path(current) / name
            if suffix and candidate.suffix.lower() != suffix:
                continue
            if not _is_text_file(candidate):
                continue
            scanned += 1
            try:
                if candidate.stat().st_size > _MAX_TEXT_BYTES:
                    continue
                for line_number, line in enumerate(
                        candidate.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if pattern.search(line):
                        matches.append({"file": candidate.relative_to(base).as_posix(),
                                        "line": line_number, "text": line.strip()[:200]})
                        if len(matches) >= _MAX_SEARCH_MATCHES:
                            break
            except OSError:
                continue
            if len(matches) >= _MAX_SEARCH_MATCHES:
                break
        if len(matches) >= _MAX_SEARCH_MATCHES:
            break
    return {"ok": True, "pattern": query, "files_scanned": scanned,
            "matches": matches, "count": len(matches),
            "response": f"{len(matches)} match(es) for '{query}' across {scanned} files"}


def apply_edit(path, old, new=""):
    """Replace ONE exact block (first occurrence) inside a workspace file."""
    target, failure = resolve_path(path, must_exist=True)
    if failure:
        return failure
    old_text = str(old or "")
    if not old_text:
        return {"ok": False, "error": "'old' (the exact text to replace) is required.",
                "error_code": "old_required"}
    try:
        current = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return {"ok": False, "error": str(error), "error_code": "read_failed"}
    if old_text not in current:
        return {"ok": False,
                "error": "The exact text to replace was not found. Read the file first, "
                         "then retry with an exact block.",
                "error_code": "old_not_found"}
    if current.count(old_text) > 1:
        return {"ok": False,
                "error": "That text appears several times; include more surrounding "
                         "lines so only one block matches.",
                "error_code": "ambiguous_match"}
    updated = current.replace(old_text, str(new or ""), 1)
    try:
        target.write_text(updated, encoding="utf-8")
    except OSError as error:
        return {"ok": False, "error": str(error), "error_code": "write_failed"}
    return {"ok": True, "path": target.relative_to(workspace_root()).as_posix(),
            "response": f"Edit applied to {target.name}."}


def run_command(command):
    """Run ONE whitelisted command inside a workspace folder, capture output."""
    command = str(command or "").strip().strip("\"'")
    if not command:
        return {"ok": False, "error": "A command is required.", "error_code": "command_required"}
    parts = command.split()
    executable = Path(parts[0]).name.lower()
    if executable not in {"python", "python3", "py", "node", "npm", "pip", "pytest"}:
        return {"ok": False,
                "error": f"'{parts[0]}' is not allowed. Allowed: python, node, npm, pip, pytest.",
                "error_code": "command_not_allowed"}
    # Target directory: a bare second token is the script (file) or the
    # working folder (dir). Files run from the workspace root so their
    # workspace-relative path in the command still resolves.
    relative = ""
    if executable in {"python", "python3", "py", "node", "npm", "pip", "pytest"} and len(parts) > 1 and not parts[1].startswith("-"):
        relative = parts[1]
    target, failure = (resolve_path(relative) if relative else (workspace_root(), None))
    if failure:
        return failure
    if target.is_dir():
        cwd = target
    elif target.is_file():
        cwd = workspace_root()
    else:
        return {"ok": False, "error": f"Target not found in the workspace: {relative}",
                "error_code": "not_found"}
    try:
        completed = subprocess.run(
            command, shell=True, cwd=str(cwd), capture_output=True, text=True,
            timeout=_MAX_RUN_SECONDS,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        return {"ok": completed.returncode == 0, "command": command,
                "cwd": cwd.relative_to(workspace_root()).as_posix() or ".",
                "exit_code": completed.returncode,
                "output": output[:_MAX_RUN_OUTPUT],
                "response": (output[:_MAX_RUN_OUTPUT] or f"(exit {completed.returncode})")}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timed out after {_MAX_RUN_SECONDS}s.",
                "error_code": "command_timeout"}
    except OSError as error:
        return {"ok": False, "error": str(error), "error_code": "run_failed"}


def delete_path(path):
    """Delete a file or a whole folder inside the workspace (gated)."""
    target, failure = resolve_path(path)
    if failure:
        return failure
    if target == workspace_root():
        return {"ok": False, "error": "Refusing to delete the workspace root.",
                "error_code": "workspace_root_protected"}
    if not target.exists():
        return {"ok": False, "error": f"Not found in the workspace: {path}",
                "error_code": "not_found"}
    try:
        if target.is_dir():
            shutil.rmtree(target)
            removed = f"Folder '{path}' deleted."
        else:
            target.unlink()
            removed = f"File '{path}' deleted."
        return {"ok": True, "path": path, "response": removed}
    except OSError as error:
        return {"ok": False, "error": str(error), "error_code": "delete_failed"}
