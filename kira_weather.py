"""Opt-in weather via wttr.in (the only feature that touches the network).

Fully stdlib; everything fails safe to an apology. ``fetch`` is injectable
so tests never leave the sandbox.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote_plus

DEFAULT_TIMEOUT = 6.0


def extract_city(command: str) -> "str | None":
    """'weather in tunis' / 'météo à paris' / 'الطقس في تونس' -> city."""
    text = (command or "").strip()
    for separator in (" in ", " à ", " of ", " في "):
        if separator in text.lower() or separator in text:
            before, _, after = text.partition(separator)
            if re.search(r"(weather|météo|meteo|الطقس)", before.lower()):
                city = after.strip(" .?")
                return city or None
    return ""  # weather with no city → auto-locate


def is_weather_command(command: str) -> bool:
    text = (command or "").strip().lower()
    if not text:
        return False
    starts = ("weather", "what's the weather", "what is the weather",
              "the weather", "météo", "meteo", "الطقس")
    return any(text.startswith(prefix) for prefix in starts)


def fetch(city: str = "", timeout: float = DEFAULT_TIMEOUT, opener=None):
    """GET wttr.in JSON. ``opener`` is injectable for tests."""
    url = "https://wttr.in/" + quote_plus(city or "") + "?format=j1"
    open_fn = opener or urllib.request.urlopen
    with open_fn(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


_REPORTS = {
    "en": "{city}: {desc}, {temp}°C, feels like {feels}°C, humidity {humidity}%, sir.",
    "fr": "{city} : {desc}, {temp}°C, ressenti {feels}°C, humidité {humidity}%, monsieur.",
    "ar": "{city}: {desc}، {temp} درجة مئوية، الإحساس {feels} درجة، الرطوبة {humidity}%، سيدي.",
}

_FALLBACK = {
    "en": "I could not reach the weather service right now, sir.",
    "fr": "Je n'arrive pas à joindre le service météo pour le moment, monsieur.",
    "ar": "لم أستطع الوصول إلى خدمة الطقس الآن، سيدي.",
}


def format_report(data: dict, city: str, language: str = "en") -> str:
    """Turn wttr.in's payload into a spoken line."""
    current = (data.get("current_condition") or [{}])[0]
    desc = ""
    for key in ("weatherDesc", "lang_fr", "lang_ar"):
        entries = current.get(key)
        if isinstance(entries, list) and entries and entries[0].get("value"):
            desc = entries[0]["value"]
            break
    nearest = (data.get("nearest_area") or [{}])[0]
    area = nearest.get("areaName", [{}])[0].get("value", "") if nearest else ""
    display_city = city or area or "your location"
    template = _REPORTS.get(language, _REPORTS["en"])
    return template.format(
        city=display_city,
        desc=desc or "clear",
        temp=current.get("temp_C", "?"),
        feels=current.get("FeelsLikeC", "?"),
        humidity=current.get("humidity", "?"),
    )


def report(city: str, language: str = "en", opener=None) -> str:
    try:
        data = fetch(city or "", opener=opener)
    except (urllib.error.URLError, OSError, ValueError):
        return _FALLBACK.get(language, _FALLBACK["en"])
    try:
        return format_report(data, city, language)
    except Exception:
        return _FALLBACK.get(language, _FALLBACK["en"])
