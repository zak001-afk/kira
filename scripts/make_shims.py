"""Genere les shims de compatibilite a la racine du depot.

Apres le deplacement du code dans ``src/kira/``, les anciens chemins
d'import (``import kira_ai``) et les anciens lanceurs (``python
main_window.py``) doivent continuer de fonctionner : commandes de
lancement, tests, CI, PyInstaller et habitudes utilisateur.

Les shims de modules s'auto-remplacent dans ``sys.modules`` par le vrai
module du package : l'objet importe via le shim EST le module reel
(same identity), donc ``patch.object(kira_ai, ...)`` dans les tests
modifie bien le module utilise par le reste de l'application.

Regenerer : ``python scripts/make_shims.py``.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SHIMS = {
    # core
    "kira_language": "core", "kira_speech": "core", "kira_cache": "core",
    # services
    "kira_ai": "services", "kira_planner": "services", "kira_tts": "services",
    "kira_voice_agent": "services",
    # data
    "kira_memory": "data", "kira_tasks": "data", "kira_shared_memory": "data",
    # api
    "kira_api": "api",
    # presentation
    "kira_ui": "presentation", "kira_theme": "presentation",
    # tools
    "kira_commands": "tools", "kira_open": "tools", "kira_code": "tools",
    "kira_docs": "tools", "kira_health": "tools", "kira_ops": "tools",
    "kira_agents": "tools", "kira_info": "tools", "kira_web": "tools",
    "kira_scheduler": "tools", "kira_plugins": "tools", "kira_tools": "tools",
    "kira_build": "tools",
}

SHIM_TEMPLATE = '''"""Compatibility shim — the code now lives in ``src/kira/{sub}/``.

Kept at the repository root so every historical entry point keeps working
(``import {name}``, launch commands, tests, PyInstaller). The shim installs
the real package module in ``sys.modules`` in its place: the imported object
IS the real module (same identity), so patching and caching behave exactly
as before the restructuring.
"""

import os as _os
import sys as _sys

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

_real = "kira.{sub}.{name}"

if _real in _sys.modules:
    _module = _sys.modules[_real]
else:
    from kira.{sub} import {name} as _module  # PyInstaller-friendly

_sys.modules[__name__] = _module
'''

LAUNCHER_BOOTSTRAP = '''
import os as _os
import sys as _sys

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)
'''

LAUNCHERS = {
    "main_window.py": '''"""Compatibility launcher — the code now lives in ``src/kira/presentation/``.

``python main_window.py`` keeps working exactly as before (native window).
"""\n\nimport kira.presentation.main_window as _real\n\nif __name__ == \"__main__\":\n    _real.main()\n''',
    "launch_web.py": '''"""Compatibility launcher — the code now lives in ``src/kira/presentation/``.

``python launch_web.py`` keeps working exactly as before (browser mode).
"""\n\nimport kira.presentation.launch_web as _real\n\nif __name__ == \"__main__\":\n    _real.main()\n''',
    "main_window_tk.py": '''"""Compatibility launcher — the code now lives in ``src/kira/presentation/``.

``python main_window_tk.py`` keeps working exactly as before (HUD tkinter).
"""\n\nfrom kira.presentation import main_window_tk as _real\n\nif __name__ == \"__main__\":\n    app = _real.KiraUI()\n    app.mainloop()\n''',
}


def main():
    for name, sub in sorted(SHIMS.items()):
        (ROOT / f"{name}.py").write_text(SHIM_TEMPLATE.format(sub=sub, name=name), encoding="utf-8")
        print(f"shim  {name}.py -> kira.{sub}.{name}")
    for name, content in LAUNCHERS.items():
        # Insere le bootstrap sys.path apres la docstring, avant l'import.
        for marker in ( '"""\n\nimport ', '"""\n\nfrom ' ):
            if marker in content:
                content = content.replace(marker, '"""\n' + LAUNCHER_BOOTSTRAP + '\n' + marker[5:], 1)
                break
        (ROOT / name).write_text(content, encoding="utf-8")
        print(f"lanceur {name}")
    print(f"\n{len(SHIMS)} shims + {len(LAUNCHERS)} lanceurs generes")


if __name__ == "__main__":
    main()
