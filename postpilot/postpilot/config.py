"""Configuration et chemins de PostPilot (100 % local, sur le disque E:)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SESSIONS = DATA / "sessions"      # profils navigateur persistants (cookies = connexions)
MEDIA = DATA / "media"            # vidéos / images à publier
GENERATED = DATA / "generated"    # photos Gemini générées (une par post)
GEMINI_DIR = DATA / "gemini"      # connexion Google OAuth (client_secret + jetons)
SHOTS = DATA / "shots"            # captures pendant le travail
WEB = ROOT / "web"

# Fichier Excel de référence des groupes & pages (lu et complété à chaque import)
EXCEL_LINKS_FILE = Path(r"E:\groupe fb\groupes_facebook_tunisie_vente_pub.xlsx")

ACCOUNTS_FILE = DATA / "accounts.json"
TASKS_FILE = DATA / "tasks.json"
LINKS_FILE = DATA / "links.json"      # liens enregistrés (pages & groupes)
LINK_ERRORS_FILE = DATA / "link_errors.json"  # liens en difficulté / erreur
BLACKLIST_FILE = DATA / "blacklist.json"      # liens bannis (jamais réimportés)
JOURNAL_FILE = DATA / "journal.json"
SETTINGS_FILE = DATA / "settings.json"

NAME = "PostPilot"
HOST = "127.0.0.1"
PORT = 8790

# Plateformes gérées
PLATFORMS = ("facebook", "instagram", "tiktok")

HOME_URLS = {
    "facebook": "https://www.facebook.com/",
    "instagram": "https://www.instagram.com/",
    "tiktok": "https://www.tiktok.com/",
}

PLATFORM_LABELS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
}


def ensure_dirs() -> None:
    """Crée l'arborescence de données si elle n'existe pas."""
    for d in (DATA, SESSIONS, MEDIA, GENERATED, SHOTS, GEMINI_DIR):
        d.mkdir(parents=True, exist_ok=True)
    for f in (ACCOUNTS_FILE, TASKS_FILE, LINKS_FILE, JOURNAL_FILE,
              SETTINGS_FILE, LINK_ERRORS_FILE, BLACKLIST_FILE):
        if not f.exists():
            f.write_text("[]\n" if f is not JOURNAL_FILE else "[]\n", encoding="utf-8")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
