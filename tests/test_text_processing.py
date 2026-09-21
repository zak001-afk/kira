"""Tests for KIRA's pure text helpers: JSON hygiene, chat cleanup,
language detection, wake-word handling and spoken-reply builders."""


class TestCleanJson:
    def test_strips_code_fence(self, backend):
        assert backend.clean_json('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_extracts_object_from_prose(self, backend):
        assert backend.clean_json('Sure! Here it is: {"a": 1} hope that helps') == '{"a": 1}'

    def test_empty_input(self, backend):
        assert backend.clean_json("") == ""
        assert backend.clean_json(None) == ""


class TestCleanChatResponse:
    def test_removes_think_blocks(self, backend):
        assert backend.clean_chat_response("<think>reasoning here</think>Ready, sir.") == "Ready, sir."

    def test_removes_speaker_prefix(self, backend):
        assert backend.clean_chat_response("KIRA: hello") == "hello"
        assert backend.clean_chat_response("assistant: hi there") == "hi there"

    def test_empty_is_safe(self, backend):
        assert backend.clean_chat_response("") == ""
        assert backend.clean_chat_response(None) == ""


class TestEnsureSir:
    def test_adds_title_when_missing(self, backend):
        assert backend.ensure_sir("Working on it.") == "Certainly, sir. Working on it."

    def test_leaves_existing_title_alone(self, backend):
        assert backend.ensure_sir("Already handled, sir.") == "Already handled, sir."

    def test_empty_string(self, backend):
        assert backend.ensure_sir("") == ""


class TestLanguage:
    def test_detect_french(self, backend):
        assert backend.detect_language("bonjour, ouvre chrome") == "fr"

    def test_detect_arabic(self, backend):
        assert backend.detect_language("افتح المتصفح من فضلك") == "ar"

    def test_detect_english_default(self, backend):
        assert backend.detect_language("open chrome") == "en"

    def test_normalize_for_language_unifies_apostrophes(self, backend):
        assert backend.normalize_for_language("changer d’application") == "changer d'application"


class TestWakeWords:
    def test_strips_wake_word(self, backend):
        assert backend.normalize_command("kira open chrome") == "open chrome"
        assert backend.normalize_command("KIRA open chrome") == "open chrome"
        assert backend.normalize_command("hey kira open chrome") == "open chrome"

    def test_strips_separator_after_wake_word(self, backend):
        assert backend.normalize_command("kira, open chrome") == "open chrome"
        assert backend.normalize_command("kira: open chrome") == "open chrome"

    def test_no_wake_word_kept_as_is(self, backend):
        assert backend.normalize_command("open chrome") == "open chrome"

    def test_empty(self, backend):
        assert backend.normalize_command("") == ""

    def test_is_wake_phrase(self, backend):
        assert backend.is_wake_phrase("hey kira how are you")
        assert not backend.is_wake_phrase("just some words")


class TestChatQuestion:
    def test_question_mark(self, backend):
        assert backend.is_chat_question("how fast is my pc?")

    def test_starters(self, backend):
        assert backend.is_chat_question("tell me about mars")
        assert backend.is_chat_question("pourquoi le ciel est bleu")
        assert backend.is_chat_question("كيف حالك")

    def test_commands_are_not_questions(self, backend):
        assert not backend.is_chat_question("open chrome")


class TestReplies:
    def test_open_app_reply_en(self, backend):
        assert backend.build_reply("en", "open_app", "chrome") == "Opening chrome now sir."

    def test_search_reply_fr(self, backend):
        assert backend.build_reply("fr", "search", "Paris") == "Je cherche Paris maintenant, monsieur."

    def test_lock_reply_ar(self, backend):
        reply = backend.build_reply("ar", "lock_pc")
        assert reply.startswith("سأقفل الكمبيوتر")

    def test_unknown_action_fallback(self, backend):
        assert backend.build_reply("en", "nonexistent-action") == "Done sir."

    def test_failed_action_speaks_kindly(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "personality", {"humor": "charming"})
        assert "no trouble at all" in backend.build_reply("en", "none")
        monkeypatch.setitem(backend.CONFIG, "personality", {"humor": "neutral"})
        assert backend.build_reply("en", "none") == "I couldn't do that, sir."
        monkeypatch.setitem(backend.CONFIG, "personality", {"humor": "formal"})
        assert "regret" in backend.build_reply("en", "none")


class TestAddress:
    def test_preferred_address_default(self, backend):
        assert backend.preferred_address() == "sir"

    def test_preferred_address_from_config(self, backend, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "preferred_address", "commander")
        assert backend.preferred_address() == "Commander"
        # 'sir' in replies is replaced with the custom title
        reply = backend.build_reply("en", "exit")
        assert "Commander" in reply

    def test_address_for_language(self, backend):
        assert backend.address_for_language("fr") == "monsieur"
        assert backend.address_for_language("ar") == "سيدي"

    def test_personalize_address_removes_title_comma(self, backend):
        assert backend.personalize_address("Certainly, sir.") == "Certainly sir."


class TestDescribeAction:
    def test_search(self, backend):
        assert (
            backend.describe_action({"action": "search", "query": "mars"})
            == "search the web for mars"
        )

    def test_press(self, backend):
        assert (
            backend.describe_action({"action": "press", "target": "enter"})
            == "press the enter key"
        )

    def test_non_dict(self, backend):
        assert backend.describe_action(None) == "perform the requested action"
