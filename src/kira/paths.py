"""Racine du projet KIRA, calculee depuis l'emplacement du package.

Les modules du package vivent dans ``src/kira/...`` tandis que les donnees
et ressources (.env, ``kira_memory.db``, ``ui/``, ``assets/``, ``plugins/``,
``kira_config.json``, ``kira_workspace/``...) restent a la racine du depot.
Tout le code qui ancrerait un chemin sur son propre ``__file__`` utilise
desormais ``PROJECT_ROOT`` — le comportement reste identique quel que soit
l'endroit ou vit le package.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Mode fige (PyInstaller) : les donnees bundlees vivent dans _MEIPASS,
# comme du temps ou chaque module s'ancrait sur son propre __file__.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _BASE = Path(sys._MEIPASS)
else:
    # src/kira/paths.py -> parent = src/kira -> parent = src -> parent = racine
    _BASE = Path(__file__).resolve().parents[2]

PROJECT_ROOT = _BASE
ROOT = str(PROJECT_ROOT)


def root_path(*parts: str) -> Path:
    """Chemin absolu sous la racine du projet (fichiers de donnees, ui/...)."""
    return PROJECT_ROOT.joinpath(*parts)
