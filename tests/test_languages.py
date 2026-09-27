"""Language regressions without Ollama, a microphone, SAPI or desktop actions."""
import ast
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import re
import tempfile
from threading import Thread
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import kira_language as language
import kira_commands as commands
import kira_api
import kira_tts
from kira_ui import webview_profile_directory

ROOT = Path(__file__).resolve().parents[1]


class LanguagePolicyTests(unittest.TestCase):
    def test_auto_detects_questions_in_multiple_scripts_and_languages(self):
        examples = {
            "bonjour": "fr", "Bonjour, comment allez-vous ?": "fr",
            "je veu que tu me repandre en francai": "fr",
            "Hello, how are you today?": "en", "Hola, ¿cómo estás?": "es",
            "Wie funktioniert das Internet?": "de", "Привет как дела": "ru",
            "مرحبا كيف حالك": "ar", "你好，今天怎么样？": "zh",
            "こんにちは、元気ですか？": "ja", "안녕하세요 어떻게 지내세요": "ko",
        }
        for text, expected in examples.items():
            with self.subTest(text=text):
                self.assertEqual(language.resolve_reply_language(text, previous="en").language, expected)

    @unittest.skipUnless(language.detector_available(), "langid is optional in minimal previews")
    def test_offline_detector_extends_coverage_beyond_the_three_ui_languages(self):
        for text, expected in [("कृपया मुझे सौर मंडल के बारे में बताएं", "hi"),
                               ("Bom dia, como você está?", "pt"),
                               ("Расскажи мне о Солнечной системе", "ru"),
                               ("¿Puedes explicarme cómo funciona la memoria?", "es")]:
            self.assertEqual(language.resolve_reply_language(text).language, expected)

    def test_explicit_french_request_beats_english_words_and_manual_english(self):
        choice = language.resolve_reply_language("Please reply in French", "en", previous="en")
        self.assertEqual(choice.language, "fr")
        self.assertEqual(choice.preference, "fr")
        self.assertTrue(choice.language_only)
        choice = language.resolve_reply_language("Réponds-moi en français", "en")
        self.assertEqual(choice.locale, "fr-FR")
        self.assertEqual(choice.source, "explicit")

    def test_questions_with_language_instructions_are_not_swallowed_as_settings(self):
        for text in ["Answer in French. What is a black hole?", "Explique le sujet et réponds en français", "Write a poem in French", "Translate hello into French"]:
            choice = language.resolve_reply_language(text)
            self.assertEqual(choice.language, "fr")
            self.assertFalse(choice.language_only)
            self.assertIsNone(choice.preference)
        self.assertEqual(language.resolve_reply_language("Traduis « bonjour » en anglais").language, "en")

    def test_mentions_negations_and_quoted_examples_do_not_set_a_language(self):
        for text in ['What does "reply in French" mean?', "Tell me about France", "Ne réponds pas en anglais"]:
            self.assertEqual(language.language_directive(text), (None, False))

    def test_fixed_language_and_ambiguous_followups_keep_the_correct_context(self):
        self.assertEqual(language.resolve_reply_language("Hello", "fr").language, "fr")
        self.assertEqual(language.resolve_reply_language("ok", previous="ar").language, "ar")
        self.assertEqual(language.resolve_reply_language("42", previous="fr").language, "fr")
        self.assertEqual(language.resolve_reply_language("Hola", previous="fr").language, "es")
        self.assertEqual(language.resolve_reply_language("langue automatique", previous="fr").preference, "auto")

    def test_tts_content_is_not_interpreted_as_an_instruction(self):
        self.assertEqual(language.speech_language('The phrase "reply in French" is an instruction.', "en"), "en")
        self.assertEqual(language.speech_language("Bonjour, je suis Kira.", "auto"), "fr")

    def test_short_english_replies_are_localized_but_identifiers_are_preserved(self):
        model = Mock(side_effect=AssertionError("short known replies should not need a model"))
        self.assertEqual(language.ensure_reply_language("Yes, sir.", "fr", model), "Oui.")
        self.assertEqual(language.ensure_reply_language("Sure.", "ar", model), "نعم.")
        self.assertEqual(language.ensure_reply_language("Python 3.11", "fr", model), "Python 3.11")
        self.assertEqual(language.ensure_reply_language("42", "ja", model), "42")
        self.assertEqual(language.ensure_reply_language("```python\nprint('hello')\n```", "fr", model), "```python\nprint('hello')\n```")

    def test_wrong_language_is_repaired_once_not_silently_spoken_with_wrong_accent(self):
        model = Mock(return_value={"message": {"content": "Le Soleil est une étoile au centre de notre système solaire."}})
        answer = language.ensure_reply_language("The sun is a star at the centre of our solar system.", "fr", model)
        self.assertTrue(answer.startswith("Le Soleil"))
        self.assertEqual(model.call_count, 1)
        self.assertIn("French", model.call_args.kwargs["messages"][0]["content"])
        model.return_value = {"message": {"content": "Je suis KIRA."}}
        self.assertEqual(language.ensure_reply_language("I am KIRA.", "fr", model), "Je suis KIRA.")
        model.return_value = {"message": {"content": "The sun is a star at the centre of our solar system."}}
        with self.assertRaises(language.ReplyLanguageError):
            language.ensure_reply_language("The sun is a star at the centre of our solar system.", "fr", model)


class CommandLanguageTests(unittest.TestCase):
    def backend(self):
        return SimpleNamespace(normalize_command=lambda text: text, parse_simple_command=Mock(return_value=None),
                               ask_chat=Mock(return_value="Une réponse en français."), execute_action=Mock(return_value=True),
                               build_reply=Mock(return_value="The application has been opened successfully."),
                               call_ollama=Mock(return_value={"message": {"content": "L’application a été ouverte avec succès."}}))

    def test_bonjour_and_merci_never_return_the_old_english_sir_greeting(self):
        backend = self.backend()
        self.assertTrue(commands.process_command(backend, "bonjour")["response"].startswith("Bonjour"))
        result = commands.process_command(backend, "merci", previous_language="fr")
        self.assertEqual(result["language"], "fr")
        self.assertEqual(result["response"], "Avec plaisir !")
        backend.ask_chat.assert_not_called()

    def test_language_change_has_no_desktop_side_effect(self):
        backend = self.backend()
        result = commands.process_command(backend, "réponds-moi en français", reply_language="en")
        self.assertEqual(result["reply_language_preference"], "fr")
        self.assertEqual(result["locale"], "fr-FR")
        self.assertIn("français", result["response"])
        backend.parse_simple_command.assert_not_called()
        backend.execute_action.assert_not_called()

    def test_each_chat_turn_receives_its_language_without_cross_language_caching(self):
        backend = self.backend()
        commands.process_command(backend, "Explain gravity", reply_language="fr")
        commands.process_command(backend, "Explain gravity", reply_language="es")
        self.assertEqual([call.kwargs["language"] for call in backend.ask_chat.call_args_list], ["fr", "es"])

    def test_action_executes_once_even_if_its_translation_fails(self):
        backend = self.backend()
        backend.parse_simple_command.return_value = {"action": "open_app", "target": "chrome"}
        backend.call_ollama.side_effect = RuntimeError("model offline")
        result = commands.process_command(backend, "open chrome", reply_language="fr", interface_language="fr")
        self.assertTrue(result["success"])
        self.assertEqual(result["language_warning"], "action_completed_translation_unavailable")
        self.assertEqual(backend.execute_action.call_count, 1)

    def test_chat_endpoint_cannot_trigger_desktop_actions(self):
        backend = self.backend()
        commands.process_command(backend, "open chrome", reply_language="fr", chat_only=True)
        backend.parse_simple_command.assert_not_called()
        backend.execute_action.assert_not_called()
        backend.ask_chat.assert_called_once_with("open chrome", language="fr")

    def test_legacy_callback_is_never_retried_after_a_typeerror(self):
        calls = []
        def handler(text):
            calls.append(text)
            raise TypeError("inside the handler, after a side effect")
        with self.assertRaises(TypeError):
            commands.call_with_options(handler, "hello", reply_language="fr")
        self.assertEqual(calls, ["hello"])


class VoiceLanguageTests(unittest.TestCase):
    def test_neural_voice_matches_the_language_not_the_old_jenny_default(self):
        for code, prefix in [("fr", "fr-FR-"), ("ar", "ar-SA-"), ("es", "es-ES-"), ("de", "de-DE-"), ("ja", "ja-JP-")]:
            self.assertTrue(kira_tts.select_neural_voice("text", "jenny", code).startswith(prefix))
        self.assertEqual(kira_tts.select_neural_voice("hello", "aria", "en"), "en-US-AriaNeural")

    def test_missing_voice_does_not_silently_return_english(self):
        with patch.object(kira_tts, "list_voices", return_value=[]):
            self.assertIsNone(kira_tts.select_neural_voice("Saluton", language="eo"))

    def test_native_voice_selection_handles_windows_ids_and_never_penalizes_french(self):
        english = SimpleNamespace(id="TTS_MS_EN-US_ZIRA", name="Microsoft Zira Desktop", languages=[])
        french = SimpleNamespace(id="TTS_MS_FR-FR_HORTENSE", name="Microsoft Hortense Desktop", languages=[])
        self.assertIs(language.select_installed_voice([english, french], "fr-FR"), french)
        self.assertIsNone(language.select_installed_voice([english], "fr"))
        script = language.sapi_script("Bonjour '); quelque chose", "fr")
        self.assertIn("fr-FR", script)
        self.assertNotIn("Microsoft Zira", script)
        self.assertNotIn("Bonjour", script, "speech text must be encoded, not interpolated as PowerShell")

    def test_native_preferences_have_a_persistent_profile_outside_the_checkout(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"LOCALAPPDATA": tmp}):
            self.assertEqual(webview_profile_directory(), Path(tmp) / "KIRA" / "WebViewProfile")
        source = (ROOT / "main_window.py").read_text()
        self.assertIn("private_mode=False", source)
        self.assertIn("storage_path=str(profile)", source)


class ModelPromptTests(unittest.TestCase):
    def namespace(self, model):
        tree = ast.parse((ROOT / "kira_voice_agent.py").read_text())
        names = {"build_chat_system_prompt", "clean_chat_response", "ask_chat", "_ask_chat_response", "preferred_address", "address_for_language", "detect_language", "chat_answer_with_web", "_web_answer", "_run_bounded", "_web_lookup", "_web_results", "_format_web_results", "_synthesize_web_answer", "WEB_SYNTHESIS_PROMPTS", "chat_budget", "_cloud_chat_answer", "CLOUD_CHAT_PROMPTS", "chat_provider", "_local_chat_answer", "direct_answer", "_is_personal", "_safe_math", "_FR_DAYS", "_FR_MONTHS", "_EN_DAYS", "_EN_MONTHS", "_AR_DAYS", "_AR_MONTHS", "_TIME_QUESTIONS", "_DATE_QUESTIONS", "_MATH_LEADINS", "_MATH_WORDS", "_name_capture", "_NAME_STATEMENTS"}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        nodes += [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in (names | {"CHAT_SYSTEM_PROMPT", "ADDRESS_OPTIONS", "CHAT_ANSWER_BUDGET"}) for target in node.targets)]
        nodes.sort(key=lambda node: node.lineno)  # module order: constants before their users
        saved = []
        import threading
        import time as _time
        namespace = {"re": re, "logging": logging, "kira_language": language, "kira_commands": commands,
                     "refresh_shared_private_terms": lambda: None, "shared_context_for_chat": lambda command: "",
                     "CONFIG": {}, "_CHAT_HISTORY": [], "_SESSION_ID": "test", "call_ollama": model,
                     "threading": threading, "time": _time,
                     "kira_memory": SimpleNamespace(save_message=lambda session, role, text: saved.append((role, text)),
                                                     remember_explicit_fact=lambda text: None, load_memories=lambda: [])}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "voice_agent_language_subset", "exec"), namespace)
        return namespace, saved

    def test_real_model_prompt_selects_french_and_corrects_before_saving_history(self):
        model = Mock(side_effect=[
            {"message": {"content": "The sun is a star at the centre of our solar system."}},
            {"message": {"content": "Le Soleil est une étoile au centre de notre système solaire."}},
        ])
        namespace, saved = self.namespace(model)
        answer = namespace["ask_chat"]("Parle-moi du Soleil", language="fr")
        prompt = model.call_args_list[0].kwargs["messages"][0]["content"]
        self.assertIn("write the entire answer in French", prompt)
        self.assertNotIn("Elegant, concise English", prompt)
        self.assertTrue(answer.startswith("Le Soleil"))
        self.assertEqual(saved[-1], ("assistant", answer))
        self.assertEqual(namespace["_CHAT_HISTORY"][-1]["content"], answer)

    def test_non_french_languages_are_not_mapped_to_english_in_the_system_prompt(self):
        namespace, _ = self.namespace(Mock())
        for code, name in [("es", "Spanish"), ("ja", "Japanese"), ("de", "German"), ("ar", "Arabic")]:
            self.assertIn(f"write the entire answer in {name}", namespace["build_chat_system_prompt"](code))


class LanguageApiTests(unittest.TestCase):
    @contextmanager
    def server(self, backend=None, handler=None):
        with patch.object(kira_api, "_backend", backend), patch.object(kira_api, "_command_handler", handler):
            server = ThreadingHTTPServer(("127.0.0.1", 0), kira_api.KiraAPIHandler)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                yield f"http://127.0.0.1:{server.server_port}"
            finally:
                server.shutdown(); server.server_close(); worker.join()

    def post(self, base, path, data):
        request = Request(base + path, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_language_catalog_and_command_metadata_are_same_origin_ready(self):
        with self.server(backend=SimpleNamespace()) as base:
            with urlopen(base + "/api/languages") as response:
                catalog = json.load(response)
            self.assertIn("fr", [item["code"] for item in catalog["languages"]])
            self.assertFalse(catalog["automatic_microphone_detection"])
            result = self.post(base, "/api/command", {"text": "bonjour", "reply_language": "auto", "interface_language": "fr"})
            self.assertTrue(result["response"].startswith("Bonjour"))
            self.assertEqual(result["locale"], "fr-FR")

    def test_custom_native_handler_receives_language_options(self):
        seen = []
        def handler(text, **options):
            seen.append((text, options))
            return {"response": "Bonjour", "language": "fr", "locale": "fr-FR"}
        with self.server(handler=handler) as base:
            self.post(base, "/api/command", {"text": "hello", "reply_language": "fr", "previous_language": "ar", "interface_language": "fr"})
        self.assertEqual(seen[0][1]["reply_language"], "fr")
        self.assertEqual(len(seen), 1)

    def test_bad_language_values_are_rejected_before_any_command(self):
        handler = Mock()
        with self.server(handler=handler) as base:
            with self.assertRaises(HTTPError) as error:
                self.post(base, "/api/command", {"text": "hello", "reply_language": "en; do something else"})
            self.assertEqual(error.exception.code, 400)
        handler.assert_not_called()

    def test_tts_receives_french_voice_and_returns_word_timing_and_locale(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "test.mp3"; audio.write_bytes(b"fixture audio")
            with patch.object(kira_tts, "generate_speech", return_value=str(audio)) as generate, self.server() as base:
                result = self.post(base, "/api/tts", {"text": "Bonjour, je suis Kira.", "language": "fr-FR", "voice": "jenny"})
            self.assertEqual(generate.call_args.args[1], "fr-FR-DeniseNeural")
            self.assertEqual(generate.call_args.kwargs["language"], "fr")
            self.assertEqual(result["locale"], "fr-FR")
            self.assertEqual(result["language"], "fr")
            self.assertIn("word_timings", result)


if __name__ == "__main__":
    unittest.main()
