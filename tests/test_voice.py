"""Voice selection: warm voices for the charming persona, calm pacing."""
import types

import kira_voice_agent as backend


ARIA = "Microsoft Aria Online (Natural) - English (United States)"
ZIRA = "Microsoft Zira Desktop"
HORTENSE = "Microsoft Hortense Desktop"


class TestVoiceScore:
    def test_charming_prefers_the_sweetest_voice(self):
        assert backend.voice_score(ARIA, "en-us", "charming") > backend.voice_score(
            ZIRA, "en-us", "charming"
        )

    def test_all_charming_tokens_beat_unlisted_names(self):
        assert backend.voice_score("Hazel", "en-us", "charming") > backend.voice_score(
            "David", "en-us", "charming"
        )

    def test_english_language_bonus_and_french_penalty(self):
        assert backend.voice_score("Any", "en-us") > backend.voice_score("Any", "fr-fr")
        assert backend.voice_score("French Voice", "en-us") < backend.voice_score(
            "English Voice", "en-us"
        )

    def test_scores_are_integers(self):
        for humor in ("charming", "neutral", "dry", "formal"):
            assert isinstance(backend.voice_score(ARIA, "en-us", humor), int)


class TestPickVoiceName:
    def test_picks_aria_over_zira(self):
        names = [ZIRA, ARIA, HORTENSE]
        langs = ["en-us", "en-us", "fr-fr"]
        assert backend.pick_voice_name(names, "charming", langs) == ARIA

    def test_falls_back_to_english_voices_when_natural_missing(self):
        assert backend.pick_voice_name([HORTENSE, ZIRA], "charming", ["fr-fr", "en-us"]) == ZIRA

    def test_empty_input_is_safe(self):
        assert backend.pick_voice_name([], "charming", []) is None
        assert backend.pick_voice_name(None, "charming", None) is None


class TestPacing:
    def test_charming_speaks_a_touch_slower(self):
        assert backend.speech_rate("charming") == 160
        assert backend.speech_rate("neutral") == 180
        assert backend.speech_rate("charming") < backend.speech_rate("dry")

    def test_sapi_rate_offset_is_gentler_when_charming(self):
        assert backend.sapi_rate("charming") == -1
        assert backend.sapi_rate("formal") == 0


class TestSapiScript:
    def test_script_tries_candidates_in_order_and_never_crashes(self):
        script = backend.sapi_voice_script("charming")
        assert script.index(backend.SAPI_VOICE_CANDIDATES[0]) < script.index(
            backend.SAPI_VOICE_CANDIDATES[-1]
        )
        assert "try { $speaker.SelectVoice($v); break } catch { }" in script

    def test_first_candidate_is_a_natural_voice(self):
        assert "Natural" in backend.SAPI_VOICE_CANDIDATES[0]


class TestSpokenCommand:
    def _capture(self, backend, monkeypatch):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return types.SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr(backend.subprocess, "run", fake_run)
        return captured

    def test_charming_uses_warm_voice_and_slower_rate(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "personality", {"humor": "charming"})
        captured = self._capture(backend, monkeypatch)
        backend.speak("Good morning sir.")
        assert "Aria" in captured["cmd"][-1]
        assert "Rate = -1" in captured["cmd"][-1]

    def test_neutral_keeps_the_plain_rate(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "personality", {"humor": "neutral"})
        captured = self._capture(backend, monkeypatch)
        backend.speak("Done sir.")
        assert "Rate = 0" in captured["cmd"][-1]
