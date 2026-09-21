"""Tests for action execution. pyautogui/pyperclip/psutil are stubbed by
conftest, so these assert *what KIRA decided to do* without touching a real
desktop."""

import sys


def calls():
    return sys.modules["pyautogui"].calls


def set_clipboard(value):
    sys.modules["pyperclip"].value = value


class TestSimpleActions:
    def test_volume_up(self, backend):
        assert backend.execute_action({"action": "volume_up"}) is True
        assert ("press", ("volumeup",), {}) in calls()

    def test_press_key_alias(self, backend):
        assert backend.execute_action({"action": "press", "target": "escape"}) is True
        assert ("press", ("esc",), {}) in calls()

    def test_type_text(self, backend):
        assert backend.execute_action({"action": "type", "text": "hello"}) is True
        assert ("write", ("hello",), {}) in calls()

    def test_type_empty_is_rejected(self, backend):
        assert backend.execute_action({"action": "type", "text": ""}) is False

    def test_window_hotkeys(self, backend):
        assert backend.execute_action({"action": "switch_app"}) is True
        assert ("hotkey", ("alt", "tab"), {}) in calls()

    def test_non_dict_action(self, backend):
        assert backend.execute_action("not-a-dict") is False
        assert backend.execute_action(None) is False

    def test_open_app_resolves_alias_to_executable(self, backend, monkeypatch):
        launched = []
        monkeypatch.setattr("subprocess.Popen", lambda *a, **k: launched.append(a[0]))
        assert backend.open_app("chrome") is True
        assert launched == ["chrome.exe"]


class TestSequences:
    def test_sequence_executes_steps_in_order(self, backend):
        result = backend.execute_action(
            {
                "action": "sequence",
                "steps": [
                    {"action": "volume_up"},
                    {"action": "mute"},
                ],
            }
        )
        assert result == "Completed 2 actions, sir."
        assert calls() == [
            ("press", ("volumeup",), {}),
            ("press", ("volumemute",), {}),
        ]

    def test_empty_sequence_reports_failure(self, backend):
        result = backend.execute_action({"action": "sequence", "steps": []})
        assert "could not determine the sequence" in result

    def test_nested_sequences_are_skipped(self, backend):
        result = backend.execute_action(
            {
                "action": "sequence",
                "steps": [
                    {"action": "sequence", "steps": [{"action": "volume_up"}]},
                    {"action": "mute"},
                ],
            }
        )
        assert result == "Completed 1 action, sir."


class TestBrowserActions:
    def test_open_url_adds_scheme(self, backend, monkeypatch):
        opened = []
        monkeypatch.setattr("webbrowser.open", opened.append)
        assert backend.open_url("example.com") is True
        assert opened == ["https://example.com"]

    def test_search_url_encoding(self, backend, monkeypatch):
        opened = []
        monkeypatch.setattr("webbrowser.open", opened.append)
        assert backend.search_web("hello world") is True
        assert opened[0].startswith("https://www.google.com/search?q=hello+world")

    def test_search_empty_query(self, backend):
        assert backend.search_web("   ") is False


class TestClipboard:
    def test_read_clipboard_content(self, backend):
        set_clipboard("kira rocks")
        assert (
            backend.execute_action({"action": "read_clipboard"})
            == "The clipboard contains: kira rocks"
        )

    def test_read_empty_clipboard(self, backend):
        set_clipboard("")
        # personalize_address() drops the comma before the title
        assert backend.read_clipboard() == "The clipboard is empty sir."


class TestSystemInfo:
    def test_includes_stubbed_metrics(self, backend):
        report = backend.system_info()
        assert "CPU usage: 4%" in report
        assert "Memory usage: 37%" in report
        assert "Battery is at 91 percent" in report


class TestMemoryAction:
    def test_remember_persists(self, backend, memory_db):
        assert backend.execute_action({"action": "remember", "target": "mint tea"})
        assert memory_db.get_memory("user_preference", "general") == "mint tea"

    def test_remember_empty_target_fails(self, backend, memory_db):
        assert backend.execute_action({"action": "remember", "target": "  "}) is False


class TestSetAddress:
    def test_persists_to_config_file(self, backend, tmp_path, speak_silenced, monkeypatch):
        config = tmp_path / "kira_config.json"
        monkeypatch.setattr(backend, "CONFIG_PATH", str(config))
        monkeypatch.setitem(backend.CONFIG, "preferred_address", "sir")

        assert backend.set_address("commander") is True

        import json

        assert json.loads(config.read_text())["preferred_address"] == "commander"

    def test_rejects_unknown_title(self, backend, speak_silenced):
        assert backend.set_address("overlord") is False
