KIRA — HOLOGRAPHIC COCKPIT 03 / LANGUAGES 01

IMPORTANT : mettre a jour le projet complet, pas seulement main_window.py.
La nouvelle interface est dans ui/ (HTML, CSS, JavaScript, images et polices),
et son serveur commun est kira_ui.py.

Pour lancer la copie source depuis votre dossier KIRA (PowerShell) :
    .\.venv\Scripts\python.exe main_window.py

Le titre de la nouvelle fenetre est KIRA — HOLOGRAPHIC COCKPIT 03 / LANGUAGES 01.
La console affiche aussi [KIRA UI], le Python utilise et le chemin du dossier ui/.
Si ces indications sont absentes, vous lancez encore une autre/ancienne copie.
Fermez l'ancienne fenetre avant de relancer.

Les changements dans Arena ou une branche GitHub ne mettent pas automatiquement
votre dossier local a jour. Recuperez la branche qui contient la refonte.
Un git pull sur main ne recupere pas une pull request non fusionnee.

Conservez vos donnees locales :
- .venv/
- kira_config.json
- kira_memory.db et les fichiers de donnees associes
- kira_files/ et vos plugins personnels

Le lancement Python n'exige pas de reconstruire un executable.
Si vous lancez KIRA.exe, reconstruisez-le avec build_kira.bat apres la mise a jour.
Voir README.md et LAUNCH_MODES.md pour les autres modes de lancement.

Animation de la bouche :
- Activez la voix et LIPS: ON dans SETTINGS.
- MOTION: ON autorise les mouvements si Windows demande une animation reduite.
- DIAGNOSTICS > TEST LIPS : demonstration visuelle sans audio.
- DIAGNOSTICS > TEST VOICE : exemple Hello / Bonjour avec la vraie synthese vocale.
La synchronisation est une animation 2D approximative, pas une video humaine.

Langues (LANGUAGES 01) :
- Installez le detecteur dans le meme environnement :
    .\.venv\Scripts\python.exe -m pip install langid
- SETTINGS > Interface language > Francais : traduit les menus.
- Parametres > Langue des reponses et de la voix > Automatique : suit la question.
- « Reponds-moi en francais » fixe aussi le francais pour les reponses suivantes.
- Le microphone du navigateur ecoute une seule langue a la fois : choisissez sa
  langue d'ecoute si vous changez de langue a l'oral. Auto suit la conversation.
- La qualite multilingue depend du modele Ollama et des voix disponibles ; aucune
  promesse de prise en charge universelle. Pas de repli vocal anglais silencieux.
- Les reglages natifs persistent dans %LOCALAPPDATA%/KIRA/WebViewProfile.
