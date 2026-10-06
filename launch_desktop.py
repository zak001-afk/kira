"""Desktop entry point — launches KIRA from the sources in this folder.

Legacy no-console alternative to ``launch_kira.bat`` (the desktop shortcut's
normal target). Because it runs the .py sources directly (no frozen exe),
any change made to the files in this folder is picked up on the next
launch.

- No console window: stdout/stderr are appended to kira_launch.log.
- ``input()`` is neutralised so error paths cannot hang on an invisible
  prompt.
- Takes the single-instance lock (``single_instance.py``) like every other
  launcher: a refusal is journalled and the process exits with code 3.
"""

import builtins
import os
import runpy
import sys
import traceback

import single_instance

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Journal instead of a console: append with a timestamped header per run.
_log = open(
    os.path.join(ROOT, "kira_launch.log"),
    "a",
    encoding="utf-8",
    errors="replace",
)


class _LogWriter:
    def __init__(self, original):
        self._original = original

    def write(self, data):
        try:
            _log.write(data)
            _log.flush()
        except Exception:
            pass
        # keep the original (pythonw dummy) stream happy too
        try:
            return self._original.write(data)
        except Exception:
            return 0

    def flush(self):
        try:
            _log.flush()
        except Exception:
            pass
        try:
            return self._original.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._original, name)


_log.write("\n===== KIRA desktop launch %s =====\n" % __import__("datetime").datetime.now().isoformat(timespec="seconds"))
_log.flush()

sys.stdout = _LogWriter(sys.stdout)
sys.stderr = _LogWriter(sys.stderr)


def _no_input(prompt=""):
    """No console: never block on an invisible prompt."""
    print(prompt)
    return ""


builtins.input = _no_input

try:
    if __name__ == "__main__":
        # Journal du refus plutôt que popup : la console n'existe pas ici.
        lock_error = single_instance.acquire(force="--force" in sys.argv[1:])
        if lock_error:
            print(f"[KIRA] {lock_error}")
            _log.write(f"\n[KIRA] {lock_error}\n")
            _log.flush()
            raise SystemExit(single_instance.LOCK_REFUSED_EXIT_CODE)
    runpy.run_path(os.path.join(ROOT, "main_window.py"), run_name="__main__")
except SystemExit:
    pass
except BaseException:
    traceback.print_exc()
    _log.write("\n[KIRA] launcher terminated with an error — see above.\n")
    _log.flush()
    raise SystemExit(1) from None
finally:
    single_instance.release()
