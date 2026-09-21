"""Command routing for the suit-mode operator phrases (EN/FR/AR)."""
import pytest


class TestParserPhrases:
    @pytest.mark.parametrize(
        ("phrase", "action"),
        [
            ("enable watchdog", "monitor_on"),
            ("watch the systems", "monitor_on"),
            ("démarre la surveillance", "monitor_on"),
            ("شغل المراقبة", "monitor_on"),
            ("disable watchdog", "monitor_off"),
            ("arrête la surveillance", "monitor_off"),
            ("أوقف المراقبة", "monitor_off"),
            ("eyes down", "privacy_blur"),
            ("privacy mode", "privacy_blur"),
            ("وضع الخصوصية", "privacy_blur"),
            ("secure the lab", "secure_lab"),
            ("lockdown", "secure_lab"),
            ("verrouille le labo", "secure_lab"),
            ("أمّن المختبر", "secure_lab"),
            ("take that back", "undo_last"),
            ("undo", "undo_last"),
            ("annule ça", "undo_last"),
            ("تراجع", "undo_last"),
        ],
    )
    def test_exact_phrases_route(self, backend, phrase, action):
        parsed = backend.parse_simple_command(phrase)
        assert parsed and parsed["action"] == action
        assert parsed.get("language") in {"en", "fr", "ar"}

    def test_unlock_command_carries_the_verdict(self, backend):
        parsed = backend.parse_simple_command("unlock the lab")
        assert parsed["action"] == "unlock_lab"
        assert parsed["verdict"] == "unlock"

    def test_unlock_with_passphrase_denies_when_wrong(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "lab_passphrase", "jarvis")
        assert backend.parse_simple_command("unlock the lab nope")["verdict"] == "deny"
        assert backend.parse_simple_command("unlock the lab jarvis")["verdict"] == (
            "unlock"
        )

    def test_normal_conversation_is_not_claimed(self, backend):
        for phrase in ("open chrome", "what time is it", "tell me a joke"):
            parsed = backend.parse_simple_command(phrase)
            assert parsed is None or parsed["action"] not in {
                "monitor_on",
                "monitor_off",
                "privacy_blur",
                "secure_lab",
                "undo_last",
            }


class TestExecutorRunners:
    def test_watchdog_starts_and_stops(self, backend, speak_silenced):
        reply = backend.execute_action({"action": "monitor_on", "language": "en"})
        assert "Watchdog engaged" in reply
        assert backend.kira_monitor._watchdog is not None
        reply = backend.execute_action({"action": "monitor_off", "language": "en"})
        assert "disengaged" in reply
        assert backend.kira_monitor._watchdog is None

    def test_watchdog_respects_disabled_config(
        self, backend, speak_silenced, monkeypatch
    ):
        monkeypatch.setitem(backend.CONFIG, "monitor", {"enabled": False})
        backend.execute_action({"action": "monitor_on", "language": "en"})
        assert backend.kira_monitor._watchdog is None

    def test_watchdog_sampler_reads_the_stub(self, backend):
        reading = backend._sample_suit_telemetry()
        assert reading.cpu_percent == 4.0
        assert reading.memory_percent == 37.0
        assert reading.battery_percent == 91.0
        assert reading.battery_plugged is True

    def test_background_tasks_start_the_watchdog(self, backend, speak_silenced):
        backend.start_background_tasks()
        assert backend.kira_monitor._watchdog is not None

    def test_humor_configuration_is_read_safely(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "personality", {"humor": "dry"})
        assert backend._humor() == "dry"
        monkeypatch.setitem(backend.CONFIG, "personality", {"humor": "neutral"})
        assert backend._humor() == "neutral"
        # missing or bogus personality falls back to the charming default
        monkeypatch.setitem(backend.CONFIG, "personality", None)
        assert backend._humor() == "charming"
        monkeypatch.setitem(backend.CONFIG, "personality", {"humor": "bogus"})
        assert backend._humor() == "charming"
