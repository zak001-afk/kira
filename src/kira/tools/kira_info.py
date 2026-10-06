"""Keyless public information tools: weather, holidays, currency, jokes,
fun facts.

Every service here is free, needs NO API key and NO account — nothing to
put in .env, nothing to leak, nothing to rotate:
- Weather + geocoding: Open-Meteo (open-meteo.com)
- Public holidays:     Nager.Date (date.nager.at)
- Exchange rates:      fawazahmed0/currency-api (jsDelivr CDN + fallback)
- Jokes (EN/FR/…):     JokeAPI (v2.jokeapi.dev), safe-mode always on
- Fun facts:           uselessfacts.jsph.pl

Tools return DATA (dicts/strings) and raise on failure; the agent registry
turns exceptions into structured errors. Nothing here speaks or touches
the UI, and nothing personal is ever sent — only city names, country codes
and currency codes.
"""

import os
import re
from datetime import date

import requests

DEFAULT_TIMEOUT = 8
_HEADERS = {"User-Agent": "KIRA-desktop-assistant/1.0"}

# Grouped WMO weather interpretation codes -> short condition wording.
_CONDITIONS = (
    ({0}, {"en": "clear sky", "fr": "ciel dégagé", "ar": "سماء صافية"}),
    ({1, 2}, {"en": "partly cloudy", "fr": "partiellement nuageux", "ar": "غائم جزئياً"}),
    ({3}, {"en": "overcast", "fr": "couvert", "ar": "غائم"}),
    ({45, 48}, {"en": "fog", "fr": "brouillard", "ar": "ضباب"}),
    ({51, 53, 55, 56, 57}, {"en": "drizzle", "fr": "bruine", "ar": "رذاذ"}),
    ({61, 63, 65, 66, 67, 80, 81, 82}, {"en": "rain", "fr": "pluie", "ar": "مطر"}),
    ({71, 73, 75, 77, 85, 86}, {"en": "snow", "fr": "neige", "ar": "ثلج"}),
    ({95, 96, 99}, {"en": "thunderstorm", "fr": "orage", "ar": "عاصفة رعدية"}),
)

# Common country names (EN/FR) -> ISO codes for Nager.Date.
COUNTRY_CODES = {
    "tunisia": "TN", "tunisie": "TN", "تونس": "TN",
    "france": "FR", "germany": "DE", "allemagne": "DE", "spain": "ES",
    "espagne": "ES", "italy": "IT", "italie": "IT", "portugal": "PT",
    "united kingdom": "GB", "uk": "GB", "royaume-uni": "GB",
    "united states": "US", "usa": "US", "etats-unis": "US", "états-unis": "US",
    "canada": "CA", "morocco": "MA", "maroc": "MA", "algeria": "DZ",
    "algerie": "DZ", "algérie": "DZ", "egypt": "EG", "egypte": "EG",
    "égypte": "EG", "turkey": "TR", "turquie": "TR", "japan": "JP",
    "japon": "JP", "china": "CN", "chine": "CN", "brazil": "BR",
    "bresil": "BR", "brésil": "BR", "netherlands": "NL", "pays-bas": "NL",
    "belgium": "BE", "belgique": "BE", "switzerland": "CH", "suisse": "CH",
}

# Spoken currency names -> ISO codes.
CURRENCY_WORDS = {
    "euro": "eur", "euros": "eur", "dollar": "usd", "dollars": "usd",
    "dinar": "tnd", "dinars": "tnd", "dinar tunisien": "tnd",
    "pound": "gbp", "pounds": "gbp", "livre": "gbp", "livres": "gbp",
    "dirham": "mad", "dirhams": "mad", "yen": "jpy", "yens": "jpy",
}

_JOKE_LANGUAGES = {"en", "fr", "de", "es", "pt", "cs"}


def _get_json(url, params=None, timeout=DEFAULT_TIMEOUT):
    """One HTTP GET returning parsed JSON. Single seam for tests."""
    response = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.json()


def condition_text(code, language="en"):
    for codes, wording in _CONDITIONS:
        if code in codes:
            return wording.get(language) or wording["en"]
    return {"en": "unusual weather", "fr": "temps inhabituel", "ar": "طقس غير معتاد"}.get(language, "unusual weather")


def default_city():
    return os.environ.get("KIRA_CITY", "").strip()


def default_country():
    return os.environ.get("KIRA_COUNTRY", "TN").strip().upper() or "TN"


def get_weather(city: str) -> dict:
    """Current weather + today/tomorrow range for a city (Open-Meteo, keyless)."""
    city = str(city or "").strip()
    if not city:
        raise ValueError("No city given.")
    geo = _get_json("https://geocoding-api.open-meteo.com/v1/search",
                    {"name": city, "count": 1, "language": "en", "format": "json"})
    places = geo.get("results") or []
    if not places:
        raise ValueError(f"Unknown city: {city}")
    place = places[0]
    forecast = _get_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 2,
    })
    current = forecast.get("current") or {}
    daily = forecast.get("daily") or {}
    code = int(current.get("weather_code", 0))
    return {
        "city": place.get("name") or city,
        "country": place.get("country") or "",
        "temperature": current.get("temperature_2m"),
        "feels_like": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind_kmh": current.get("wind_speed_10m"),
        "condition_code": code,
        "condition": {lang: condition_text(code, lang) for lang in ("en", "fr", "ar")},
        "today_min": (daily.get("temperature_2m_min") or [None])[0],
        "today_max": (daily.get("temperature_2m_max") or [None])[0],
        "tomorrow_min": (daily.get("temperature_2m_min") or [None, None])[1],
        "tomorrow_max": (daily.get("temperature_2m_max") or [None, None])[1],
        "rain_chance_today": (daily.get("precipitation_probability_max") or [None])[0],
    }


def get_holidays(country: str = "", year: int = 0) -> dict:
    """Public holidays for a country/year (Nager.Date, keyless).

    `country` may be an ISO code (TN, FR) or a common EN/FR country name.
    Includes `upcoming`: holidays from today on (this year only)."""
    raw = str(country or "").strip()
    code = COUNTRY_CODES.get(raw.lower(), raw.upper()) if raw else default_country()
    if not re.fullmatch(r"[A-Z]{2}", code):
        raise ValueError(f"Unknown country: {country}")
    year = int(year) or date.today().year
    rows = _get_json(f"https://date.nager.at/api/v3/PublicHolidays/{year}/{code}")
    holidays = [{"date": row.get("date"), "name": row.get("name"),
                 "local_name": row.get("localName")} for row in rows or []]
    today = date.today().isoformat()
    upcoming = [h for h in holidays if (h["date"] or "") >= today] if year == date.today().year else holidays
    return {"country": code, "year": year, "holidays": holidays, "upcoming": upcoming}


def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert between 150+ currencies incl. TND (currency-api, keyless).

    Rates from the fawazahmed0/currency-api CDN, with an automatic mirror
    fallback. Daily reference rates — information, not trading advice."""
    src = CURRENCY_WORDS.get(str(from_currency).strip().lower(), str(from_currency).strip().lower())
    dst = CURRENCY_WORDS.get(str(to_currency).strip().lower(), str(to_currency).strip().lower())
    if not re.fullmatch(r"[a-z]{3,5}", src) or not re.fullmatch(r"[a-z]{3,5}", dst):
        raise ValueError(f"Unknown currency: {from_currency} / {to_currency}")
    amount = float(amount)
    urls = (f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{src}.json",
            f"https://latest.currency-api.pages.dev/v1/currencies/{src}.json")
    payload, last_error = None, None
    for url in urls:
        try:
            payload = _get_json(url)
            break
        except Exception as error:  # try the mirror before giving up
            last_error = error
    if payload is None:
        raise last_error
    table = payload.get(src) or {}
    if dst not in table:
        raise ValueError(f"No rate for {src.upper()} -> {dst.upper()}.")
    rate = float(table[dst])
    return {"amount": amount, "from": src.upper(), "to": dst.upper(),
            "rate": rate, "result": round(amount * rate, 3),
            "date": payload.get("date", "")}


def tell_joke(language: str = "en") -> str:
    """One safe-mode joke (JokeAPI, keyless). EN/FR/DE/ES/PT/CS; others fall back to EN."""
    lang = str(language or "en").strip().lower()[:2]
    if lang not in _JOKE_LANGUAGES:
        lang = "en"
    data = _get_json("https://v2.jokeapi.dev/joke/Any", {"safe-mode": "", "lang": lang})
    if data.get("error"):
        raise RuntimeError(str(data.get("message") or "Joke service error."))
    if data.get("type") == "twopart":
        return f"{data.get('setup', '').strip()}\n{data.get('delivery', '').strip()}".strip()
    return str(data.get("joke", "")).strip()


def fun_fact() -> str:
    """One random true-but-useless fact (uselessfacts.jsph.pl, keyless, EN)."""
    data = _get_json("https://uselessfacts.jsph.pl/api/v2/facts/random", {"language": "en"})
    return str(data.get("text", "")).strip()


def crypto_price(coin: str, currency: str = "usd") -> dict:
    """Live crypto price via CoinGecko (keyless). Spoken names accepted."""
    coins = {"bitcoin": "bitcoin", "btc": "bitcoin", "ethereum": "ethereum",
             "eth": "ethereum", "dogecoin": "dogecoin", "doge": "dogecoin",
             "cardano": "cardano", "ada": "cardano", "solana": "solana",
             "sol": "solana", "litecoin": "litecoin", "xrp": "ripple"}
    currencies = {"usd": "usd", "eur": "eur", "tnd": "tnd", "dollar": "usd",
                  "dinars": "tnd", "dinar": "tnd", "euro": "eur", "euros": "eur"}
    coin_id = coins.get(str(coin or "").strip().lower())
    if not coin_id:
        raise ValueError(f"Unknown crypto coin: {coin}")
    vs = currencies.get(str(currency or "usd").strip().lower(), "usd")
    data = _get_json("https://api.coingecko.com/api/v3/simple/price",
                     {"ids": coin_id, "vs_currencies": vs,
                      "include_24hr_change": "true"})
    entry = (data.get(coin_id) or {})
    price = entry.get(vs)
    if price is None:
        raise RuntimeError(f"No price found for {coin} in {vs}.")
    return {"coin": coin_id, "currency": vs, "price": price,
            "change_24h": entry.get(f"{vs}_24h_change")}


_PRAYER_METHOD = 3  # Union Organization Islamic de France — widely used in TN/Maghreb


def prayer_times(city: str = "") -> dict:
    """Today's prayer times + Hijri date for a city (Aladhan, keyless)."""
    city = str(city or default_city() or "Nabeul").strip()
    geo = _get_json("https://geocoding-api.open-meteo.com/v1/search",
                    {"name": city, "count": 1, "language": "en", "format": "json"})
    places = geo.get("results") or []
    if not places:
        raise ValueError(f"Unknown city: {city}")
    place = places[0]
    data = _get_json("https://api.aladhan.com/v1/timings",
                     {"latitude": place["latitude"], "longitude": place["longitude"],
                      "method": _PRAYER_METHOD})
    timings = ((data.get("data") or {}).get("timings") or {})
    hijri = (((data.get("data") or {}).get("date") or {}).get("hijri") or {})
    wanted = ("Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha")
    times = {name: timings.get(name, "") for name in wanted}
    if not any(times.values()):
        raise RuntimeError("Prayer service returned no timings.")
    return {"city": place.get("name", city), "times": times,
            "hijri_date": hijri.get("date", ""),
            "hijri_month": (hijri.get("month") or {}).get("en", ""),
            "hijri_year": hijri.get("year", "")}


def song_search(query: str, limit: int = 3) -> dict:
    """Search a song on iTunes (keyless): title, artist, album, 30s preview."""
    query = str(query or "").strip()
    if not query:
        raise ValueError("No song to search.")
    data = _get_json("https://itunes.apple.com/search",
                     {"term": query, "entity": "song", "limit": max(1, min(int(limit or 3), 5))},
                     timeout=10)
    songs = []
    for row in (data.get("results") or [])[:max(1, min(int(limit or 3), 5))]:
        songs.append({"title": row.get("trackName", ""),
                      "artist": row.get("artistName", ""),
                      "album": row.get("collectionName", ""),
                      "preview_url": row.get("previewUrl", ""),
                      "artwork": row.get("artworkUrl100", "")})
    if not songs:
        raise ValueError(f"No song found for: {query}")
    return {"query": query, "count": len(songs), "songs": songs}


def daily_quote() -> dict:
    """Random quote (ZenQuotes, keyless) — also injected in the morning briefing."""
    data = _get_json("https://zenquotes.io/api/random", timeout=10)
    rows = data if isinstance(data, list) else []
    if not rows or not isinstance(rows[0], dict):
        raise RuntimeError("Quote service error.")
    return {"quote": str(rows[0].get("q", "")).strip(),
            "author": str(rows[0].get("a", "")).strip()}


_WIKI_LANGUAGES = {"en", "fr", "ar", "es", "de", "it", "pt"}

# Spoken language names (EN/FR) -> ISO codes, for translation targets.
LANGUAGE_CODES = {
    "english": "en", "anglais": "en", "french": "fr", "francais": "fr",
    "français": "fr", "arabic": "ar", "arabe": "ar", "spanish": "es",
    "espagnol": "es", "german": "de", "allemand": "de", "italian": "it",
    "italien": "it", "portuguese": "pt", "portugais": "pt", "turkish": "tr",
    "turc": "tr", "russian": "ru", "russe": "ru", "chinese": "zh",
    "chinois": "zh", "japanese": "ja", "japonais": "ja",
}


def wiki_summary(topic: str, language: str = "en") -> dict:
    """Lead summary of the best-matching Wikipedia article (keyless, ~150 ms).

    Tries the requested language edition first (en/fr/ar/es/de/it/pt),
    then the English one. Raises when nothing matches."""
    from urllib.parse import quote
    topic = str(topic or "").strip()
    if not topic:
        raise ValueError("No topic given.")
    lang = str(language or "en").strip().lower()[:2]
    if lang not in _WIKI_LANGUAGES:
        lang = "en"
    editions = (lang, "en") if lang != "en" else ("en",)
    for code in editions:
        try:
            found = _get_json(f"https://{code}.wikipedia.org/w/rest.php/v1/search/title",
                              {"q": topic, "limit": 1})
            pages = found.get("pages") or []
            if not pages:
                continue
            title = pages[0].get("key") or pages[0].get("title")
            data = _get_json(f"https://{code}.wikipedia.org/api/rest_v1/page/summary/{quote(str(title))}")
            extract = str(data.get("extract", "")).strip()
            if extract:
                return {"title": data.get("title") or title,
                        "summary": extract,
                        "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page", ""),
                        "language": code}
        except Exception:
            continue  # try the next edition before giving up
    raise ValueError(f"Nothing found on Wikipedia for: {topic}")


def translate_text(text: str, target_language: str, source_language: str = "") -> dict:
    """Translate a short text (MyMemory, keyless). Language names or codes.

    The source language is detected locally (kira_language) when not given —
    only the text itself ever leaves the machine."""
    text = str(text or "").strip().strip('"\u201c\u201d\u00ab\u00bb').strip("'").strip()
    if not text:
        raise ValueError("No text to translate.")
    dst = LANGUAGE_CODES.get(str(target_language).strip().lower(), str(target_language).strip().lower())
    if not re.fullmatch(r"[a-z]{2}", dst):
        raise ValueError(f"Unknown target language: {target_language}")
    src = LANGUAGE_CODES.get(str(source_language).strip().lower(), str(source_language).strip().lower())
    if not re.fullmatch(r"[a-z]{2}", src or ""):
        try:
            import kira_language
            src = kira_language.detect_language(text).language or "en"
        except Exception:
            src = "en"
    if src == dst:
        return {"translated": text, "source": src, "target": dst, "match": 1.0}
    try:
        data = _get_json("https://api.mymemory.translated.net/get",
                         {"q": text, "langpair": f"{src}|{dst}"})
    except requests.HTTPError as error:
        if getattr(error.response, "status_code", 0) == 429:
            raise RuntimeError("The free translation quota for today is used up "
                               "(MyMemory). Ask the chat model to translate instead.") from error
        raise
    body = data.get("responseData") or {}
    translated = str(body.get("translatedText", "")).strip()
    if int(data.get("responseStatus", 0) or 0) != 200 or not translated:
        raise RuntimeError(str(data.get("responseDetails") or "Translation service error."))
    return {"translated": translated, "source": src, "target": dst,
            "match": body.get("match")}
