"""Compatibility launcher — the code now lives in ``src/kira/presentation/``.

``python main_window.py`` keeps working exactly as before (native window),
with one addition: the single-instance lock (``single_instance.py``)
guarantees that launching KIRA while it already runs prints a clear
message and exits, instead of a second window fighting the first for
ports 8765/8766. ``--force`` bypasses the guard (deliberate dev copy).
"""

import os as _os
import sys as _sys

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

if __name__ == "__main__":
    import single_instance as _si

    _error = _si.acquire(force="--force" in _sys.argv[1:])
    if _error:
        print(f"[KIRA] {_error}")
        _sys.exit(_si.LOCK_REFUSED_EXIT_CODE)

import kira.presentation.main_window as _real

if __name__ == "__main__":
    try:
        _real.main()
    finally:
        _si.release()
