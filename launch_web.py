"""Compatibility launcher — the code now lives in ``src/kira/presentation/``.

``python launch_web.py`` keeps working exactly as before (browser mode).
"""

import os as _os
import sys as _sys

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import kira.presentation.launch_web as _real

if __name__ == "__main__":
    _real.main()
