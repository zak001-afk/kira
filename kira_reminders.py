"""In-memory voice reminders for KIRA.

    "remind me in 5 minutes to call mom"
    "rappelle-moi dans 2 heures de fermer la session"
    "ذكرني بعد 10 دقائق"

Reminders live for the duration of the KIRA process and fire through a
callback (the voice agent wires it to ``speak``). Daemon timers never block
shutdown.
"""
from __future__ import annotations

import logging
import re
import threading
import time

log = logging.getLogger(__name__)

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_UNITS = {
    "en": {"s": {"second", "seconds", "sec", "secs"},
           "m": {"minute", "minutes", "min", "mins"},
           "h": {"hour", "hours", "hr", "hrs"}},
    "fr": {"s": {"seconde", "secondes"},
           "m": {"minute", "minutes"},
           "h": {"heure", "heures"}},
    "ar": {"s": {"ثانية", "ثواني", "ثوان"},
           "m": {"دقيقة", "دقائق"},
           "h": {"ساعة", "ساعات"}},
}

# display pairs (singular, plural) used when speaking durations aloud
_DISPLAY_UNITS = {
    "en": {"h": ("hour", "hours"), "m": ("minute", "minutes"), "s": ("second", "seconds")},
    "fr": {"h": ("heure", "heures"), "m": ("minute", "minutes"), "s": ("seconde", "secondes")},
    "ar": {"h": ("ساعة", "ساعات"), "m": ("دقيقة", "دقائق"), "s": ("ثانية", "ثواني")},
}

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "quarter": 0.25, "half": 0.5,
    "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "demi": 0.5, "quart": 0.25,
    "واحدة": 1, "واحد": 1, "اثنتين": 2, "ثلاث": 3, "أربع": 4, "خمس": 5,
    "نصف": 0.5, "ربع": 0.25,
}

# "remind me in 5 minutes to X" / "rappelle-moi dans 2 heures de X" / "ذكرني بعد 10 دقائق X"
_PATTERNS = [
    r"(?:remind me|set (?:a )?timer(?: for)?|rappelle[- ]moi|ذكرني|نبهني)",
]

_lock = threading.Lock()
_reminders: dict[int, dict] = {}
_next_id = 1

_on_fire = None  # callable(message: str)


def set_fire_callback(callback):
    """Install the function KIRA uses to announce a fired reminder."""
    global _on_fire
    _on_fire = callback


def humanize(seconds: float, language: str = "en") -> str:
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    units = _DISPLAY_UNITS.get(language, _DISPLAY_UNITS["en"])

    def _label(kind: str, n: int) -> str:
        singular, plural = units[kind]
        return singular if n == 1 else plural

    if hours:
        parts.append(f"{hours} {_label('h', hours)}")
    if minutes:
        parts.append(f"{minutes} {_label('m', minutes)}")
    if secs and not hours:
        parts.append(f"{secs} {_label('s', secs)}")
    if not parts:
        parts.append(f"0 {units['s'][1]}")
    return " ".join(parts[:2])


def parse_reminder(command: str):
    """Parse a natural reminder command.

    Returns dict(seconds, text) or None when the command is not a reminder.
    """
    text = (command or "").strip()
    if not text:
        return None
    lower = text.lower().translate(_ARABIC_DIGITS)

    is_reminder = any(re.search(pattern, lower) for pattern in _PATTERNS)
    if not is_reminder:
        return None

    # find "<amount> <unit>" anywhere after the trigger
    unit_tokens = sorted(
        {u for lang in _UNITS.values() for s in lang.values() for u in s},
        key=len,
        reverse=True,
    )
    number_tokens = sorted(_NUMBER_WORDS, key=len, reverse=True)
    pattern = rf"(?P<num>\d+(?:\.\d+)?|{'|'.join(number_tokens)})\s+(?P<unit>{'|'.join(unit_tokens)})\b"
    match = re.search(pattern, lower)
    if not match:
        return None

    raw_num = match.group("num")
    amount = float(raw_num) if re.fullmatch(r"\d+(?:\.\d+)?", raw_num) else _NUMBER_WORDS[raw_num]
    unit = match.group("unit")
    seconds = None
    for lang_units in _UNITS.values():
        for key, names in lang_units.items():
            if unit in names:
                seconds = amount * {"s": 1, "m": 60, "h": 3600}[key]
                break
        if seconds is not None:
            break
    if not seconds or seconds <= 0:
        return None

    # the reminder text is whatever is left once the trigger, the duration
    # and the connective prepositions are removed — regardless of word order
    # ("remind me in 5 minutes to X" and "remind me to X in 5 minutes").
    body = (lower[: match.start()] + " " + lower[match.end():]).strip()
    body = re.sub(
        r"(remind me(?: to)?|set (?:a )?timer(?: for)?|rappelle[- ]moi|ذكرني|نبهني)",
        " ",
        body,
    )
    body = re.sub(r"\b(in|dans|après|بعد|خلال)\b", " ", body)
    body = re.sub(r"^(to|de|d'|que|أن)\s+", "", body.strip())
    body = re.sub(r"\s{2,}", " ", body).strip(" .,")

    if not body:
        body = {"fr": "il est l'heure", "ar": "حان الوقت"}.get(
            detect_language_hint(lower), "time's up"
        )
        if "timer" in lower:
            body = "the timer finished"

    return {"seconds": seconds, "text": body, "language": detect_language_hint(lower)}


def detect_language_hint(text: str) -> str:
    if re.search(r"[\u0600-\u06FF]", text):
        return "ar"
    if any(token in text for token in ("rappelle", "dans", "heures", "bientôt")):
        return "fr"
    return "en"


# ── registry ────────────────────────────────────────────────────────────────

def _fire(reminder_id: int) -> None:
    with _lock:
        entry = _reminders.pop(reminder_id, None)
    if entry is None:
        return
    language = entry.get("language", "en")
    text = entry["text"]
    message = {
        "en": f"Reminder, sir: {text}.",
        "fr": f"Rappel, monsieur : {text}.",
        "ar": f"تذكير، سيدي: {text}.",
    }.get(language, f"Reminder: {text}.")
    callback = entry.get("on_fire") or _on_fire
    try:
        if callback:
            callback(message)
        else:
            print(f"KIRA REMINDER: {message}")
    except Exception as exc:  # never let a reminder kill the process
        log.warning("reminder callback failed: %s", exc)


def add_reminder(seconds: float, text: str, language: str = "en", on_fire=None) -> int:
    global _next_id
    timer = threading.Timer(float(seconds), _fire, args=(_next_id,))
    timer.daemon = True
    with _lock:
        reminder_id = _next_id
        _next_id += 1
        _reminders[reminder_id] = {
            "text": text,
            "language": language,
            "due_at": time.time() + float(seconds),
            "timer": timer,
            "on_fire": on_fire,
        }
    timer.start()
    return reminder_id


def cancel_reminder(reminder_id: int) -> bool:
    with _lock:
        entry = _reminders.pop(reminder_id, None)
    if entry is None:
        return False
    entry["timer"].cancel()
    return True


def cancel_all() -> int:
    with _lock:
        entries = list(_reminders.values())
        _reminders.clear()
    for entry in entries:
        entry["timer"].cancel()
    return len(entries)


def active() -> list[dict]:
    with _lock:
        entries = [
            {"id": rid, "text": e["text"], "language": e["language"],
             "remaining": max(0.0, e["due_at"] - time.time())}
            for rid, e in _reminders.items()
        ]
    return sorted(entries, key=lambda e: e["remaining"])


# ── spoken replies ───────────────────────────────────────────────────────────

def confirmation(seconds: float, text: str, language: str = "en") -> str:
    when = humanize(seconds, language)
    return {
        "en": f"I will remind you in {when}, sir: {text}.",
        "fr": f"Je vous le rappellerai dans {when}, monsieur : {text}.",
        "ar": f"سأذكرك بعد {when}، سيدي: {text}.",
    }.get(language, f"Reminder set: {text}.")


def describe_active(language: str = "en") -> str:
    entries = active()
    if not entries:
        return {
            "en": "You have no active reminders, sir.",
            "fr": "Vous n'avez aucun rappel actif, monsieur.",
            "ar": "لا توجد تذكيرات نشطة، سيدي.",
        }.get(language)
    parts = [
        f"'{e['text']}' ({humanize(e['remaining'], language)})" for e in entries
    ]
    listing = "; ".join(parts)
    return {
        "en": f"You have {len(entries)} reminder{'s' if len(entries) != 1 else ''}, sir: {listing}.",
        "fr": f"Vous avez {len(entries)} rappel{'s' if len(entries) != 1 else ''}, monsieur : {listing}.",
        "ar": f"لديك {len(entries)} تذكيرات، سيدي: {listing}.",
    }.get(language)


def cleared_message(count: int, language: str = "en") -> str:
    if count == 0:
        return describe_active(language)
    return {
        "en": f"All {count} reminder{'s' if count != 1 else ''} cancelled, sir.",
        "fr": f"Les {count} rappels ont été annulés, monsieur.",
        "ar": f"تم إلغاء {count} تذكيرات، سيدي.",
    }.get(language)
