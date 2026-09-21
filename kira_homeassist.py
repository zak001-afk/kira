"""Optional Home Assistant bridge (local-first: your HA instance only).

Configure in kira_config.json:

    "home_assistant": {
        "url": "http://homeassistant.local:8123",
        "token": "long-lived-access-token",
        "entities": {"desk lamp": "light.desk_lamp", "fan": "switch.fan"}
    }

When unconfigured, the feature is completely inert: the voice parser asks
``find_entity`` first and falls through to normal routing when nothing is
known.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

_config: dict = {}


def configure(config: dict | None) -> None:
    global _config
    _config = dict(config or {})


def is_configured() -> bool:
    return bool(_config.get("url") and _config.get("entities"))


def find_entity(target: str):
    """Match a spoken name to a configured entity id, or None."""
    if not is_configured():
        return None
    key = (target or "").strip().lower()
    entities = _config.get("entities", {})
    if key in entities:
        return entities[key], key
    for name, entity_id in entities.items():
        if key and (key in name.lower() or name.lower() in key):
            return entity_id, name
    return None


def call_service(entity_id: str, turn_on: bool, opener=None) -> bool:
    """POST /api/services/<domain>/turn_on|turn_off to the HA instance."""
    domain = entity_id.split(".", 1)[0]
    service = "turn_on" if turn_on else "turn_off"
    url = f"{_config['url'].rstrip('/')}/api/services/{domain}/{service}"
    request = urllib.request.Request(
        url,
        data=json.dumps({"entity_id": entity_id}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_config.get('token', '')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(request, timeout=8) as response:
            return 200 <= getattr(response, "status", 200) < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


_REPLIES = {
    "ok": {
        "en": "Done sir. The {name} is now {state}.",
        "fr": "C'est fait, monsieur. {name} est maintenant {state}.",
        "ar": "تم، سيدي. {name} الآن {state}.",
    },
    "failed": {
        "en": "I couldn't reach the {name}, sir — is Home Assistant running?",
        "fr": "Impossible de joindre {name}, monsieur — Home Assistant est-il lancé ?",
        "ar": "لم أستطع الوصول إلى {name}، سيدي — هل يعمل Home Assistant؟",
    },
}

_STATES = {
    "en": ("on", "off"),
    "fr": ("allumé", "éteint"),
    "ar": ("يعمل", "متوقف"),
}


def control(target: str, turn_on: bool, language: str = "en", opener=None) -> str:
    """Full spoken control flow for a target name."""
    found = find_entity(target)
    states = _STATES.get(language, _STATES["en"])
    state_word = states[0] if turn_on else states[1]
    if not found:
        return {
            "en": f"I don't know any device called '{target}', sir.",
            "fr": f"Je ne connais aucun appareil nommé '{target}', monsieur.",
            "ar": f"لا أعرف أي جهاز باسم '{target}'، سيدي.",
        }[language if language in _REPLIES["ok"] else "en"]
    entity_id, name = found
    if call_service(entity_id, turn_on, opener=opener):
        return _REPLIES["ok"].get(language, _REPLIES["ok"]["en"]).format(
            name=name, state=state_word
        )
    return _REPLIES["failed"].get(language, _REPLIES["failed"]["en"]).format(name=name)
