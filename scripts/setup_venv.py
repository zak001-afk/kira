"""Create or repair KIRA's ``.venv``.

Why this exists: ``.venv/pyvenv.cfg`` stores the absolute path of the
interpreter that built the environment. Clone the repository onto another
machine, or remove that Python install, and ``.venv\\Scripts\\python.exe`` has
no base interpreter to hand off to — it refuses to start with a dialog like::

    did not find executable at 'C:\\Users\\someone\\...\\pythonw.exe'

Run this script with ANY working Python (the one inside a broken venv will
not work, so use ``python`` / ``py`` from PATH)::

    python scripts/setup_venv.py            # repair if possible, else rebuild
    python scripts/setup_venv.py --rebuild  # force a clean environment
    python scripts/setup_venv.py --no-install   # skip pip installs

Exit code 0 means ``.venv`` starts and the requirements are installed.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
CFG = VENV / "pyvenv.cfg"
VENV_PY = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
REQUIREMENTS = [ROOT / "requirements.txt", ROOT / "requirements-dev.txt"]

MINOR = f"{sys.version_info.major}.{sys.version_info.minor}"
VERSION = f"{MINOR}.{sys.version_info.micro}"
# The interpreter a repaired venv must point at: the base of the one running
# this script (CPython spells it `_base_executable`; PyPy uses `base_executable`).
_BASE = getattr(sys, "_base_executable", None) or getattr(sys, "base_executable", None)
_BASE = Path(_BASE) if _BASE else Path(sys.executable)
if VENV in _BASE.parents:  # this script was started from inside .venv
    _BASE = Path(sys.base_prefix) / ("python.exe" if sys.platform == "win32" else "bin/python")
BASE_EXECUTABLE = _BASE


def say(message=""):
    print(message, flush=True)


def venv_works(timeout=60):
    """True when the venv launcher starts and reports its own prefix."""
    if not VENV_PY.exists():
        return False
    try:
        done = subprocess.run(
            [str(VENV_PY), "-c", "import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)"],
            capture_output=True, timeout=timeout, cwd=str(ROOT),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def read_cfg():
    """Return the pyvenv.cfg keys, or {} when the file is missing/unreadable."""
    try:
        lines = CFG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    cfg = {}
    for line in lines:
        key, sep, value = line.partition("=")
        if sep:
            cfg[key.strip()] = value.strip()
    return cfg


def write_cfg(cfg):
    CFG.write_text(
        "".join(f"{key} = {value}\n" for key, value in cfg.items()),
        encoding="utf-8",
    )


def repoint():
    """Point an intact-but-orphaned venv at the interpreter running this script.

    Cheap first attempt: the packages in site-packages stay untouched. Only
    valid when the interpreter we are running is the SAME major.minor as the
    venv was built with, otherwise the binary extensions do not match.
    """
    cfg = read_cfg()
    if not cfg:
        return False, "pyvenv.cfg is missing"
    built = cfg.get("version", "")
    if not built.startswith(MINOR + ".") and built != MINOR:
        return False, f"built for Python {built or 'unknown'}, this is {VERSION}"
    cfg["home"] = str(Path(BASE_EXECUTABLE).parent)
    cfg["executable"] = str(BASE_EXECUTABLE)
    cfg["version"] = VERSION
    write_cfg(cfg)
    return True, f"repointed at {BASE_EXECUTABLE}"


def rebuild():
    """Delete the broken environment and create a fresh one."""
    if VENV.exists():
        shutil.rmtree(VENV, ignore_errors=True)
        if VENV.exists():
            return False, f"could not delete {VENV}"
    done = subprocess.run([sys.executable, "-m", "venv", str(VENV)],
                          capture_output=True, text=True, cwd=str(ROOT))
    if done.returncode != 0:
        return False, (done.stderr or done.stdout or "venv creation failed").strip()
    return True, f"created with {sys.executable}"


def install_requirements():
    """Install runtime + development requirements into the venv."""
    existing = [path for path in REQUIREMENTS if path.exists()]
    if not existing:
        return False, f"no requirements file found next to this script ({REQUIREMENTS[0]})"
    args = [str(VENV_PY), "-m", "pip", "install", "--disable-pip-version-check"]
    for path in existing:
        args += ["-r", str(path)]
    done = subprocess.run(args, cwd=str(ROOT))
    if done.returncode != 0:
        return False, "pip install failed"
    return True, ""


def main():
    parser = argparse.ArgumentParser(description="Create or repair .venv for KIRA.")
    parser.add_argument("--rebuild", action="store_true",
                        help="delete and recreate the environment, even if it works")
    parser.add_argument("--no-install", action="store_true",
                        help="skip the pip installs (repair/build only)")
    args = parser.parse_args()

    say(f"KIRA venv setup — base interpreter: {BASE_EXECUTABLE} ({VERSION})")

    if Path(sys.prefix).resolve() == VENV.resolve() and not venv_works():
        say("ERROR: this Python itself lives in the broken .venv.")
        say("Run it with your normal Python instead, e.g.  python scripts/setup_venv.py")
        return 1

    if args.rebuild:
        ok, detail = rebuild()
        say(f"[1] force rebuild: {detail}")
        if not ok:
            say(f"ERROR: {detail}")
            return 1
    elif venv_works():
        say("[1] existing .venv starts — keeping it")
    else:
        say("[1] .venv is broken (its Python is gone from this machine)")
        ok, detail = repoint()
        say(f"    try repoint: {detail}")
        if not (ok and venv_works()):
            say("    falling back to a clean rebuild")
            ok, detail = rebuild()
            if not ok:
                say(f"ERROR: {detail}")
                return 1
            if not venv_works():
                say(f"ERROR: the new environment still does not start ({detail})")
                return 1

    if not args.no_install:
        say("[2] installing requirements (this can take a few minutes)...")
        ok, detail = install_requirements()
        if not ok:
            say(f"ERROR: {detail}")
            return 1

    if not venv_works():
        say("ERROR: .venv still does not start")
        return 1

    say("[done] OK — .venv is ready")
    say(f"    start KIRA : {VENV_PY} main_window.py")
    say(f"    tests      : {VENV_PY} -m unittest discover -s tests -p \"test_*.py\"")
    say(f"    lint       : {VENV_PY} -m ruff check .")
    return 0


if __name__ == "__main__":
    sys.exit(main())
