"""Tests for kira_voice_agent.parse_simple_command (the deterministic
rule-based command layer that runs before any LLM is asked)."""

import pytest


@pytest.mark.parametrize(
    "command, expected",
    [
        # exit / shutdown
        ("exit", {"action": "exit"}),
        ("quit", {"action": "exit"}),
        ("au revoir", {"action": "exit"}),
        ("خروج", {"action": "exit"}),
        # window management
        ("close window", {"action": "close_window"}),
        ("ferme la fenêtre", {"action": "close_window"}),
        ("اغلق النافذة", {"action": "close_window"}),
        ("minimize window", {"action": "minimize_window"}),
        ("maximize", {"action": "maximize_window"}),
        ("full screen", {"action": "maximize_window"}),
        ("alt tab", {"action": "switch_app"}),
        # desktop / capture
        ("screenshot", {"action": "screenshot"}),
        ("take screenshot", {"action": "screenshot"}),
        ("capture d'écran", {"action": "screenshot"}),
        ("show desktop", {"action": "show_desktop"}),
        ("afficher le bureau", {"action": "show_desktop"}),
        # media & volume
        ("volume up", {"action": "volume_up"}),
        ("louder", {"action": "volume_up"}),
        ("baisse le volume", {"action": "volume_down"}),
        ("mute", {"action": "mute"}),
        ("coupe le son", {"action": "mute"}),
        ("play pause", {"action": "media_play_pause"}),
        ("next track", {"action": "media_next"}),
        ("previous song", {"action": "media_previous"}),
        # security & clipboard
        ("lock pc", {"action": "lock_pc"}),
        ("verrouille", {"action": "lock_pc"}),
        ("copy", {"action": "copy"}),
        ("coller", {"action": "paste"}),
        ("read clipboard", {"action": "read_clipboard"}),
        # info / help / clock
        ("system info", {"action": "system_info"}),
        ("état du système", {"action": "system_info"}),
        ("pc status", {"action": "system_info"}),
        ("help", {"action": "help"}),
        ("مساعدة", {"action": "help"}),
        ("what time is it", {"action": "time"}),
        ("quelle heure est-il", {"action": "time"}),
        ("كم الساعة", {"action": "time"}),
        ("today's date", {"action": "date"}),
        # modes
        ("conversation mode", {"action": "conversation_on"}),
        ("stop conversation", {"action": "conversation_off"}),
        ("clear chat", {"action": "chat_reset"}),
        ("mode conversation", {"action": "conversation_on"}),
        ("command mode", {"action": "mode_info"}),
        # mouse
        ("click", {"action": "click"}),
    ],
)
def test_exact_phrase_commands(backend, command, expected):
    assert backend.parse_simple_command(command) == expected


class TestOpenCommands:
    def test_open_google_maps_to_url(self, backend):
        assert backend.parse_simple_command("open google") == {
            "action": "open_url",
            "target": "https://www.google.com",
        }

    def test_open_youtube_maps_to_url(self, backend):
        assert backend.parse_simple_command("open youtube") == {
            "action": "open_url",
            "target": "https://www.youtube.com",
        }

    def test_open_alias(self, backend):
        assert backend.parse_simple_command("open chrome") == {
            "action": "open_app",
            "target": "chrome",
        }
        assert backend.parse_simple_command("open notepad") == {
            "action": "open_app",
            "target": "notepad",
        }

    def test_open_full_url(self, backend):
        assert backend.parse_simple_command("open https://example.com/docs") == {
            "action": "open_url",
            "target": "https://example.com/docs",
        }

    def test_open_unknown_app_passes_through(self, backend):
        assert backend.parse_simple_command("open obsidian") == {
            "action": "open_app",
            "target": "obsidian",
        }

    def test_open_folder(self, backend):
        assert backend.parse_simple_command("open folder projects") == {
            "action": "open_folder",
            "target": "projects",
        }

    def test_play_prefix(self, backend):
        assert backend.parse_simple_command("play solitaire") == {
            "action": "open_app",
            "target": "solitaire",
        }

    def test_french_open(self, backend):
        assert backend.parse_simple_command("ouvrir notepad") == {
            "action": "open_app",
            "target": "notepad",
        }
        assert backend.parse_simple_command("lancer spotify") == {
            "action": "open_app",
            "target": "spotify",
        }

    def test_arabic_open(self, backend):
        assert backend.parse_simple_command("افتح المفكرة") == {
            "action": "open_app",
            "target": "notepad",
        }
        # "كروم" is itself an APP_ALIASES key; the parser keeps the alias
        # and open_app() resolves it to chrome.exe at execution time.
        result = backend.parse_simple_command("افتح كروم")
        assert result == {"action": "open_app", "target": "كروم"}
        assert backend.APP_ALIASES[result["target"]] == "chrome.exe"

    def test_keyword_fallback(self, backend):
        # bare keyword anywhere in the sentence routes to the app/website
        assert backend.parse_simple_command("show me youtube") == {
            "action": "open_url",
            "target": "https://www.youtube.com",
        }


class TestCombinedCommands:
    def test_open_and_search_becomes_sequence(self, backend):
        result = backend.parse_simple_command("open chrome and search minecraft mods")
        assert result == {
            "action": "sequence",
            "steps": [
                {"action": "open_app", "target": "chrome"},
                {"action": "search", "query": "minecraft mods"},
            ],
        }

    def test_run_shortcut_from_config(self, backend):
        # "work mode" ships in the repository kira_config.json
        assert backend.parse_simple_command("work mode") == {
            "action": "shortcut",
            "target": "work mode",
        }

    def test_custom_shortcut(self, backend, monkeypatch):
        monkeypatch.setitem(
            backend.CONFIG,
            "shortcuts",
            {"focus mode": [{"action": "open_app", "target": "code"}]},
        )
        assert backend.parse_simple_command("focus mode") == {
            "action": "shortcut",
            "target": "focus mode",
        }


class TestTextCommands:
    @pytest.mark.parametrize(
        "command, expected",
        [
            ("search weather in tunis", {"action": "search", "query": "weather in tunis"}),
            ("recherche la météo", {"action": "search", "query": "la météo"}),
            ("ابحث عن الطقس", {"action": "search", "query": "الطقس"}),
            ("type hello world", {"action": "type", "text": "hello world"}),
            ("écris bonjour le monde", {"action": "type", "text": "bonjour le monde"}),
            ("اكتب مرحبا", {"action": "type", "text": "مرحبا"}),
            ("press enter", {"action": "press", "target": "enter"}),
            ("appuie entrée", {"action": "press", "target": "entrée"}),
            ("اضغط مسافة", {"action": "press", "target": "مسافة"}),
        ],
    )
    def test_parameterized_commands(self, backend, command, expected):
        assert backend.parse_simple_command(command) == expected


class TestMemoryCommands:
    def test_remember_default_browser(self, backend, memory_db):
        result = backend.parse_simple_command("remember my browser is firefox")
        assert result == {"action": "remember", "target": "default_browser=firefox"}
        assert backend.USER_MEMORY["default_browser"] == "firefox"

    def test_generic_remember(self, backend):
        result = backend.parse_simple_command("remember I like mint tea")
        assert result == {"action": "remember", "target": "I like mint tea"}

    def test_set_address(self, backend):
        assert backend.parse_simple_command("call me commander") == {
            "action": "set_address",
            "target": "commander",
        }

    def test_set_address_rejects_unknown_title(self, backend):
        assert backend.parse_simple_command("call me zaphod") is None


class TestUnrecognized:
    @pytest.mark.parametrize(
        "command",
        [
            "",
            "   ",
            "search",
            "press",
            "hello there",
            "what is the weather like today",
            "tell me a joke",
        ],
    )
    def test_returns_none(self, backend, command):
        assert backend.parse_simple_command(command) is None
