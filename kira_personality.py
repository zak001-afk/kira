"""KIRA's personality layer: humor levels, time-aware greetings, boot theater.

Personality levels (config key ``personality.humor``):
- ``charming`` — warm, smooth, reassuring; makes the user feel looked after (default)
- ``neutral``  — plain, efficient acknowledgements
- ``dry``      — restrained JARVIS-style wit
- ``formal``   — extra proper and precise

Everything is deterministic: reply variants are chosen by hashing the text,
so identical commands always sound the same (and tests stay stable).
"""
from __future__ import annotations

LEVELS = ("charming", "neutral", "dry", "formal")
DEFAULT_LEVEL = "charming"


def normalize(level) -> str:
    """Coerce any config value to a known personality level."""
    value = str(level or DEFAULT_LEVEL).strip().lower()
    return value if value in LEVELS else DEFAULT_LEVEL


def _pick(seed: str, options: list[str]) -> str:
    index = sum(ord(ch) for ch in seed) % len(options)
    return options[index]


# ── acknowledgements ─────────────────────────────────────────────────────────

_DONE_VARIANTS = {
    "en": {
        "charming": [
            "Consider it done, sir.",
            "Right away, sir.",
            "With pleasure, sir.",
            "Of course, sir.",
            "Done, sir — happy to help.",
            "It's my pleasure, sir.",
        ],
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
        "charming": [
            "Avec plaisir, monsieur.",
            "Tout de suite, monsieur.",
            "C'est fait, monsieur — ravi de vous aider.",
            "Bien sûr, monsieur.",
        ],
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
        "charming": [
            "بكل سرور، سيدي.",
            "حالاً، سيدي.",
            "تم، سيدي — يسعدني خدمتك.",
            "بالتأكيد، سيدي.",
        ],
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

# ── charming: warm, reassuring, made to feel comfortable ─────────────────────

_CHARMING_GREETINGS = {
    "en": {
        "morning": "Good morning sir. I hope you slept well — everything is ready for you.",
        "afternoon": "Good afternoon, sir. Take your time; I'll handle the busywork.",
        "evening": "Good evening, sir. Let's make this a calm one.",
        "night": "It's late, sir. I'll keep things quiet — do rest soon.",
    },
    "fr": {
        "morning": "Bonjour monsieur. J'espère que vous avez bien dormi — tout est prêt pour vous.",
        "afternoon": "Bon après-midi, monsieur. Prenez votre temps, je m'occupe du reste.",
        "evening": "Bonsoir monsieur. Faisons de cette soirée un moment tranquille.",
        "night": "Il est tard, monsieur. Je reste discret — reposez-vous bientôt.",
    },
    "ar": {
        "morning": "صباح الخير سيدي. أرجو أنك نمت جيداً — كل شيء جاهز لك.",
        "afternoon": "مساء الخير سيدي. خذ وقتك، وسأتكفل بالباقي.",
        "evening": "مساء الخير سيدي. لنجعل هذه الأمسية هادئة.",
        "night": "الوقت متأخر، سيدي. سأبقى هادئاً — ارتح قريباً.",
    },
}

_FAILED_REPLIES = {
    "en": {
        "charming": "That didn't quite work, sir — no trouble at all, we'll find another way.",
        "neutral": "I couldn't do that, sir.",
        "dry": "That one got away from me, sir. Shall we try again?",
        "formal": "I regret that the request could not be completed, sir.",
    },
    "fr": {
        "charming": "Cela n'a pas tout à fait fonctionné, monsieur — sans souci, nous trouverons un autre moyen.",
        "neutral": "Je n'ai pas pu faire cela, monsieur.",
        "dry": "Celle-là m'a échappé, monsieur. On réessaie ?",
        "formal": "Je regrette que la demande n'ait pu être exécutée, monsieur.",
    },
    "ar": {
        "charming": "لم تنجح تماماً، سيدي — لا بأس، سنجد طريقة أخرى.",
        "neutral": "لم أستطع تنفيذ ذلك، سيدي.",
        "dry": "أفلتت مني هذه المرة، سيدي. هل نحاول مجدداً؟",
        "formal": "يؤسفني أن الطلب لم يكتمل، سيدي.",
    },
}


def failed_reply(language: str = "en", humor: str = DEFAULT_LEVEL) -> str:
    """A kind, personality-aware line for a command that could not run."""
    table = _FAILED_REPLIES.get(language, _FAILED_REPLIES["en"])
    return table.get(humor) or table[DEFAULT_LEVEL]


def greeting(hour: int, language: str = "en", humor: str = DEFAULT_LEVEL) -> str:
    """A time-aware greeting; warm for charming, witty for dry."""
    day = daypart(hour)
    if humor == "charming":
        table = _CHARMING_GREETINGS.get(language)
        if table:
            return table[day]
    language_table = _GREETINGS.get(language, _GREETINGS["en"])
    base = language_table[day]
    if humor == "dry":
        suffix = _DRY_SUFFIX.get(language, {}).get(day)
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
    elif humor == "charming":
        lines.append("Everything is ready for you, sir — at your service.")
    return lines
