"""Morning briefing composition: greeting, clock, battery, reminder counts."""
from datetime import datetime

import kira_briefing
import kira_reminders


def _clear_reminders():
    kira_reminders.cancel_all()


class TestBriefing:
    def setup_method(self):
        _clear_reminders()

    def teardown_method(self):
        _clear_reminders()

    def test_contains_greeting_clock_and_date(self):
        text = kira_briefing.briefing(
            language="en", now=datetime(2026, 9, 21, 8, 30)
        )
        assert text.startswith("Good morning sir.")
        assert "08:30" in text
        assert "September" in text

    def test_battery_included_when_provided(self):
        text = kira_briefing.briefing(
            language="en", battery_percent=84.0, now=datetime(2026, 9, 21, 8, 30)
        )
        assert "battery is at 84 percent" in text

    def test_battery_omitted_when_none(self):
        text = kira_briefing.briefing(
            language="en", now=datetime(2026, 9, 21, 8, 30)
        )
        assert "battery" not in text.lower()

    def test_pending_reminders_are_counted(self):
        kira_reminders.add_reminder(600, "call the lab")
        text = kira_briefing.briefing(language="en", now=datetime(2026, 9, 21, 8, 30))
        assert "1 reminder pending" in text

    def test_french_and_arabic_variants(self):
        fr = kira_briefing.briefing(language="fr", now=datetime(2026, 9, 21, 8, 30))
        assert fr.startswith("Bonjour monsieur.")
        ar = kira_briefing.briefing(language="ar", battery_percent=50.0,
                                    now=datetime(2026, 9, 21, 8, 30))
        assert "البطارية" in ar

    def test_dry_humor_flows_through_greeting(self):
        text = kira_briefing.briefing(language="en", humor="dry",
                                      now=datetime(2026, 9, 21, 8, 30))
        assert "less chaos than yesterday" in text
