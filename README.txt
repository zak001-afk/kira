KIRA — AI COMMAND CENTER MED / MERGED 01

L'interface principale est la version francaise noir et or de MED.
Mettre a jour le projet complet, pas seulement main_window.py.

Dans votre dossier KIRA (PowerShell), avec votre environnement active :
    python -m pip install -r requirements.txt
    python main_window.py

Fermez l'ancienne fenetre avant de relancer. La console affiche [KIRA UI],
le Python utilise et le chemin du dossier ui/ pour identifier la bonne copie.

Conservez vos donnees locales : .env, .venv/, kira_config.json,
kira_memory.db, kira_files/ et vos plugins personnels.

Si vous lancez KIRA.exe, reconstruisez-le avec build_kira.bat.
Les reglages de voix et de microphone sont dans Parametres.
Le moteur comprend plusieurs langues ; les menus MED restent en francais.

Voir BRANCH_CONSOLIDATION.md pour la fusion des branches et les etapes manuelles
vers main + zakaria + arena/01a0df8a-kira-MED.
