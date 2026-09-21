"""Weather (wttr.in, injected opener) and the optional Home Assistant bridge."""
import io
import json

import kira_homeassist
import kira_weather

_SAMPLE = {
    "current_condition": [
        {
            "temp_C": "27",
            "FeelsLikeC": "29",
            "humidity": "55",
            "weatherDesc": [{"value": "Sunny"}],
        }
    ],
    "nearest_area": [{"areaName": [{"value": "Tunis"}]}],
}


class _FakeResponse(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestWeatherParsing:
    def test_detects_weather_commands(self):
        for phrase in (
            "weather",
            "weather in paris",
            "what's the weather",
            "what is the weather like today",
            "météo à paris",
            "الطقس في تونس",
        ):
            assert kira_weather.is_weather_command(phrase), phrase

    def test_search_phrase_stays_a_search(self):
        assert not kira_weather.is_weather_command("search weather in tunis")

    def test_non_weather(self):
        assert not kira_weather.is_weather_command("open chrome")
        assert not kira_weather.is_weather_command("")

    def test_city_extraction(self):
        assert kira_weather.extract_city("weather in tunis") == "tunis"
        assert kira_weather.extract_city("what is the weather in new york?") == "new york"
        assert kira_weather.extract_city("météo à paris") == "paris"
        assert kira_weather.extract_city("الطقس في تونس") == "تونس"
        assert kira_weather.extract_city("weather") == ""  # auto-locate


class TestWeatherReport:
    def test_formats_the_report(self):
        text = kira_weather.format_report(_SAMPLE, "tunis")
        assert "tunis" in text
        assert "Sunny" in text
        assert "27" in text and "humidity 55%" in text

    def test_auto_city_uses_nearest_area(self):
        text = kira_weather.format_report(_SAMPLE, "")
        assert "Tunis" in text

    def test_report_uses_injected_opener(self):
        seen = {}

        def opener(url, timeout=None):
            seen["url"] = url
            return _FakeResponse(_SAMPLE)

        text = kira_weather.report("tunis", opener=opener)
        assert "Sunny" in text
        assert seen["url"] == "https://wttr.in/tunis?format=j1"

    def test_network_failure_falls_back_gracefully(self):
        def broken(url, timeout=None):
            raise OSError("offline")

        assert "could not reach" in kira_weather.report("tunis", opener=broken)
        assert "joindre" in kira_weather.report("paris", "fr", opener=broken)

    def test_localized_reports(self):
        assert "ressenti" in kira_weather.format_report(_SAMPLE, "paris", "fr")
        assert "سيدي" in kira_weather.format_report(_SAMPLE, "تونس", "ar")


class TestHomeAssist:
    def teardown_method(self):
        kira_homeassist.configure(None)

    def test_inert_until_configured(self):
        assert not kira_homeassist.is_configured()
        assert kira_homeassist.find_entity("desk lamp") is None
        reply = kira_homeassist.control("desk lamp", True)
        assert "don't know any device" in reply

    def test_requires_both_url_and_entities(self):
        kira_homeassist.configure({"url": "http://ha:8123"})
        assert not kira_homeassist.is_configured()

    def test_find_entity_by_name_and_alias(self):
        kira_homeassist.configure(
            {
                "url": "http://ha:8123",
                "token": "tok",
                "entities": {"desk lamp": "light.desk", "fan": "switch.fan"},
            }
        )
        assert kira_homeassist.find_entity("desk lamp") == ("light.desk", "desk lamp")
        assert kira_homeassist.find_entity("the desk lamp") == ("light.desk", "desk lamp")
        assert kira_homeassist.find_entity("fan") == ("switch.fan", "fan")
        assert kira_homeassist.find_entity("toaster") is None

    def test_call_service_builds_the_right_request(self):
        kira_homeassist.configure(
            {
                "url": "http://ha:8123/",
                "token": "secret",
                "entities": {"desk lamp": "light.desk"},
            }
        )
        captured = {}

        def opener(request, timeout=None):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse({}, status=200)

        assert kira_homeassist.call_service("light.desk", True, opener=opener)
        assert captured["url"] == "http://ha:8123/api/services/light/turn_on"
        assert captured["method"] == "POST"
        assert captured["auth"] == "Bearer secret"
        assert captured["body"] == {"entity_id": "light.desk"}

    def test_turn_off_uses_the_off_service(self):
        kira_homeassist.configure(
            {"url": "http://ha:8123", "token": "t", "entities": {"fan": "switch.fan"}}
        )
        captured = {}

        def opener(request, timeout=None):
            captured["url"] = request.full_url
            return _FakeResponse({}, status=200)

        assert kira_homeassist.call_service("switch.fan", False, opener=opener)
        assert captured["url"].endswith("/api/services/switch/turn_off")

    def test_control_speaks_success_and_failure(self):
        kira_homeassist.configure(
            {"url": "http://ha:8123", "token": "t", "entities": {"lamp": "light.lamp"}}
        )

        def ok(request, timeout=None):
            return _FakeResponse({}, status=200)

        def broken(request, timeout=None):
            raise OSError("unreachable")

        assert "now on" in kira_homeassist.control("lamp", True, opener=ok)
        assert "now off" in kira_homeassist.control("lamp", False, opener=ok)
        assert "couldn't reach" in kira_homeassist.control("lamp", True, opener=broken)


class TestBackendRouting:
    def test_weather_action_executes(self, backend, speak_silenced, monkeypatch):
        monkeypatch.setattr(
            backend.kira_weather, "report", lambda city, lang="en": f"sunny in {city}"
        )
        reply = backend.execute_action(
            {"action": "weather", "target": "tunis", "language": "en"}
        )
        assert "sunny in tunis" in reply

    def test_home_control_unconfigured_is_honest(self, backend, speak_silenced):
        reply = backend.execute_action(
            {"action": "home_control", "name": "desk lamp", "mode": "on", "language": "en"}
        )
        assert "don't know any device" in reply

    def test_parser_weather_route(self, backend):
        parsed = backend.parse_simple_command("weather in tunis")
        assert parsed["action"] == "weather"
        assert parsed["target"] == "tunis"

    def test_parser_leaves_unknown_home_phrases_alone(self, backend):
        # home control only claims configured entity names; "turn on tv" falls through
        assert backend.parse_simple_command("turn on tv") is None

    def test_parser_routes_configured_entity(self, backend):
        backend.kira_homeassist.configure(
            {
                "url": "http://ha:8123",
                "token": "t",
                "entities": {"kitchen light": "light.kitchen"},
            }
        )
        parsed = backend.parse_simple_command("turn on kitchen light")
        assert parsed["action"] == "home_control"
        assert parsed["name"] == "kitchen light"
        assert parsed["mode"] == "on"

    def test_open_branches_win_over_home_control(self, backend):
        # "open x"/"شغل x" stay app actions even when HA has similar names
        backend.kira_homeassist.configure(
            {"url": "http://ha:8123", "token": "t", "entities": {"chrome": "switch.chrome"}}
        )
        assert backend.parse_simple_command("open chrome")["action"] == "open_app"
        assert backend.parse_simple_command("شغل chrome")["action"] == "open_app"
