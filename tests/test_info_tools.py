"""Keyless info tools (weather, holidays, currency, jokes, facts):
data in, localized sentences out, zero API keys, zero network in tests."""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kira_agents
import kira_commands
import kira_info

GEO = {"results": [{"name": "Nabeul", "country": "Tunisia", "latitude": 36.45, "longitude": 10.73}]}
FORECAST = {
    "current": {"temperature_2m": 24.1, "apparent_temperature": 25.0,
                "relative_humidity_2m": 60, "weather_code": 0, "wind_speed_10m": 12.5},
    "daily": {"weather_code": [0, 3], "temperature_2m_max": [26.0, 27.5],
              "temperature_2m_min": [18.2, 19.0], "precipitation_probability_max": [5, 40]},
}
HOLIDAYS = [
    {"date": "2026-01-01", "name": "New Year's Day", "localName": "رأس السنة"},
    {"date": "2099-12-31", "name": "Future Day", "localName": "Future Day"},
]


def backend():
    return SimpleNamespace(normalize_command=lambda text: text,
                           parse_simple_command=lambda text: {"action": "none"},
                           ask_chat=Mock(return_value="chat answer"))


def route(text, **options):
    """La secrétaire annonce OÙ elle va chercher/agir avant chaque action :
    « oui » exécute. L'annonce est obligatoire sur ce chemin."""
    asked = kira_commands.process_command(backend(), text, **options)
    assert asked.get("needs_confirmation"), f"pas d'annonce d'intention: {asked}"
    assert asked["action"] == "intent", asked
    return kira_commands.process_command(backend(), "yes", **options)


class WeatherTests(unittest.TestCase):
    def test_geocodes_then_forecasts(self):
        with patch.object(kira_info, "_get_json", side_effect=[GEO, FORECAST]) as get:
            data = kira_info.get_weather("nabeul")
        self.assertEqual(data["city"], "Nabeul")
        self.assertEqual(data["temperature"], 24.1)
        self.assertEqual(data["condition"]["fr"], "ciel dégagé")
        self.assertEqual(data["tomorrow_max"], 27.5)
        self.assertEqual(get.call_count, 2)

    def test_unknown_city_raises(self):
        with patch.object(kira_info, "_get_json", return_value={"results": []}):
            with self.assertRaises(ValueError):
                kira_info.get_weather("xyzzy-nowhere")

    def test_route_localizes_french_response(self):
        with patch.object(kira_info, "_get_json", side_effect=[GEO, FORECAST]):
            result = route("météo à Nabeul", reply_language="fr")
        self.assertEqual(result["action"], "get_weather")
        self.assertTrue(result["success"])
        self.assertIn("Météo à Nabeul", result["response"])
        self.assertIn("ciel dégagé", result["response"])

    def test_no_city_no_default_asks_for_one(self):
        with patch.dict(os.environ, {"KIRA_CITY": ""}):
            result = route("weather", reply_language="en")
        self.assertEqual(result["error_code"], "city_missing")
        self.assertIn("KIRA_CITY", result["response"])

    def test_kira_city_default_is_used(self):
        with patch.dict(os.environ, {"KIRA_CITY": "Nabeul"}), \
                patch.object(kira_info, "_get_json", side_effect=[GEO, FORECAST]):
            result = route("what's the weather", reply_language="en")
        self.assertTrue(result["success"])
        self.assertIn("Weather in Nabeul", result["response"])


class HolidaysTests(unittest.TestCase):
    def test_country_names_map_to_iso_codes(self):
        with patch.object(kira_info, "_get_json", return_value=HOLIDAYS) as get:
            data = kira_info.get_holidays("tunisie", 2026)
        self.assertEqual(data["country"], "TN")
        self.assertIn("/2026/TN", get.call_args[0][0])
        self.assertEqual([h["date"] for h in data["upcoming"]], ["2099-12-31"])

    def test_unknown_country_raises(self):
        with self.assertRaises(ValueError):
            kira_info.get_holidays("atlantis")

    def test_route_lists_upcoming(self):
        with patch.object(kira_info, "_get_json", return_value=HOLIDAYS):
            result = route("holidays in France", reply_language="en")
        self.assertTrue(result["success"])
        self.assertIn("FR", result["response"])
        self.assertIn("2099-12-31", result["response"])
        self.assertNotIn("2026-01-01", result["response"])  # already past


class CurrencyTests(unittest.TestCase):
    RATES = {"date": "2026-09-27", "eur": {"tnd": 3.42, "usd": 1.17}}

    def test_convert_with_currency_words(self):
        with patch.object(kira_info, "_get_json", return_value=self.RATES):
            data = kira_info.convert_currency("100", "euros", "dinars")
        self.assertEqual((data["from"], data["to"]), ("EUR", "TND"))
        self.assertEqual(data["result"], 342.0)

    def test_cdn_failure_uses_mirror(self):
        with patch.object(kira_info, "_get_json", side_effect=[RuntimeError("cdn down"), self.RATES]) as get:
            data = kira_info.convert_currency(10, "eur", "usd")
        self.assertEqual(data["result"], 11.7)
        self.assertEqual(get.call_count, 2)
        self.assertIn("currency-api.pages.dev", get.call_args[0][0])

    def test_route_formats_sentence(self):
        with patch.object(kira_info, "_get_json", return_value=self.RATES):
            result = route("convert 100 eur to tnd", reply_language="en")
        self.assertTrue(result["success"])
        self.assertIn("100.0 EUR = 342.0 TND", result["response"])

    def test_missing_rate_raises(self):
        with patch.object(kira_info, "_get_json", return_value=self.RATES):
            with self.assertRaises(ValueError):
                kira_info.convert_currency(5, "eur", "xxx")


class JokeAndFactTests(unittest.TestCase):
    def test_twopart_joke_joined_and_arabic_falls_back_to_english(self):
        reply = {"error": False, "type": "twopart", "setup": "Why?", "delivery": "Because."}
        with patch.object(kira_info, "_get_json", return_value=reply) as get:
            joke = kira_info.tell_joke("ar")
        self.assertEqual(joke, "Why?\nBecause.")
        self.assertEqual(get.call_args[0][1]["lang"], "en")

    def test_french_joke_requested_in_french(self):
        reply = {"error": False, "type": "single", "joke": "Une blague."}
        with patch.object(kira_info, "_get_json", return_value=reply) as get:
            self.assertEqual(kira_info.tell_joke("fr"), "Une blague.")
        self.assertEqual(get.call_args[0][1]["lang"], "fr")

    def test_fun_fact_returns_plain_string_through_registry(self):
        with patch.object(kira_info, "_get_json", return_value={"text": "Bees sleep."}):
            result = kira_agents.run("fun_fact", {}, source="test")
        self.assertTrue(result.ok)
        self.assertEqual(result.response, "Bees sleep.")


WIKI_SEARCH = {"pages": [{"id": 1, "key": "Tunis", "title": "Tunis"}]}
WIKI_PAGE = {"title": "Tunis", "extract": "Tunis est la capitale de la Tunisie.",
             "content_urls": {"desktop": {"page": "https://fr.wikipedia.org/wiki/Tunis"}}}


class WikiTests(unittest.TestCase):
    def test_summary_in_requested_language(self):
        with patch.object(kira_info, "_get_json", side_effect=[WIKI_SEARCH, WIKI_PAGE]) as get:
            data = kira_info.wiki_summary("tunis", "fr")
        self.assertEqual(data["title"], "Tunis")
        self.assertIn("capitale", data["summary"])
        self.assertEqual(data["language"], "fr")
        self.assertIn("fr.wikipedia.org", get.call_args_list[0][0][0])

    def test_falls_back_to_english_edition(self):
        english = {"title": "Foo", "extract": "Foo is a thing.", "content_urls": {}}
        with patch.object(kira_info, "_get_json",
                          side_effect=[{"pages": []}, WIKI_SEARCH, english]):
            data = kira_info.wiki_summary("foo", "fr")
        self.assertEqual(data["language"], "en")

    def test_nothing_found_raises(self):
        with patch.object(kira_info, "_get_json", return_value={"pages": []}):
            with self.assertRaises(ValueError):
                kira_info.wiki_summary("xyzzy", "fr")

    def test_route_answers_with_the_summary(self):
        with patch.object(kira_info, "_get_json", side_effect=[WIKI_SEARCH, WIKI_PAGE]):
            result = route("qui est Tunis", reply_language="fr")
        self.assertEqual(result["action"], "wiki_summary")
        self.assertEqual(result["response"], "Tunis est la capitale de la Tunisie.")

    def test_route_not_found_is_a_localized_sentence(self):
        with patch.object(kira_info, "_get_json", return_value={"pages": []}):
            result = route("wikipedia xyzzy", reply_language="fr")
        self.assertEqual(result["error_code"], "wiki_not_found")
        self.assertIn("xyzzy", result["response"])

    def test_personal_who_is_never_hits_wikipedia(self):
        self.assertIsNone(kira_commands.parse_tool_command("who is my best friend"))
        self.assertIsNone(kira_commands.parse_tool_command("qui est mon patron"))


class TranslateTests(unittest.TestCase):
    REPLY = {"responseStatus": 200,
             "responseData": {"translatedText": "Bonjour tout le monde", "match": 0.98}}

    def test_translate_with_language_names(self):
        with patch.object(kira_info, "_get_json", return_value=self.REPLY) as get:
            data = kira_info.translate_text("hello everyone", "french", "english")
        self.assertEqual(data["translated"], "Bonjour tout le monde")
        self.assertEqual(get.call_args[0][1]["langpair"], "en|fr")

    def test_source_detected_locally_when_missing(self):
        with patch.object(kira_info, "_get_json", return_value=self.REPLY):
            data = kira_info.translate_text("hello everyone my dear friends", "fr")
        self.assertEqual(data["target"], "fr")
        self.assertIn(data["source"], {"en", "fr"})  # detector decides, never the network

    def test_same_language_short_circuits_without_network(self):
        with patch.object(kira_info, "_get_json", side_effect=AssertionError("no call")) as get:
            data = kira_info.translate_text("bonjour", "fr", "fr")
        self.assertEqual(data["translated"], "bonjour")
        get.assert_not_called()

    def test_route_returns_translation_as_response(self):
        with patch.object(kira_info, "_get_json", return_value=self.REPLY):
            result = route("translate hello everyone to french",
                                                   reply_language="en")
        self.assertEqual(result["action"], "translate_text")
        self.assertEqual(result["response"], "Bonjour tout le monde")

    def test_grammar_en_fr(self):
        parsed = kira_commands.parse_tool_command("traduis bonjour les amis en anglais")
        self.assertEqual(parsed, {"action": "translate_text", "text": "bonjour les amis",
                                  "target_language": "anglais"})
        self.assertIsNone(kira_commands.parse_tool_command("translate"))


class GrammarTests(unittest.TestCase):
    def parse(self, text):
        return kira_commands.parse_tool_command(text)

    def test_weather_grammar_en_fr(self):
        self.assertEqual(self.parse("what's the weather in Nabeul"),
                         {"action": "get_weather", "city": "Nabeul"})
        self.assertEqual(self.parse("météo à Paris"),
                         {"action": "get_weather", "city": "Paris"})
        self.assertEqual(self.parse("quel temps fait-il à Tunis ?"),
                         {"action": "get_weather", "city": "Tunis"})
        self.assertEqual(self.parse("weather")["city"], "")

    def test_holidays_grammar_en_fr(self):
        self.assertEqual(self.parse("holidays in France 2027"),
                         {"action": "get_holidays", "country": "France", "year": "2027"})
        parsed = self.parse("prochains jours fériés en Tunisie")
        self.assertEqual(parsed["action"], "get_holidays")
        self.assertEqual(parsed["country"], "Tunisie")
        self.assertEqual(self.parse("public holidays")["country"], "")

    def test_currency_grammar(self):
        self.assertEqual(self.parse("convert 100 eur to tnd"),
                         {"action": "convert_currency", "amount": "100",
                          "from_currency": "eur", "to_currency": "tnd"})
        self.assertEqual(self.parse("convertis 50,5 euros en dinars")["amount"], "50.5")
        self.assertIsNone(self.parse("convert my feelings to poetry"))

    def test_registry_lists_all_five_tools(self):
        names = {spec["name"] for spec in kira_agents.tool_catalog()}
        for tool in ("get_weather", "get_holidays", "convert_currency", "tell_joke", "fun_fact"):
            self.assertIn(tool, names)

    def test_network_failure_is_structured_never_raised(self):
        with patch.object(kira_info, "_get_json", side_effect=RuntimeError("offline")):
            result = route("météo à Nabeul", reply_language="fr")
        self.assertFalse(result.get("success", False))
        self.assertEqual(result.get("error_code"), "tool_failed")


if __name__ == "__main__":
    unittest.main()


CRYPTO = {"bitcoin": {"eur": 73953.2, "eur_24h_change": 0.3}}
COINGECKO_META = {"results": [{"name": "Nabeul", "latitude": 36.45, "longitude": 10.73}]}
ALADHAN = {"data": {"timings": {"Fajr": "04:46", "Sunrise": "06:11", "Dhuhr": "12:07",
                                "Asr": "15:29", "Maghrib": "18:02", "Isha": "19:23"},
                    "date": {"hijri": {"date": "19-04-1448", "year": "1448",
                                       "month": {"en": "Rabi al-thani"}}}}}
ITUNES = {"resultCount": 1, "results": [{"trackName": "One More Time", "artistName": "Daft Punk",
                                         "collectionName": "Discovery", "previewUrl": "http://x/1.m4a"}]}
ZEN = [{"q": "Stay hungry.", "a": "Steve Jobs"}]


class CryptoTests(unittest.TestCase):
    def test_price_with_currency_word(self):
        with patch.object(kira_info, "_get_json", return_value=CRYPTO) as get:
            data = kira_info.crypto_price("bitcoin", "eur")
        self.assertEqual(data["price"], 73953.2)
        self.assertEqual(data["change_24h"], 0.3)

    def test_unknown_coin_raises(self):
        with self.assertRaises(ValueError):
            kira_info.crypto_price("mooncoin")

    def test_route_formats_sentence(self):
        with patch.object(kira_info, "_get_json", return_value=CRYPTO):
            result = route("what is the bitcoin price in eur",
                                                   reply_language="en")
        self.assertEqual(result["action"], "crypto_price")
        self.assertTrue(result["success"])
        self.assertIn("Bitcoin", result["response"])


class PrayerTests(unittest.TestCase):
    def test_geocodes_then_timings(self):
        with patch.object(kira_info, "_get_json", side_effect=[COINGECKO_META, ALADHAN]) as get:
            data = kira_info.prayer_times("Nabeul")
        self.assertEqual(data["times"]["Fajr"], "04:46")
        self.assertEqual(data["hijri_year"], "1448")

    def test_route_lists_times(self):
        with patch.object(kira_info, "_get_json", side_effect=[COINGECKO_META, ALADHAN]):
            result = route("heures de prière à Nabeul",
                                                   reply_language="fr")
        self.assertEqual(result["action"], "prayer_times")
        self.assertTrue(result["success"])
        self.assertIn("Fajr 04:46", result["response"])
        self.assertIn("1448", result["response"])


class SongTests(unittest.TestCase):
    def test_search_parses_tracks(self):
        with patch.object(kira_info, "_get_json", return_value=ITUNES):
            data = kira_info.song_search("daft punk")
        self.assertEqual(data["songs"][0]["title"], "One More Time")
        self.assertEqual(data["songs"][0]["artist"], "Daft Punk")

    def test_route_lists_tracks(self):
        with patch.object(kira_info, "_get_json", return_value=ITUNES):
            result = route("cherche la chanson one more time",
                                                   reply_language="fr")
        self.assertEqual(result["action"], "song_search")
        self.assertTrue(result["success"])
        self.assertIn("One More Time — Daft Punk", result["response"])


class QuoteTests(unittest.TestCase):
    def test_quote_parsed(self):
        with patch.object(kira_info, "_get_json", return_value=ZEN):
            data = kira_info.daily_quote()
        self.assertEqual(data["author"], "Steve Jobs")

    def test_route_quotes_with_author(self):
        with patch.object(kira_info, "_get_json", return_value=ZEN):
            result = route("donne-moi une citation",
                                                   reply_language="fr")
        self.assertEqual(result["action"], "daily_quote")
        self.assertIn("Steve Jobs", result["response"])

    def test_briefing_includes_quote(self):
        import kira_scheduler
        with patch.object(kira_info, "daily_quote", return_value={"quote": "Test.", "author": "X"}), \
             patch.object(kira_info, "get_weather", side_effect=Exception("offline")), \
             patch("kira_tasks.list_tasks", return_value=[]), \
             patch.object(kira_info, "get_holidays", return_value={"upcoming": []}):
            text, data = kira_scheduler.briefing("fr")
        self.assertIn("Test.", text)
        self.assertEqual(data["quote"]["author"], "X")


class NewToolRegistrationTests(unittest.TestCase):
    def test_four_new_tools_registered(self):
        kira_agents.ensure_builtins()
        for name in ("crypto_price", "prayer_times", "song_search", "daily_quote"):
            self.assertIn(name, kira_agents._REGISTRY, f"{name} not registered")
