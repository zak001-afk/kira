"""Tests for kira_reminders — parsing, scheduling, firing, cancellation."""

import threading
import time

import pytest

import kira_reminders as reminders


@pytest.fixture(autouse=True)
def clean_reminders():
    reminders.cancel_all()
    yield
    reminders.cancel_all()


class TestParseReminder:
    @pytest.mark.parametrize(
        "command, seconds, text",
        [
            ("remind me in 5 minutes to call mom", 300, "call mom"),
            ("remind me to call mom in 5 minutes", 300, "call mom"),
            ("remind me in 1 hour to stretch", 3600, "stretch"),
            ("remind me in 30 seconds to check the oven", 30, "check the oven"),
            ("set a timer for 30 seconds", 30, "the timer finished"),
            ("rappelle-moi dans 2 heures de fermer la session", 7200, "fermer la session"),
            ("rappelle-moi dans 10 minutes de boire de l'eau", 600, "boire de l'eau"),
        ],
    )
    def test_valid_reminders(self, command, seconds, text):
        parsed = reminders.parse_reminder(command)
        assert parsed is not None
        assert parsed["seconds"] == seconds
        assert parsed["text"] == text

    def test_arabic_reminder(self):
        parsed = reminders.parse_reminder("ذكرني بعد 10 دقائق شرب الماء")
        assert parsed is not None
        assert parsed["seconds"] == 600
        assert parsed["text"] == "شرب الماء"
        assert parsed["language"] == "ar"

    def test_number_words(self):
        parsed = reminders.parse_reminder("remind me in five minutes to breathe")
        assert parsed["seconds"] == 300
        assert parsed["text"] == "breathe"

    def test_not_a_reminder(self):
        assert reminders.parse_reminder("open chrome") is None
        assert reminders.parse_reminder("") is None
        assert reminders.parse_reminder("remind me") is None
        assert reminders.parse_reminder("remind me in 5 to do something") is None


class TestHumanize:
    def test_hours(self):
        assert reminders.humanize(3600, "en") == "1 hour"
        assert reminders.humanize(7200, "en") == "2 hours"

    def test_minutes_and_seconds(self):
        assert reminders.humanize(90, "en") == "1 minute 30 seconds"
        assert reminders.humanize(0, "en") == "0 seconds"

    def test_french(self):
        assert reminders.humanize(3600, "fr") == "1 heure"
        assert reminders.humanize(120, "fr") == "2 minutes"


class TestScheduling:
    def test_reminder_fires(self):
        fired = []
        event = threading.Event()

        def on_fire(message):
            fired.append(message)
            event.set()

        reminders.add_reminder(0.05, "call mom", "en", on_fire=on_fire)
        assert event.wait(timeout=2)
        assert fired == ["Reminder, sir: call mom."]
        assert reminders.active() == []

    def test_cancel_prevents_firing(self):
        fired = []
        reminder_id = reminders.add_reminder(0.05, "nope", "en", on_fire=fired.append)
        assert reminders.cancel_reminder(reminder_id)
        time.sleep(0.15)
        assert fired == []

    def test_cancel_unknown_id(self):
        assert not reminders.cancel_reminder(999)

    def test_active_lists_remaining_time(self):
        reminders.add_reminder(3600, "stretch", "en", on_fire=lambda m: None)
        entries = reminders.active()
        assert len(entries) == 1
        assert entries[0]["text"] == "stretch"
        assert 3500 < entries[0]["remaining"] <= 3600

    def test_cancel_all(self):
        reminders.add_reminder(3600, "a", "en")
        reminders.add_reminder(3600, "b", "en")
        assert reminders.cancel_all() == 2
        assert reminders.active() == []


class TestReplies:
    def test_confirmation_localized(self):
        assert "5 minutes" in reminders.confirmation(300, "x", "en")
        assert reminders.confirmation(300, "x", "fr").startswith("Je vous le rappellerai")
        assert reminders.confirmation(300, "x", "ar").startswith("سأذكرك")

    def test_describe_active_empty(self):
        assert reminders.describe_active("en") == "You have no active reminders, sir."
        assert "aucun" in reminders.describe_active("fr")

    def test_describe_active_with_entries(self):
        reminders.add_reminder(300, "call mom", "en", on_fire=lambda m: None)
        description = reminders.describe_active("en")
        assert "call mom" in description
        assert "1 reminder," in description

    def test_cleared_message(self):
        assert reminders.cleared_message(0, "en") == "You have no active reminders, sir."
        assert reminders.cleared_message(2, "en") == "All 2 reminders cancelled, sir."
        assert reminders.cleared_message(1, "en") == "All 1 reminder cancelled, sir."
