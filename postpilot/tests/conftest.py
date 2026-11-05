"""Isole les tests : ils n'écrivent JAMAIS dans les vraies données de l'utilisateur.

Redirige les chemins de socia.config vers un dossier temporaire avant tout
import des modules qui lisent/écrivent au niveau module.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from postpilot import config  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="socia-tests-"))
config.DATA = _TMP / "data"
config.SESSIONS = config.DATA / "sessions"
config.MEDIA = config.DATA / "media"
config.GENERATED = config.DATA / "generated"
config.GEMINI_DIR = config.DATA / "gemini"
config.GENERATED = config.DATA / "generated"
config.SHOTS = config.DATA / "shots"
config.WEB = ROOT / "web"
config.ACCOUNTS_FILE = config.DATA / "accounts.json"
config.TASKS_FILE = config.DATA / "tasks.json"
config.LINKS_FILE = config.DATA / "links.json"
config.JOURNAL_FILE = config.DATA / "journal.json"
config.SETTINGS_FILE = config.DATA / "settings.json"
config.LINK_ERRORS_FILE = config.DATA / "link_errors.json"
config.BLACKLIST_FILE = config.DATA / "blacklist.json"
config.ensure_dirs()
