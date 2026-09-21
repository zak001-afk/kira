"""KIRA's personality layer: humor levels, time-aware greetings, boot theater.

Humor levels (config key ``personality.humor``):
- ``neutral`` — plain, efficient acknowledgements (default)
- ``dry``     — restrained JARVIS-style wit
- ``formal``  — extra proper and precise

Everything is deterministic: reply variants are chosen by hashing the text,
so identical commands always sound the same (and tests stay stable).
"""
from __future__ import annotations

LEVELS = ("neutral", "dry", "formal")
DEFAULT_LEVEL = "neutral"


def normalize(level) -> str:
    """Coerce any config value to a known humor level."""
    value = str(level or DEFAULT_LEVEL).strip().lower()
    return value if value in LEVELS else DEFAULT_LEVEL


def _pick(seed: str, options: list[str]) -> str:
    index = sum(ord(ch) for ch in seed) % len(options)
    return options[index]


# ── acknowledgements ─────────────────────────────────────────────────────────

_DONE_VARIANTS = {
    "en": {
        "neutral": ["Done sir."],
        "dry": [
            "Done sir.",
            "Consider it done.",
            "Already handled, sir.",
            "As you wish.",
        ],
        "formal": [
            "It is done, sir.",
            "Certainly sir, it is complete.",
        ],
    },
    "fr": {
        "neutral": ["C'est fait, monsieur."],
        "dry": [
            "C'est fait, monsieur.",
            "Déjà réglé, monsieur.",
            "Comme vous voulez.",
        ],
        "formal": [
            "C'est terminé, monsieur.",
            "Certainement, monsieur, c'est accompli.",
        ],
    },
    "ar": {
        "neutral": ["تم، سيدي."],
        "dry": [
            "تم، سيدي.",
            "اعتبره منجزاً.",
            "كما تشاء.",
        ],
        "formal": [
            "لقد تم الأمر، سيدي.",
            "بالتأكيد، سيدي، اكتمل.",
        ],
    },
}


def done_ack(language: str = "en", humor: str = DEFAULT_LEVEL, seed: str = "") -> str:
    """An acknowledgement line in the configured tone (deterministic)."""
    table = _DONE_VARIANTS.get(language, _DONE_VARIANTS["en"])
    options = table.get(humor) or table["neutral"]
    return _pick(seed or language, options)


# ── greetings ────────────────────────────────────────────────────────────────

def daypart(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 23:
        return "evening"
    return "night"


_GREETINGS = {
    "en": {
        "morning": "Good morning sir.",
        "afternoon": "Good afternoon sir.",
        "evening": "Good evening sir.",
        "night": "Working late, sir?",
    },
    "fr": {
        "morning": "Bonjour monsieur.",
        "afternoon": "Bon après-midi, monsieur.",
        "evening": "Bonsoir monsieur.",
        "night": "Vous travaillez tard, monsieur ?",
    },
    "ar": {
        "morning": "صباح الخير سيدي.",
        "afternoon": "مساء الخير سيدي.",
        "evening": "مساء الخير سيدي.",
        "night": "تعمل في وقت متأخر، سيدي؟",
    },
}

_DRY_SUFFIX = {
    "en": {
        "morning": "I do hope today involves less chaos than yesterday.",
        "afternoon": "Productivity already looks promising.",
        "evening": "Shall we make the evening count?",
        "night": "The lab never really sleeps, does it.",
    },
    "fr": {},
    "ar": {},
}


def greeting(hour: int, language: str = "en", humor: str = DEFAULT_LEVEL) -> str:
    """A time-aware greeting; dry humor adds a restrained flourish."""
    language_table = _GREETINGS.get(language, _GREETINGS["en"])
    base = language_table[daypart(hour)]
    if humor == "dry":
        suffix = _DRY_SUFFIX.get(language, {}).get(daypart(hour))
        if suffix:
            return f"{base} {suffix}"
    return base


# ── boot theater ─────────────────────────────────────────────────────────────

def boot_lines(version: str, counts: dict, humor: str = DEFAULT_LEVEL) -> list[str]:
    """Escalating startup status lines (printed; the greeting is spoken)."""
    lines = [
        f"KIRA v{version} — initializing core systems",
        f"memory banks loaded: {counts.get('memories', 0)} facts, "
        f"{counts.get('learnings', 0)} skills, {counts.get('episodes', 0)} episodes",
        f"local models: {counts.get('model', '?')} / vision: {counts.get('vision', '?')}",
        "all systems nominal.",
    ]
    if humor == "dry":
        lines.append("I trust the lab is as I left it, sir.")
    return lines
