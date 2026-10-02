"""Compatibility launcher — the code now lives in ``src/kira/presentation/``.

``python main_window_tk.py`` keeps working exactly as before (HUD tkinter).
"""

import os as _os
import sys as _sys

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

from kira.presentation import main_window_tk as _real

if __name__ == "__main__":
    app = _real.KiraUI()
    app.mainloop()
