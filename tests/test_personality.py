"""Personality layer: humor levels, greetings, deterministic acks, boot theater."""
import kira_personality


class TestNormalize:
    def test_known_levels_round_trip(self):
        assert kira_personality.normalize("dry") == "dry"
        assert kira_personality.normalize("FORMAL") == "formal"
        assert kira_personality.normalize(" neutral ") == "neutral"

    def test_unknown_falls_back_to_neutral(self):
        assert kira_personality.normalize("sarcastic") == "neutral"
        assert kira_personality.normalize(None) == "neutral"
        assert kira_personality.normalize("") == "neutral"


class TestDoneAck:
    def test_neutral_is_the_plain_ack(self):
        assert kira_personality.done_ack("en", "neutral") == "Done sir."

    def test_dry_offers_variants_but_is_deterministic(self):
        first = kira_personality.done_ack("en", "dry", seed="open chrome")
        second = kira_personality.done_ack("en", "dry", seed="open chrome")
        assert first == second
        assert first in kira_personality._DONE_VARIANTS["en"]["dry"]

    def test_formal_tone_distinct(self):
        line = kira_personality.done_ack("en", "formal", seed="save file")
        assert line in kira_personality._DONE_VARIANTS["en"]["formal"]

    def test_all_languages_supported(self):
        for language in ("en", "fr", "ar"):
            for humor in kira_personality.LEVELS:
                line = kira_personality.done_ack(language, humor, seed="x")
                assert isinstance(line, str) and line

    def test_unknown_language_falls_back_to_english(self):
        assert kira_personality.done_ack("de", "neutral") == "Done sir."


class TestDaypart:
    def test_boundaries(self):
        assert kira_personality.daypart(5) == "morning"
        assert kira_personality.daypart(11) == "morning"
        assert kira_personality.daypart(12) == "afternoon"
        assert kira_personality.daypart(16) == "afternoon"
        assert kira_personality.daypart(17) == "evening"
        assert kira_personality.daypart(22) == "evening"
        assert kira_personality.daypart(23) == "night"
        assert kira_personality.daypart(3) == "night"


class TestGreeting:
    def test_morning_greeting(self):
        assert kira_personality.greeting(8) == "Good morning sir."

    def test_night_greeting(self):
        assert kira_personality.greeting(1) == "Working late, sir?"

    def test_dry_humor_appends_flourish_in_english(self):
        line = kira_personality.greeting(8, "en", humor="dry")
        assert line.startswith("Good morning sir.")
        assert len(line) > len("Good morning sir.")

    def test_dry_humor_falls_back_in_other_languages(self):
        # no dry suffix defined for fr/ar → plain greeting
        assert kira_personality.greeting(8, "fr", humor="dry") == "Bonjour monsieur."

    def test_formal_greeting_is_the_base(self):
        assert kira_personality.greeting(20, "en", humor="formal") == "Good evening sir."


class TestBootLines:
    def test_lines_report_version_and_counts(self):
        lines = kira_personality.boot_lines(
            "2.3.0",
            {"memories": 4, "learnings": 2, "episodes": 7, "model": "m", "vision": "v"},
        )
        joined = "\n".join(lines)
        assert "2.3.0" in joined
        assert "4 facts" in joined
        assert "2 skills" in joined
        assert "7 episodes" in joined
        assert "m / vision: v" in joined
        assert "all systems nominal." in joined

    def test_dry_humor_adds_a_closing_line(self):
        counts = {"memories": 0, "learnings": 0, "episodes": 0}
        plain = kira_personality.boot_lines("2.3.0", counts, humor="neutral")
        witty = kira_personality.boot_lines("2.3.0", counts, humor="dry")
        assert len(witty) == len(plain) + 1
        assert "as I left it" in witty[-1]
