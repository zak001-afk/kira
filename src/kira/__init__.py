"""KIRA — assistant IA local, code source (refactoring 2026-10).

Organisation du package ``kira`` (le code, sous ``src/``) :

- ``kira.core``          : fondations transverses (langue, parole, cache)
- ``kira.services``      : cerveau IA, planificateur, voix/TTS, agent vocal
- ``kira.data``          : donnees (memoire SQLite, taches, savoir partage)
- ``kira.api``           : pont REST same-origin pour l'interface
- ``kira.presentation``  : affichage (serveur UI, HUD tkinter, fenetres)
- ``kira.tools``         : actions utilisateur (commandes, ouvertures, code, agents…)
- ``kira.bin``           : petits outils en ligne de commande

La racine du depot reste le lieu des donnees et ressources (.env,
``kira_memory.db``, ``ui/``, ``assets/``, ``plugins/``, ``kira_config.json``…).
Les lanceurs a la racine importent ce package et conservent les commandes
historiques (``python main_window.py``, ``python dev.py``…).
"""

from kira import paths

__all__ = ["paths"]
