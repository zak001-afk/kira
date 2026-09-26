"""Offline regressions; desktop functions are isolated from Windows imports."""
import ast
import base64
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

from kira_commands import try_web_learning
from kira_speech import clean_for_speech

ROOT = Path(__file__).resolve().parents[1]


def load_function(filename, name, namespace=None):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = namespace if namespace is not None else {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), scope)
    return scope[name]


class RoutingTests(unittest.TestCase):
    def test_all_entry_points_bypass_models(self):
        web = types.SimpleNamespace(search_and_learn=Mock(return_value="Learned"))
        with patch.dict("sys.modules", kira_web=web):
            self.assertEqual(try_web_learning("Learn About Python"), "Learned")
            for filename, name, args in [
                ("main_window.py", "process_command", ("learn about Python",)),
                ("main_window_tk.py", "_route", (object(), "learn about Python")),
                ("kira_voice_agent.py", "ask_chat", ("learn about Python",)),
            ]:
                reply = load_function(filename, name)(*args)
                self.assertEqual(reply.get("response") if isinstance(reply, dict) else reply, "Learned")
            handler = Mock()
            load_function("kira_api.py", "_handle_command", {"_command_handler": None})(handler, {"text": "learn about Python"})
            handler._send_json.assert_called_once_with({"response": "Learned", "action": "web_learn"})

    def test_topic_required_and_private_commands_not_routed(self):
        self.assertIn("What", try_web_learning("learn about"))
        for text in ["remember this password", "memorize my name", "I want to research", "studying"]:
            self.assertIsNone(try_web_learning(text))


class SearchTests(unittest.TestCase):
    def test_empty_and_error_results(self):
        for results, expected in [([], "no web results"), ([{"error": "offline"}], "offline")]:
            fn = load_function("kira_web.py", "search_and_summarize", {"search_web": Mock(return_value=results)})
            self.assertIn(expected, fn("Python", store_memory=True))

    def test_empty_cache_is_retried_and_not_written(self):
        import hashlib
        cache = Mock()
        cache.get.return_value = []
        ddgs = Mock()
        client = ddgs.return_value.__enter__ = Mock(return_value=Mock())
        ddgs.return_value.__exit__ = Mock(return_value=False)
        client.return_value.text.return_value = []
        fn = load_function("kira_web.py", "search_web", {
            "DUCKDUCKGO_AVAILABLE": True, "CACHE_ENABLED": True,
            "web_cache": cache, "hashlib": hashlib, "DDGS": ddgs,
        })
        self.assertEqual(fn("Python"), [])
        client.return_value.text.assert_called_once()
        cache.set.assert_not_called()


class SpeechTests(unittest.TestCase):
    def test_sequences_and_multilingual_text(self):
        self.assertEqual(clean_for_speech("Hi 👩🏽‍💻 🇺🇸 1️⃣ ☀️ ❤️! مرحبا café 123"), "Hi ! مرحبا café 123")
        self.assertEqual(clean_for_speech("👨‍👩‍👧‍👦 ✅"), "")

    def test_windows_fallback_uses_cleaned_text(self):
        engine = Mock()
        subprocess = Mock()
        subprocess.run.side_effect = OSError("not Windows")
        fn = load_function("kira_voice_agent.py", "speak", {
            "personalize_address": lambda text: text, "base64": base64,
            "subprocess": subprocess, "SAPI_VOICE": "test",
            "get_or_create_speech_engine": lambda: engine,
        })
        fn("Hello 👩🏽‍💻")
        engine.say.assert_called_once_with("Hello")
        engine.reset_mock()
        fn("😀")
        engine.say.assert_not_called()

    def test_edge_receives_cleaned_text(self):
        import kira_tts
        with patch.object(kira_tts, "EDGE_TTS_AVAILABLE", True), patch.object(kira_tts, "_generate_speech") as generate:
            self.assertIsNone(kira_tts.generate_speech("😀"))
            generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
