"""Routing tests for the feature layer: websites, config aliases, calculator,
reminders, confirmation gating and wake-word enforcement."""

import pytest

import kira_reminders


@pytest.fixture(autouse=True)
def clean_reminders():
    kira_reminders.cancel_all()
    yield
    kira_reminders.cancel_all()


class TestWebsites:
    @pytest.mark.parametrize(
        "command, url",
        [
            ("open github", "https://github.com"),
            ("open gmail", "https://mail.google.com"),
            ("open stack overflow", "https://stackoverflow.com"),
            ("ouvrir netflix", "https://www.netflix.com"),
        ],
    )
    def test_known_sites_open_as_urls(self, backend, command, url):
        assert backend.parse_simple_command(command) == {
            "action": "open_url",
            "target": url,
        }

    def test_french_google_and_youtube_open_the_site(self, backend):
        # regression: these used to become open_app("google"), which has
        # no matching executable and silently failed on Windows
        assert backend.parse_simple_command("ouvrir google") == {
            "action": "open_url",
            "target": "https://www.google.com",
        }
        assert backend.parse_simple_command("ouvrir youtube") == {
            "action": "open_url",
            "target": "https://www.youtube.com",
        }

    def test_user_defined_site(self, backend, monkeypatch):
        monkeypatch.setitem(backend.WEBSITES, "my blog", "https://example.com/blog")
        assert backend.parse_simple_command("open my blog") == {
            "action": "open_url",
            "target": "https://example.com/blog",
        }

    def test_user_defined_app_alias(self, backend, monkeypatch):
        monkeypatch.setitem(backend.APP_ALIASES, "notion", "notion.exe")
        assert backend.parse_simple_command("open notion") == {
            "action": "open_app",
            "target": "notion",
        }
        assert backend.APP_ALIASES["notion"] == "notion.exe"


class TestCalculatorRouting:
    def test_parse(self, backend):
        result = backend.parse_simple_command("calculate 2+2")
        assert result["action"] == "calc"
        assert result["expression"] == "2+2"

    def test_parse_question_form(self, backend):
        result = backend.parse_simple_command("what is 15% of 200")
        assert result["action"] == "calc"
        assert result["expression"] == "15/100*200"

    def test_execute(self, backend):
        reply = backend.execute_action(
            {"action": "calc", "expression": "15/100*200", "language": "en"}
        )
        assert "30" in reply
        assert "sir" in reply

    def test_execute_invalid_expression_reports_failure(self, backend):
        reply = backend.execute_action(
            {"action": "calc", "expression": "banana", "language": "en"}
        )
        assert "could not compute" in reply

    def test_math_questions_beat_chat(self, backend):
        # "what is ..." is a chat pattern, but arithmetic must win
        assert backend.parse_simple_command("what is 7 times 8")["action"] == "calc"
        # …while non-arithmetic questions still fall through to chat
        assert backend.parse_simple_command("what is the weather") is None


class TestReminderRouting:
    def test_parse(self, backend):
        result = backend.parse_simple_command("remind me in 5 minutes to call mom")
        assert result["action"] == "remind"
        assert result["seconds"] == 300
        assert result["text"] == "call mom"

    def test_execute_confirmation_is_spoken(self, backend):
        reply = backend.execute_action(
            {"action": "remind", "seconds": 300, "text": "call mom", "language": "en"}
        )
        assert reply.startswith("I will remind you in 5 minutes")
        assert "call mom" in reply
        assert len(kira_reminders.active()) == 1

    def test_execute_rejects_bad_input(self, backend):
        assert backend.execute_action(
            {"action": "remind", "seconds": 0, "text": "x", "language": "en"}
        ) is False
        assert backend.execute_action(
            {"action": "remind", "seconds": 10, "text": "  ", "language": "en"}
        ) is False

    def test_list_and_clear(self, backend):
        backend.execute_action(
            {"action": "remind", "seconds": 600, "text": "stretch", "language": "en"}
        )
        listing = backend.execute_action(
            {"action": "reminders_list", "language": "en"}
        )
        assert "stretch" in listing

        cleared = backend.execute_action(
            {"action": "reminders_clear", "language": "en"}
        )
        assert "cancelled" in cleared
        assert kira_reminders.active() == []

    def test_list_empty(self, backend):
        reply = backend.execute_action({"action": "reminders_list", "language": "en"})
        assert reply == "You have no active reminders sir."

    def test_parse_list_and_clear_commands(self, backend):
        assert backend.parse_simple_command("list reminders")["action"] == "reminders_list"
        assert backend.parse_simple_command("mes rappels")["action"] == "reminders_list"
        assert backend.parse_simple_command("cancel reminders")["action"] == "reminders_clear"
        assert backend.parse_simple_command("annule les rappels")["action"] == "reminders_clear"


class TestConfirmationGating:
    @pytest.mark.parametrize("action", ["search", "mouse_move", "click", "lock_pc"])
    def test_default_dangerous_actions_require_confirmation(self, backend, action):
        assert backend.requires_confirmation(action)

    @pytest.mark.parametrize("action", ["open_app", "volume_up", "calc", "remind"])
    def test_safe_actions_do_not(self, backend, action):
        assert not backend.requires_confirmation(action)

    def test_configurable_list(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "require_confirmation", ["lock_pc"])
        assert backend.requires_confirmation("lock_pc")
        assert not backend.requires_confirmation("search")

    def test_empty_list_disables_confirmation(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "require_confirmation", [])
        assert not backend.requires_confirmation("lock_pc")


class TestWakeWordGating:
    def test_default_processes_everything(self, backend):
        assert backend.should_process_command("open chrome")
        assert backend.should_process_command("random sentence")
        assert not backend.should_process_command("")

    def test_required_wake_word_filters(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "require_wake_word", True)
        assert not backend.should_process_command("open chrome")
        assert backend.should_process_command("kira open chrome")
        assert backend.should_process_command("hey kira, open chrome")

    def test_conversation_mode_overrides_wake_word(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "require_wake_word", True)
        monkeypatch.setattr(backend, "_CONVERSATION_MODE", True)
        assert backend.should_process_command("open chrome")
