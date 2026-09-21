"""Tests for kira_calculator — safe local arithmetic."""

import pytest

import kira_calculator as calc


class TestTryParse:
    @pytest.mark.parametrize(
        "command, expected",
        [
            ("calculate 2+2", "2+2"),
            ("compute 5 * (3 + 2)", "5*(3+2)"),
            ("calculate twenty five times two", "25*2"),
            ("what is 15% of 200", "15/100*200"),
            ("what's 7 times 8", "7*8"),
            ("how much is 100 divided by 4", "100/4"),
            ("calcule dix fois trois", "10*3"),
            ("combien font deux plus trois", "2+3"),
            ("كم يساوي ١٢ ضرب ٢", "12*2"),
            ("calculate 2 to the power of 10", "2**10"),
            ("calculate pi times two", "pi*2"),
        ],
    )
    def test_parseable(self, command, expected):
        assert calc.try_parse(command) == expected

    @pytest.mark.parametrize(
        "command",
        [
            "",
            "open chrome",
            "what is my name",
            "what is the weather like",
            "search pythagoras",
            "calculate",
            "what is love",
        ],
    )
    def test_not_math(self, command):
        assert calc.try_parse(command) is None


class TestEvaluate:
    @pytest.mark.parametrize(
        "expression, expected",
        [
            ("2+2", 4),
            ("5 * (3 + 2)", 25),
            ("100 / 4", 25.0),
            ("2**10", 1024),
            ("10 % 3", 1),
            ("sqrt(16)", 4.0),
            ("abs(-7)", 7),
            ("round(pi, 2)", 3.14),
        ],
    )
    def test_valid(self, expression, expected):
        # ints and floats compare equal in Python (25.0 == 25)
        assert calc.evaluate(expression) == expected

    @pytest.mark.parametrize(
        "expression",
        [
            "",
            "1/0",
            "banana",
            "__import__('os').system('id')",
            "5 .__class__",
            "().__class__.__bases__",
            "9**9**9",            # exponent bomb
            "open('secret')",
            "'string'",
            "x = 5",
        ],
    )
    def test_rejected(self, expression):
        assert calc.evaluate(expression) is None


class TestFormatAndReply:
    def test_integral_floats_display_as_ints(self):
        assert calc.format_result(4.0) == "4"
        assert calc.format_result(25.0) == "25"

    def test_float_precision_trimmed(self):
        assert calc.format_result(0.1 + 0.2) == "0.3"

    def test_reply_en(self):
        assert calc.calculate_reply("2+2", "en") == "2+2 equals 4, sir."

    def test_reply_localized(self):
        assert calc.calculate_reply("10*3", "fr").endswith("30, monsieur.")
        assert calc.calculate_reply("10*3", "ar").endswith(" سيدي.") or "30" in calc.calculate_reply("10*3", "ar")

    def test_failure_reply(self):
        assert calc.calculate_reply("nonsense", "en") == "I could not compute that, sir."
        assert "calculer" in calc.calculate_reply("nonsense", "fr")
