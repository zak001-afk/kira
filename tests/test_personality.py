"""Personality layer: humor levels, greetings, deterministic acks, boot theater."""
import kira_personality


class TestNormalize:
    def test_known_levels_round_trip(self):
        assert kira_personality.normalize("dry") == "dry"
        assert kira_personality.normalize("FORMAL") == "formal"
        assert kira_personality.normalize(" neutral ") == "neutral"
        assert kira_personality.normalize("CHARMING") == "charming"

    def test_default_is_charming(self):
        assert kira_personality.DEFAULT_LEVEL == "charming"

    def test_unknown_falls_back_to_the_default(self):
        assert kira_personality.normalize("sarcastic") == "charming"
        assert kira_personality.normalize(None) == "charming"
        assert kira_personality.normalize("") == "charming"


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

    def test_charming_acknowledgements_are_warm_and_deterministic(self):
        first = kira_personality.done_ack("en", "charming", seed="open chrome")
        second = kira_personality.done_ack("en", "charming", seed="open chrome")
        assert first == second
        assert first in kira_personality._DONE_VARIANTS["en"]["charming"]
        assert any(
            word in first
            for word in ("pleasure", "Right away", "Of course", "happy", "Consider it done")
        )

    def test_charming_acknowledgements_exist_in_every_language(self):
        for language in ("en", "fr", "ar"):
            line = kira_personality.done_ack(language, "charming", seed="x")
            assert isinstance(line, str) and line.strip()

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
    def test_neutral_morning_greeting(self):
        assert kira_personality.greeting(8, humor="neutral") == "Good morning sir."

    def test_neutral_night_greeting(self):
        assert kira_personality.greeting(1, humor="neutral") == "Working late, sir?"

    def test_charming_is_the_default_and_feels_warm(self):
        line = kira_personality.greeting(8)
        assert line.startswith("Good morning sir.")
        assert "hope you slept well" in line

    def test_charming_greetings_cover_every_daypart_and_language(self):
        for hour in (8, 14, 20, 2):
            for language in ("en", "fr", "ar"):
                line = kira_personality.greeting(hour, language, humor="charming")
                assert isinstance(line, str) and line.strip()

    def test_charming_night_greeting_cares(self):
        assert "rest" in kira_personality.greeting(1, humor="charming").lower()

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


class TestFailedReply:
    def test_charming_failure_is_reassuring(self):
        line = kira_personality.failed_reply("en", "charming")
        assert "no trouble at all" in line

    def test_every_level_has_a_distinct_line(self):
        lines = {
            kira_personality.failed_reply("en", level)
            for level in kira_personality.LEVELS
        }
        assert len(lines) == len(kira_personality.LEVELS)

    def test_localized_and_safe_for_unknown_inputs(self):
        assert "بأس" in kira_personality.failed_reply("ar", "charming")
        assert kira_personality.failed_reply("de", "charming")  # falls back to en


class TestBootLinesCharming:
    def test_charming_boot_line_is_welcoming(self):
        counts = {"memories": 0, "learnings": 0, "episodes": 0}
        lines = kira_personality.boot_lines("2.3.1", counts, humor="charming")
        assert "Everything is ready for you" in lines[-1]

    def test_other_levels_keep_their_own_closers(self):
        counts = {"memories": 0, "learnings": 0, "episodes": 0}
        neutral = kira_personality.boot_lines("2.3.1", counts, humor="neutral")
        assert neutral[-1] == "all systems nominal."
        dry = kira_personality.boot_lines("2.3.1", counts, humor="dry")
        assert "as I left it" in dry[-1]
