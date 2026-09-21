"""Stark-lab protocols: voice lock with optional passphrase, privacy blur.

State lives here; the actual OS actions (lock workstation, show desktop,
mute) stay in the voice agent, which calls this module for decisions
and spoken replies.
"""
from __future__ import annotations

import re

_lab_locked = False


def is_locked() -> bool:
    return _lab_locked


def lock() -> None:
    global _lab_locked
    _lab_locked = True


def unlock() -> None:
    global _lab_locked
    _lab_locked = False


def extract_unlock(command: str, passphrase: str = ""):
    """Parse an unlock attempt; returns ("unlock", "deny") or None.

    Commands: "unlock the lab", "unlock the lab <passphrase>",
    FR "ouvre le labo", AR "افتح المختبر".
    """
    text = re.sub(r"\s+", " ", (command or "").strip().lower())
    patterns = [
        r"^unlock the lab(?:\s+(?P<pw>.+))?$",
        r"^déverrouille le labo(?:\s+(?P<pw>.+))?$",
        r"^افتح المختبر(?:\s+(?P<pw>.+))?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        wanted = (passphrase or "").strip().lower()
        if not wanted:
            return "unlock"
        offered = (match.group("pw") or "").strip()
        return "unlock" if offered and offered == wanted else "deny"
    return None


_LOCK_REPLIES = {
    "en": "The lab is secured, sir. Say 'unlock the lab' to resume.",
    "fr": "Le labo est verrouillé, monsieur. Dites 'déverrouille le labo' pour reprendre.",
    "ar": "المختبر مؤمّن، سيدي. قل 'افتح المختبر' للمتابعة.",
}

_UNLOCK_REPLIES = {
    "en": "Welcome back, sir. The lab is open.",
    "fr": "Bon retour, monsieur. Le labo est ouvert.",
    "ar": "أهلاً بعودتك، سيدي. المختبر مفتوح.",
}

_DENY_REPLIES = {
    "en": "That passphrase does not match, sir. The lab stays locked.",
    "fr": "Ce mot de passe ne correspond pas, monsieur. Le labo reste verrouillé.",
    "ar": "كلمة المرور غير صحيحة، سيدي. يبقى المختبر مغلقاً.",
}

_BLUR_REPLIES = {
    "en": "Privacy mode engaged, sir.",
    "fr": "Mode discrétion activé, monsieur.",
    "ar": "تم تفعيل وضع الخصوصية، سيدي.",
}


def lock_reply(language: str = "en") -> str:
    return _LOCK_REPLIES.get(language, _LOCK_REPLIES["en"])


def unlock_reply(language: str = "en") -> str:
    return _UNLOCK_REPLIES.get(language, _UNLOCK_REPLIES["en"])


def deny_reply(language: str = "en") -> str:
    return _DENY_REPLIES.get(language, _DENY_REPLIES["en"])


def blur_reply(language: str = "en") -> str:
    return _BLUR_REPLIES.get(language, _BLUR_REPLIES["en"])


def locked_notice(language: str = "en") -> str:
    return _LOCK_REPLIES.get(language, _LOCK_REPLIES["en"])
