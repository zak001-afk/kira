"""Project builder: from an idea to a tested project on disk.

The flow KIRA runs when you say *"build me a project that …"*:

1. **Plan** — the local model turns the idea into a strict JSON spec
   (name, language, files, test command).
2. **Generate** — each planned file is written by the model, one call per
   file, with the plan as context.
3. **Write** — files land in ``projects_dir`` through hardened path joining:
   absolute paths, ``..`` escapes and symlinked parents are refused.
4. **Test** — the plan's test command runs **for real**, with the project's
   interpreter, inside the project directory, with a timeout.
5. **Repair** — if tests fail, the failing output goes back to the model and
   the loop repeats, at most ``max_attempts`` times.
6. **Report** — the summary states exactly what happened. KIRA never claims
   success unless the tests actually passed.

Safety: test commands are restricted to a allow-list of test runners and are
executed without a shell, so a hallucinated ``rm -rf`` plan cannot run.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_TIMEOUT = 180
MAX_ATTEMPTS = 3
MAX_FILES = 12
MAX_CONTENT_CHARS = 20_000

# Only these executables may be run as a project's test command.
ALLOWED_RUNNERS = {
    "pytest", "python", "python3", "py", "node", "npm", "npx", "cargo",
    "go", "dotnet", "deno", "bun",
}

_PLAN_SYSTEM_PROMPT = """You are KIRA's project architect. The user describes a \
project idea; you answer with EXACTLY ONE JSON object, no prose:

{
  "name": "short-kebab-case-name",
  "description": "one sentence",
  "language": "python",
  "files": ["main.py", "tests/test_main.py"],
  "test_command": "python -m pytest -q",
  "run_command": "python main.py"
}

Rules:
- 2 to 8 files. Every file path is relative and uses forward slashes.
- Always include at least one test file and a working test_command.
- Prefer Python with pytest unless the idea clearly needs something else.
- The project must be runnable and fully testable offline with no API keys.
- Keep each file small, focused and complete. No placeholders or TODOs.
"""

_CODE_SYSTEM_PROMPT = """You are KIRA's implementation engine. You receive a \
project plan and ONE file path to write. Answer with the file's full contents \
only — no markdown fences, no commentary, no explanation.

Requirements:
- Complete, runnable code. No TODO comments, no placeholders, no ellipses.
- Standard library only unless the plan says otherwise.
- Include proper docstrings. Code must pass its own tests.
"""


@dataclass
class Plan:
    name: str
    description: str = ""
    language: str = "python"
    files: list = field(default_factory=list)
    test_command: str = "python -m pytest -q"
    run_command: str = ""


@dataclass
class BuildResult:
    ok: bool
    project_dir: str
    plan: "Plan | None" = None
    attempts: int = 0
    test_output: str = ""
    files_written: list = field(default_factory=list)
    error: str = ""

    def summary(self) -> str:
        """A truthful, human-readable report."""
        if self.plan is None:
            return self.error or "I could not plan that project."
        lines = [
            f"Project '{self.plan.name}' — {'tests passing' if self.ok else 'TESTS FAILING'}",
            f"location: {self.project_dir}",
            f"files: {len(self.files_written)}",
            f"attempts: {self.attempts}",
        ]
        if self.error:
            lines.append(f"error: {self.error}")
        if self.test_output and not self.ok:
            tail = self.test_output.strip().splitlines()[-12:]
            lines.append("last test output:")
            lines.extend(tail)
        return "\n".join(lines)


# ── naming and paths ─────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """A filesystem-safe project folder name."""
    text = str(name or "").strip().lower()
    text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:48] or "kira-project"


def safe_relative(path: str) -> "str | None":
    """Validate a planned file path; None when it must be refused."""
    raw = str(path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("~"):
        return None
    if re.match(r"^[a-zA-Z]:", raw):  # Windows drive letter
        return None
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    cleaned = "/".join(parts)
    if len(cleaned) > 180:
        return None
    return cleaned


def safe_target(root: "str | Path", relative: str) -> "Path | None":
    """Resolve ``relative`` inside ``root``, refusing any escape."""
    cleaned = safe_relative(relative)
    if cleaned is None:
        return None
    root_path = Path(root).resolve()
    target = (root_path / cleaned).resolve()
    if root_path != target and root_path not in target.parents:
        return None
    return target


# ── model calls (injectable) ─────────────────────────────────────────────────

def _extract_json(text: str):
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return None


def _ask(chat_fn, system_prompt: str, user_prompt: str) -> str:
    response = chat_fn(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        {"temperature": 0.2, "num_ctx": 8192},
    )
    if isinstance(response, dict):
        message = response.get("message") or {}
        return str(message.get("content") or "")
    return str(response or "")


def strip_code_fence(text: str) -> str:
    """Remove markdown fences a model may wrap code in."""
    body = str(text or "").strip()
    if not body.startswith("```"):
        return body
    lines = body.splitlines()
    lines = lines[1:]
    while lines and lines[-1].strip().startswith("```"):
        lines.pop()
    if lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines).strip("\n")


def parse_plan(raw_text: str, idea: str = "") -> "Plan | None":
    """Turn the model's answer into a validated Plan."""
    data = _extract_json(raw_text)
    if not isinstance(data, dict):
        return None

    files = []
    for entry in data.get("files") or []:
        cleaned = safe_relative(entry)
        if cleaned and cleaned not in files:
            files.append(cleaned)
    files = files[:MAX_FILES]
    if not files:
        return None

    name = str(data.get("name") or "").strip() or slugify(idea)
    return Plan(
        name=slugify(name),
        description=str(data.get("description") or "").strip(),
        language=str(data.get("language") or "python").strip().lower(),
        files=files,
        test_command=str(data.get("test_command") or "").strip()
        or "python -m pytest -q",
        run_command=str(data.get("run_command") or "").strip(),
    )


def plan_project(idea: str, chat_fn) -> "Plan | None":
    return parse_plan(_ask(chat_fn, _PLAN_SYSTEM_PROMPT, idea), idea)


def generate_file(plan: Plan, relative: str, chat_fn, feedback: str = "") -> str:
    """Ask the model for one file's contents ("" when it returns nothing)."""
    prompt = (
        f"Project: {plan.name} — {plan.description}\n"
        f"Language: {plan.language}\n"
        f"Files in the project: {', '.join(plan.files)}\n\n"
        f"Write this file now: {relative}"
    )
    if feedback:
        prompt += f"\n\nThe previous attempt failed its tests:\n{feedback[:2000]}"
    content = strip_code_fence(_ask(chat_fn, _CODE_SYSTEM_PROMPT, prompt))
    if not content.strip():
        return ""
    return content[:MAX_CONTENT_CHARS]


# ── writing and running ──────────────────────────────────────────────────────

def write_files(root: "str | Path", files: dict) -> list:
    """Write ``{relative_path: contents}`` inside root. Returns written paths."""
    written = []
    for relative, content in files.items():
        target = safe_target(root, relative)
        if target is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        written.append(relative)
    return written


def parse_command(command: str) -> "list[str] | None":
    """Split and allow-list a test command. None when it must be refused."""
    try:
        parts = shlex.split(str(command or ""), posix=False)
    except ValueError:
        return None
    parts = [part.strip('"') for part in parts if part.strip()]
    if not parts:
        return None
    executable = Path(parts[0]).name.lower()
    if executable.endswith(".exe"):
        executable = executable[:-4]
    if executable not in ALLOWED_RUNNERS:
        return None
    return parts


def resolve_command(parts: list) -> list:
    """Run python through the interpreter that is running KIRA."""
    first = parts[0].lower()
    if first in {"python", "python3", "py"}:
        return [sys.executable] + parts[1:]
    return parts


def clear_bytecode_caches(project_dir) -> int:
    """Delete ``__pycache__`` folders inside a project.

    A repair can produce a file with the same byte size written in the same
    second as the previous version. CPython's timestamp-based .pyc check then
    accepts the stale cache and the fix appears to do nothing — so every test
    run starts from a clean cache.
    """
    removed = 0
    for cache in Path(project_dir).rglob("__pycache__"):
        if any(part in {".venv", "venv", "node_modules"} for part in cache.parts):
            continue
        shutil.rmtree(cache, ignore_errors=True)
        removed += 1
    return removed


def run_tests(project_dir, command: str, timeout: int = DEFAULT_TIMEOUT,
              runner=None):
    """Run the project's test command. Returns (ok, output)."""
    parts = parse_command(command)
    if parts is None:
        return False, (
            f"Refused to run '{command}': only test runners are allowed "
            f"({', '.join(sorted(ALLOWED_RUNNERS))})."
        )
    argv = resolve_command(parts)
    execute = runner or subprocess.run
    clear_bytecode_caches(project_dir)
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        result = execute(
            argv,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return False, f"Test command timed out after {timeout}s: {command}"
    except (OSError, ValueError) as exc:
        return False, f"Could not run the tests: {exc}"
    output = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
    return result.returncode == 0, output


_IGNORED_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "node_modules", "target", ".venv", "venv", "dist", "build",
}


def _is_ignored(path: Path) -> bool:
    return any(part in _IGNORED_DIRS for part in path.parts)


def _read_tree(project_dir: Path) -> dict:
    """Best-effort snapshot of the project's text files."""
    snapshot = {}
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file() or _is_ignored(path):
            continue
        try:
            snapshot[str(path.relative_to(project_dir)).replace("\\", "/")] = (
                path.read_text(encoding="utf-8", errors="ignore")
            )
        except OSError:
            continue
    return snapshot


def diagnose_test_failure(output: str) -> str:
    """Turn a raw failure into one honest, actionable sentence."""
    text = str(output or "").lower()
    if "no module named pytest" in text or "no module named 'pytest'" in text:
        return "pytest isn't installed for KIRA's Python — run: pip install pytest"
    match = re.search(r"no module named '?([\w\.]+)'?", text)
    if match:
        return f"the generated code imports '{match.group(1)}', which isn't installed"
    if "timed out" in text:
        return "the test command timed out"
    if "syntaxerror" in text or "syntax error" in text:
        return "the generated code has a syntax error"
    if "error: no test" in text or "no tests ran" in text:
        return "the test command found no tests to run"
    return ""


def ensure_python_path_helper(project_dir, plan: Plan) -> str:
    """Add a minimal conftest.py so tests can import the project's modules.

    Generated test files commonly do ``import calc`` while pytest only puts
    the test file's own folder on ``sys.path`` — a very predictable failure.
    This writes a three-line bootstrap when the plan doesn't provide one.
    """
    if plan.language != "python":
        return ""
    if not any(str(name).endswith(".py") for name in plan.files):
        return ""
    if any(Path(str(name)).name == "conftest.py" for name in plan.files):
        return ""
    target = Path(project_dir) / "conftest.py"
    if target.exists():
        return ""
    target.write_text(
        '"""KIRA: make the project importable from its tests."""\n'
        "import sys\n"
        "from pathlib import Path\n\n"
        "ROOT = Path(__file__).resolve().parent\n"
        "if str(ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(ROOT))\n",
        encoding="utf-8",
    )
    return "conftest.py"


def patch_files(project_dir, plan: Plan, chat_fn, feedback: str) -> bool:
    """Ask the model to correct each existing file, given the failure output.

    Returns True when at least one file actually changed. This is the repair
    strategy for both fresh builds and existing projects: the model sees its
    own code plus the exact error instead of regenerating from scratch.
    """
    changed = False
    for relative in plan.files[:MAX_FILES]:
        target = safe_target(project_dir, relative)
        if target is None or not target.exists():
            continue
        existing = target.read_text(encoding="utf-8", errors="ignore")
        prompt = (
            f"Project: {plan.name}\n"
            f"File: {relative}\n\n"
            f"Current contents:\n{existing[:8000]}\n\n"
            f"The tests fail with:\n{feedback[:2000]}\n\n"
            "Return the complete corrected file. If it is already correct, "
            "return it unchanged."
        )
        fixed = strip_code_fence(_ask(chat_fn, _CODE_SYSTEM_PROMPT, prompt))
        if fixed and fixed != existing:
            target.write_text(fixed[:MAX_CONTENT_CHARS], encoding="utf-8")
            changed = True
    return changed


def build_project(
    idea: str,
    chat_fn,
    projects_dir=".",
    max_attempts: int = MAX_ATTEMPTS,
    timeout: int = DEFAULT_TIMEOUT,
    runner=None,
    on_progress=None,
    slug: str = "",
) -> BuildResult:
    """Idea → planned, generated, written and *tested* project."""
    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    root = Path(projects_dir).expanduser()
    idea = str(idea or "").strip()
    if not idea:
        return BuildResult(False, str(root), error="I need an idea to work with.")

    progress("planning the project...")
    plan = plan_project(idea, chat_fn)
    if plan is None:
        return BuildResult(
            False,
            str(root),
            error="I could not turn that idea into a plan. Is Ollama running?",
        )

    project_dir = root / (slugify(slug) if slug else plan.name)
    project_dir.mkdir(parents=True, exist_ok=True)
    progress(f"scaffolding '{plan.name}' in {project_dir}")

    feedback = ""
    test_output = ""
    attempts = 0
    ok = False

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        if attempt == 1:
            progress(f"writing {len(plan.files)} file(s) from scratch")
            contents = {}
            empty = []
            for relative in plan.files:
                body = generate_file(plan, relative, chat_fn, feedback)
                if body:
                    contents[relative] = body
                else:
                    # never destroy existing code because a model call came
                    # back empty — a silent failure must not delete a file
                    empty.append(relative)
            if empty:
                progress(
                    f"model returned nothing for {len(empty)} file(s): "
                    f"{', '.join(empty)} — keeping previous versions"
                )
            write_files(project_dir, contents)
            if not contents:
                return BuildResult(
                    False,
                    str(project_dir),
                    plan,
                    attempt,
                    error="the model returned no code at all",
                )
            helper = ensure_python_path_helper(project_dir, plan)
            if helper:
                progress(f"added {helper} so tests can import the project")
        else:
            # from here on, repair: show the model its own code and the exact
            # failure. Regenerating blindly throws away working files.
            progress("asking the model to correct the failing files")
            if not patch_files(project_dir, plan, chat_fn, feedback):
                progress("the model made no further changes — stopping")
                break

        progress(f"running tests: {plan.test_command}")
        ok, test_output = run_tests(project_dir, plan.test_command, timeout, runner)
        if ok:
            break
        progress("tests failed — repairing from the output")
        feedback = test_output

    written = sorted(_read_tree(project_dir).keys())
    return BuildResult(
        ok=ok,
        project_dir=str(project_dir),
        plan=plan,
        attempts=attempts,
        test_output=test_output,
        files_written=written,
        error="" if ok else diagnose_test_failure(test_output),
    )


def create_project(idea: str, chat_fn, projects_dir=".", **kwargs) -> BuildResult:
    """Alias with a friendlier name for callers."""
    return build_project(idea, chat_fn, projects_dir=projects_dir, **kwargs)


# ── command parsing helpers ──────────────────────────────────────────────────

_BUILD_PREFIXES = (
    "build me a project", "build me a", "build a project", "build an app",
    "create a project", "create an app", "make a project", "make me a project",
    "new project", "start a project", "scaffold a project",
    "crée un projet", "crée-moi un projet", "créer un projet",
    "fais un projet", "nouveau projet",
    "أنشئ مشروعا", "أنشئ مشروعاً", "اعمل مشروع", "مشروع جديد",
)

_FIX_PREFIXES = (
    "fix the project", "fix my project", "fix the tests",
    "répare le projet", "corrige le projet", "أصلح المشروع",
)


def extract_idea(command: str) -> str:
    """Pull the idea out of 'build me a project that ...'."""
    text = re.sub(r"\s+", " ", str(command or "").strip())
    lower = text.lower()
    for prefix in _BUILD_PREFIXES:
        if lower.startswith(prefix.lower()):
            remainder = text[len(prefix) :].strip(" ,.:;-")
            for lead in ("that ", "which ", "to ", "for ", "qui ", "pour ", "لـ"):
                if remainder.lower().startswith(lead):
                    remainder = remainder[len(lead) :].strip()
                    break
            return remainder
    return ""


def is_build_command(command: str) -> bool:
    text = str(command or "").strip().lower()
    return any(text.startswith(prefix.lower()) for prefix in _BUILD_PREFIXES)


def is_fix_command(command: str) -> bool:
    text = str(command or "").strip().lower()
    return any(text.startswith(prefix.lower()) for prefix in _FIX_PREFIXES)


def latest_project(projects_dir=".") -> "Path | None":
    """The most recently modified project folder (for 'fix the project')."""
    root = Path(projects_dir).expanduser()
    if not root.exists():
        return None
    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def repair_project(project_dir, chat_fn, timeout: int = DEFAULT_TIMEOUT,
                   max_attempts: int = 2, runner=None, on_progress=None) -> BuildResult:
    """Re-run tests on an existing project and let the model fix what fails."""
    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    project_dir = Path(project_dir)
    if not project_dir.exists():
        return BuildResult(
            False, str(project_dir), error="I could not find that project."
        )

    snapshot = _read_tree(project_dir)
    test_command = _guess_test_command(snapshot)
    ok, test_output = run_tests(project_dir, test_command, timeout, runner)
    attempts = 1
    if ok:
        return BuildResult(
            True,
            str(project_dir),
            Plan(
                name=project_dir.name,
                files=sorted(snapshot.keys()),
                test_command=test_command,
            ),
            attempts,
            test_output,
            sorted(snapshot.keys()),
        )

    plan = Plan(
        name=project_dir.name,
        description=f"existing project at {project_dir}",
        files=sorted(snapshot.keys()) or ["main.py"],
        test_command=test_command,
    )
    # an existing project may lack the import bootstrap too — without it the
    # model would be asked to fix an import error that is not its fault
    if ensure_python_path_helper(project_dir, plan):
        progress("added conftest.py so tests can import the project")
        ok, test_output = run_tests(project_dir, test_command, timeout, runner)
        if ok:
            return BuildResult(
                True,
                str(project_dir),
                plan,
                1,
                test_output,
                sorted(_read_tree(project_dir).keys()),
            )
    feedback = test_output
    for attempt in range(2, max_attempts + 2):
        attempts = attempt
        progress("asking the model for a fix...")
        if not patch_files(project_dir, plan, chat_fn, feedback):
            break
        ok, test_output = run_tests(project_dir, test_command, timeout, runner)
        if ok:
            break
        feedback = test_output

    return BuildResult(
        ok,
        str(project_dir),
        plan,
        attempts,
        test_output,
        sorted(_read_tree(project_dir).keys()),
    )


def _guess_test_command(snapshot: dict) -> str:
    names = {name.lower() for name in snapshot}
    if any(name.startswith("test") or "/test" in f"/{name}" for name in names):
        if any(name.endswith(".py") for name in names):
            return "python -m pytest -q"
    if "package.json" in names:
        return "npm test"
    if "cargo.toml" in names:
        return "cargo test"
    return "python -m pytest -q"


def describe_plan(plan: Plan) -> str:
    files = ", ".join(plan.files[:6])
    extra = "" if len(plan.files) <= 6 else f" (+{len(plan.files) - 6} more)"
    return f"{plan.name}: {plan.description or 'a small project'} — {files}{extra}"


def new_project_banner(plan: Plan) -> str:
    return (
        f"Sir, I've planned '{plan.name}': {plan.description or 'a small project'}. "
        f"{len(plan.files)} files, tested with '{plan.test_command}'."
    )


def timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
