"""Compatibility shim — the code now lives in ``src/kira/tools/``.

Kept at the repository root so every historical entry point keeps working
(``import kira_agents``, launch commands, tests, PyInstaller). The shim installs
the real package module in ``sys.modules`` in its place: the imported object
IS the real module (same identity), so patching and caching behave exactly
as before the restructuring.
"""

import os as _os
import sys as _sys

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

_real = "kira.tools.kira_agents"

if _real in _sys.modules:
    _module = _sys.modules[_real]
else:
    from kira.tools import kira_agents as _module  # PyInstaller-friendly

_sys.modules[__name__] = _module
