"""Parseur de commandes en langage naturel français.

Exemples compris :
  « Publie ce post toutes les 1 heure sur mon compte Facebook »
  « publie une story instagram toutes les 30 minutes »
  « poste cette vidéo tiktok toutes les 2h »
  « partage dans mes groupes facebook toutes les 4 heures »
"""
from __future__ import annotations

import re
from typing import Any

PLATFORM_WORDS = [
    (r"\b(fb|facebook|face book|facebok)\b", "facebook"),
    (r"\b(instagram|insta|instegram)\b", "instagram"),
    (r"\b(tiktok|tik tok|ticktock)\b", "tiktok"),
]

KIND_WORDS = [
    (r"\bstor(y|ies)\b|\bstories\b", "story"),
    (r"\bvid[eé]o?s?\b|\breels?\b|\breel\b", "video"),
    (r"\bpost(e|s|ing)?\b|\bpublication\b|\bmessage\b", "post"),
]

_UNIT_SECONDS = {
    "seconde": 1, "secondes": 1, "sec": 1, "s": 1,
    "minute": 60, "minutes": 60, "min": 60,
    "heure": 3600, "heures": 3600, "h": 3600,
    "jour": 86400, "jours": 86400, "j": 86400,
    "semaine": 604800, "semaines": 604800,
}

_INTERVAL_RE = re.compile(
    r"""
    (?:tous\s+les|toutes\s+les|chaque|par|every|un\s+par|une\s+par)?
    \s*
    (?P<num>\d+(?:[.,]\d+)?)\s*
    (?P<unit>secondes?|secs?|s|minutes?|mins?|heure[s]?|h|jours?|j|semaines?)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_TARGET_RE = re.compile(
    r"groupe[s]?\b|groupes?\s+facebook|dans\s+mes\s+groupes", re.IGNORECASE)

# chemin de fichier image/vidéo cité dans la commande
# ex. « publie ce post avec E:\photos\miel.jpg toutes les 1 heure »
_MEDIA_RE = re.compile(
    r"(?P<path>[A-Za-z]:[\\/][^\s\"'«»]+\.(?:png|jpe?g|gif|webp|bmp|avif|heic|"
    r"mp4|mov|webm|mkv|avi))|"
    r"(?P<rel>\b[\w\-./]+\.(?:png|jpe?g|gif|webp|bmp|avif|heic|mp4|mov|webm|mkv|avi))\b",
    re.IGNORECASE)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def detect_platform(text: str) -> str | None:
    low = _norm(text)
    for pattern, name in PLATFORM_WORDS:
        if re.search(pattern, low, re.IGNORECASE):
            return name
    return None


def detect_kind(text: str) -> str | None:
    low = _norm(text)
    for pattern, name in KIND_WORDS:
        if re.search(pattern, low, re.IGNORECASE):
            return name
    return None


def detect_interval(text: str) -> int | None:
    """Retourne l'intervalle en secondes, ou None."""
    low = _norm(text)
    m = _INTERVAL_RE.search(low)
    if not m:
        # « toutes les heures » sans chiffre
        if re.search(r"\btoutes\s+les\s+heures?\b|\bchaque\s+heure\b", low):
            return 3600
        if re.search(r"\btoutes\s+les\s+minutes?\b|\bchaque\s+minute\b", low):
            return 60
        if re.search(r"\btous\s+les\s+jours?\b|\bchaque\s+jour\b", low):
            return 86400
        return None
    num = float(m.group("num").replace(",", "."))
    unit = m.group("unit").lower()
    seconds = _UNIT_SECONDS.get(unit)
    if not seconds:
        return None
    total = int(num * seconds)
    return total if total > 0 else None


def detect_target(text: str) -> str:
    """« compte » (défaut) ou « groupes »."""
    low = _norm(text)
    if _TARGET_RE.search(low):
        return "groups"
    return "profile"


def detect_media(text: str) -> str:
    r"""Chemin d'une photo/vidéo cité dans la commande (« avec E:\…\p.jpg »)."""
    m = _MEDIA_RE.search(text or "")
    if not m:
        return ""
    return m.group("path") or m.group("rel") or ""


def detect_content(text: str) -> str:
    """Extrait le contenu du post si donné entre guillemets ou après « : »."""
    low = text or ""
    m = re.search(r"[\"“«'](.+?)[\"”»']", low, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:poste|publie|partage)\s*[:\-=]\s*(.+)$", low,
                  re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def parse_command(text: str) -> dict[str, Any]:
    """Analyse une commande utilisateur et retourne une tâche semi-remplie.

    Ne lève jamais d'exception : les champs manquants sont None.
    """
    raw = text or ""
    interval = detect_interval(raw)
    return {
        "raw": raw,
        "platform": detect_platform(raw),
        "kind": detect_kind(raw) or "post",
        "interval_seconds": interval,
        "target": detect_target(raw),
        "content": detect_content(raw),
        "media": detect_media(raw),
        "valid": detect_platform(raw) is not None and interval is not None,
    }


def human_interval(seconds: int) -> str:
    """60 → « toutes les 1 minute », 3600 → « toutes les 1 heure »,
    43200 → « toutes les 12 heures », 86400 → « toutes les 24 heures »."""
    if seconds <= 0:
        return "immédiatement"
    if seconds == 86400:
        return "toutes les 24 heures"       # = 1 jour : on dit 24 h
    for limit, unit in ((86400, "jour"), (3600, "heure"), (60, "minute")):
        if seconds % limit == 0:
            n = seconds // limit
            plural = "" if n == 1 else ("s" if unit == "minute" else "s")
            if unit == "heure" and n == 1:
                return "toutes les 1 heure"
            return f"toutes les {n} {unit}{plural}"
    if seconds < 60:
        return f"toutes les {seconds} secondes"
    return f"toutes les {seconds // 60} minutes"
