"""Instant common-sense answers: time, date and arithmetic never wait for a
model, and personal questions never reach the cloud."""

import ast
import os
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_names(names, extra=None):
    tree = ast.parse((ROOT / "src/kira/services/kira_voice_agent.py").read_text())
    nodes = [node for node in tree.body
             if (isinstance(node, ast.FunctionDef) and node.name in names)
             or (isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id in names for t in node.targets))]
    nodes.sort(key=lambda node: node.lineno)
    import threading
    import time as _time
    namespace = {"time": _time, "threading": threading}
    namespace.update(extra or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "direct_subset", "exec"), namespace)
    return namespace


DIRECT_NAMES = {"direct_answer", "_safe_math", "_is_personal",
                "_FR_DAYS", "_FR_MONTHS", "_EN_DAYS", "_EN_MONTHS",
                "_AR_DAYS", "_AR_MONTHS",
                "_TIME_QUESTIONS", "_DATE_QUESTIONS", "_MATH_LEADINS", "_MATH_WORDS",
                "_name_capture", "_NAME_STATEMENTS", "_diagnostic_answer", "_cloud_test_answer"}


class DirectAnswerTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_names(DIRECT_NAMES)
        self.direct = self.ns["direct_answer"]

    def test_time_questions_are_answered_instantly(self):
        now = datetime.now()
        for phrase, lang in [("What time is it?", "en"), ("what's the time", "en"),
                             ("Quelle heure est-il ?", "fr"), ("il est quelle heure", "fr"),
                             ("كم الساعة؟", "ar")]:
            answer = self.direct(phrase, lang)
            self.assertIsNotNone(answer, phrase)
            self.assertIn(f"{now:%H}", answer, phrase)

    def test_date_questions_name_the_real_day(self):
        now = datetime.now()
        english = self.direct("What day is it today?", "en")
        self.assertIn(self.ns["_EN_DAYS"][now.weekday()], english)
        self.assertIn(str(now.year), english)
        french = self.direct("Quel jour sommes-nous ?", "fr")
        self.assertIn(self.ns["_FR_DAYS"][now.weekday()], french)
        self.assertIn("quelle est la date", "quelle est la date")  # phrasing variant below
        self.assertIsNotNone(self.direct("quelle est la date d'aujourd'hui", "fr"))
        self.assertIsNotNone(self.direct("What's today's date?", "en"))

    def test_arithmetic_is_computed_not_hallucinated(self):
        self.assertIn("= 100", self.direct("what is 25*4", "en"))
        self.assertIn("= 84", self.direct("Combien font 12 fois 7 ?", "fr"))
        self.assertIn("= 2.5", self.direct("what is 10 divided by 4", "en"))
        self.assertIn("= 11", self.direct("3 plus 4 times 2", "en"))
        self.assertIn("= 8", self.direct("7,5 plus 0,5", "fr"))
        self.assertIn("= 4", self.direct("2+2=", "en"))

    def test_division_by_zero_gets_a_sane_sentence(self):
        self.assertIn("zero", self.direct("what is 5/0", "en").lower())
        self.assertIn("zéro", self.direct("combien font 5/0", "fr"))

    def test_ordinary_chat_is_left_alone(self):
        for phrase in ["tell me a joke", "hello", "what is python",
                       "open chrome", "raconte-moi une histoire", "what is love"]:
            self.assertIsNone(self.direct(phrase, "en"), phrase)

    def test_safe_math_refuses_anything_but_arithmetic(self):
        safe = self.ns["_safe_math"]
        self.assertIsNone(safe("__import__('os').system('dir')"))
        self.assertIsNone(safe("'a'*9999"))
        self.assertIsNone(safe("9**9**9"))
        self.assertEqual(safe("2+2"), 4)


class PersonalGuardTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_names(DIRECT_NAMES)
        self.personal = self.ns["_is_personal"]

    def test_personal_phrases_are_flagged(self):
        for phrase in ["what is my name", "remember my name is Zakaria",
                       "forget my name", "call me Zak", "what did I say?",
                       "what is my favorite language", "je m'appelle Zakaria",
                       "quel est mon nom", "souviens-toi que j'aime le café",
                       "oublie mon nom", "ما اسمي"]:
            self.assertTrue(self.personal(phrase), phrase)

    def test_general_questions_are_not_flagged(self):
        for phrase in ["tell me a joke", "what time is it", "what is python",
                       "raconte-moi une blague", "what is the capital of France"]:
            self.assertFalse(self.personal(phrase), phrase)


class IdentityTests(unittest.TestCase):
    def test_the_persona_never_claims_to_be_jarvis(self):
        source = (ROOT / "src/kira/services/kira_voice_agent.py").read_text()
        start = source.index('CHAT_SYSTEM_PROMPT = """')
        prompt = source[start:source.index('"""', start + 30)]
        self.assertNotIn("modeled after JARVIS", prompt)
        self.assertIn("Your name is KIRA and only KIRA", prompt)
        self.assertIn("Never claim to be JARVIS", prompt)


class NameCaptureTests(unittest.TestCase):
    def namespace(self):
        from types import SimpleNamespace
        saved = []
        extra = {
            "kira_memory": SimpleNamespace(
                save_memory=lambda **kw: saved.append(kw),
                save_message=lambda *a, **k: None),
            "refresh_shared_private_terms": lambda: None,
            "logging": __import__("logging"),
        }
        ns = load_names(DIRECT_NAMES | {"_name_capture"}, extra=extra)
        return ns, saved

    def test_english_name_statement_saves_and_confirms_instantly(self):
        ns, saved = self.namespace()
        reply = ns["_name_capture"]("my name is zakaria", "en")
        self.assertEqual(reply, "Nice to meet you, Zakaria. I will remember your name.")
        self.assertEqual(saved[0]["category"], "identity")
        self.assertEqual(saved[0]["key"], "name")
        self.assertEqual(saved[0]["value"], "Zakaria")

    def test_french_and_arabic_statements_work(self):
        ns, saved = self.namespace()
        reply = ns["_name_capture"]("Je m'appelle Zakaria !", "fr")
        self.assertIn("Zakaria", reply)
        self.assertIn("Enchantée", reply)
        reply = ns["_name_capture"]("اسمي زكريا", "ar")
        self.assertIn("زكريا", reply)
        self.assertEqual(len(saved), 2)

    def test_questions_and_junk_are_not_captured(self):
        ns, saved = self.namespace()
        for phrase in ["what is my name", "my name is", "my name is 12345",
                       "tell me a joke", "my name is a b c d e f"]:
            self.assertIsNone(ns["_name_capture"](phrase, "en"), phrase)
        self.assertEqual(saved, [])


class EnvLoadingTests(unittest.TestCase):
    """.env must work without python-dotenv, with a Notepad BOM and quotes;
    real environment variables always win."""

    def test_env_file_is_parsed_and_never_overrides_real_env(self):
        import tempfile
        import kira_ai
        content = "\ufeffKIRA_TEST_ALPHA=1\n# comment\nKIRA_TEST_BETA=\"quoted value\"\nKIRA_TEST_GAMMA=from-file\nbroken line\n"
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False,
                                         encoding="utf-8") as handle:
            handle.write(content)
            path = handle.name
        try:
            with patch.dict(os.environ, {"KIRA_TEST_GAMMA": "from-real-env"}, clear=False):
                for key in ("KIRA_TEST_ALPHA", "KIRA_TEST_BETA"):
                    os.environ.pop(key, None)
                kira_ai.ensure_env_loaded(path)
                self.assertEqual(os.environ.get("KIRA_TEST_ALPHA"), "1")  # BOM tolerated
                self.assertEqual(os.environ.get("KIRA_TEST_BETA"), "quoted value")
                self.assertEqual(os.environ.get("KIRA_TEST_GAMMA"), "from-real-env")
        finally:
            os.unlink(path)
            for key in ("KIRA_TEST_ALPHA", "KIRA_TEST_BETA"):
                os.environ.pop(key, None)

    def test_missing_file_is_harmless(self):
        import kira_ai
        kira_ai.ensure_env_loaded("/nonexistent/definitely/not/here.env")


class DiagnosticTests(unittest.TestCase):
    def namespace(self, fake_ai):
        extra = {"logging": __import__("logging")}
        ns = load_names(DIRECT_NAMES | {"_diagnostic_answer", "chat_provider",
                                        "chat_budget", "CHAT_ANSWER_BUDGET"}, extra=extra)
        return ns

    def test_cloud_status_reports_ready(self):
        fake_ai = types.SimpleNamespace(ensure_env_loaded=lambda path=None: None,
                                        cloud_enabled=lambda: True,
                                        _gemini_key=lambda: "secret-key",
                                        gemini_model=lambda: "gemini-2.5-flash",
                                        cloud_ready=lambda: True)
        ns = self.namespace(fake_ai)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "gemini", "KIRA_CHAT_BUDGET": "12"}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["_diagnostic_answer"]("cloud status", "en")
        self.assertIn("gemini", answer)
        self.assertIn("ready", answer)
        self.assertIn("12", answer)
        self.assertNotIn("secret-key", answer)  # the key never leaks

    def test_cloud_status_names_the_missing_piece_in_french(self):
        fake_ai = types.SimpleNamespace(ensure_env_loaded=lambda path=None: None,
                                        cloud_enabled=lambda: False,
                                        _gemini_key=lambda: "",
                                        gemini_model=lambda: "gemini-2.5-flash",
                                        cloud_ready=lambda: False)
        ns = self.namespace(fake_ai)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "", "KIRA_CHAT_BUDGET": ""}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["_diagnostic_answer"]("statut cloud", "fr")
        self.assertIn("KIRA_CLOUD_AI", answer)

    def test_other_messages_are_ignored(self):
        ns = self.namespace(None)
        self.assertIsNone(ns["_diagnostic_answer"]("tell me a joke", "en"))
        self.assertIsNone(ns["_diagnostic_answer"]("status", "en"))


class CloudTestCommandTests(unittest.TestCase):
    """'cloud test' proves the Gemini round trip — or names the failure."""

    def namespace(self):
        extra = {"logging": __import__("logging")}
        return load_names(DIRECT_NAMES | {"_cloud_test_answer", "_diagnostic_answer",
                                          "chat_provider", "chat_budget", "_preferred_cloud", "_role_cloud",
                                          "CHAT_ANSWER_BUDGET"}, extra=extra)

    def test_successful_round_trip_reports_latency(self):
        reply = types.SimpleNamespace(ok=True, model="gemini-2.5-flash", elapsed_ms=850,
                                      error="", error_code="")
        fake_ai = types.SimpleNamespace(ensure_env_loaded=lambda path=None: None,
                                        cloud_ready=lambda: True,
                                        chat=Mock(return_value=reply),
                                        CLOUD_PROVIDER="gemini")
        ns = self.namespace()
        with patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["_cloud_test_answer"]("cloud test", "en")
        self.assertIn("850 ms", answer)
        self.assertIn("operational", answer)

    def test_failed_call_names_the_error_code(self):
        reply = types.SimpleNamespace(ok=False, model="", elapsed_ms=0,
                                      error="HTTP 429: quota exceeded", error_code="http_429")
        fake_ai = types.SimpleNamespace(ensure_env_loaded=lambda path=None: None,
                                        cloud_ready=lambda: True,
                                        chat=Mock(return_value=reply),
                                        CLOUD_PROVIDER="gemini")
        ns = self.namespace()
        with patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["_cloud_test_answer"]("cloud test", "en")
        self.assertIn("FAILED", answer)
        self.assertIn("http_429", answer)
        self.assertIn("quota", answer)

    def test_not_ready_falls_back_to_the_status_report(self):
        fake_ai = types.SimpleNamespace(ensure_env_loaded=lambda path=None: None,
                                        cloud_ready=lambda: False,
                                        cloud_enabled=lambda: False,
                                        _gemini_key=lambda: "",
                                        gemini_model=lambda: "gemini-2.5-flash",
                                        chat=Mock(),
                                        CLOUD_PROVIDER="gemini")
        ns = self.namespace()
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "", "KIRA_CHAT_BUDGET": ""}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["_cloud_test_answer"]("cloud test", "en")
        self.assertIn("KIRA_CLOUD_AI", answer)
        fake_ai.chat.assert_not_called()

    def test_other_messages_are_ignored(self):
        ns = self.namespace()
        self.assertIsNone(ns["_cloud_test_answer"]("tell me a joke", "en"))
        self.assertIsNone(ns["_cloud_test_answer"]("test", "en"))


class AskChatWiringTests(unittest.TestCase):
    """direct_answer preempts every model; personal questions skip the cloud."""

    def namespace(self, local=None):
        import kira_commands
        from types import SimpleNamespace
        extra = {
            "kira_commands": kira_commands,
            "kira_language": SimpleNamespace(normalize_language=lambda value, default=None: value or default,
                                             ensure_reply_language=lambda answer, _language, _mode: answer),
            "kira_memory": SimpleNamespace(save_message=lambda *a, **k: None,
                                           save_memory=lambda **kw: None),
            "call_ollama": Mock(),
            "detect_language": lambda text: "en",
            "_web_lookup": lambda _command, _language: None,
            "_synthesize_web_answer": lambda _command, _language, _prompt: None,
            "_ask_chat_response": local or Mock(return_value="local answer"),
            "refresh_shared_private_terms": lambda: None,
            "logging": __import__("logging"),
            "_CHAT_HISTORY": [],
            "_SESSION_ID": "test",
            "_LAST_REPLY_LANGUAGE": "en",
        }
        return load_names(DIRECT_NAMES | {"ask_chat", "chat_budget", "chat_provider",
                                          "_local_chat_answer", "chat_answer_with_web",
                                          "_run_bounded", "CHAT_ANSWER_BUDGET",
                                          "_cloud_chat_answer", "CLOUD_CHAT_PROMPTS", "_preferred_cloud", "_role_cloud"},
                          extra=extra)

    def test_time_question_never_reaches_model_or_cloud(self):
        fake_ai = types.SimpleNamespace(cloud_ready=Mock(return_value=True),
                                        chat=Mock(), CLOUD_PROVIDER="gemini")
        local = Mock(return_value="local answer")
        ns = self.namespace(local=local)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "gemini", "KIRA_CHAT_BUDGET": ""}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["ask_chat"]("what time is it?", language="en")
        self.assertIn(f"{datetime.now():%H}", answer)
        local.assert_not_called()
        fake_ai.chat.assert_not_called()
        self.assertEqual(ns["_CHAT_HISTORY"][-1]["content"], answer)

    def test_math_question_is_instant_and_correct(self):
        fake_ai = types.SimpleNamespace(cloud_ready=Mock(return_value=True),
                                        chat=Mock(), CLOUD_PROVIDER="gemini")
        ns = self.namespace()
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "gemini", "KIRA_CHAT_BUDGET": ""}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["ask_chat"]("what is 25*4", language="en")
        self.assertIn("= 100", answer)
        fake_ai.chat.assert_not_called()

    def test_personal_question_stays_local_even_in_gemini_mode(self):
        fake_ai = types.SimpleNamespace(cloud_ready=Mock(return_value=True),
                                        chat=Mock(), CLOUD_PROVIDER="gemini")
        local = Mock(return_value="Your name is Zakaria.")
        ns = self.namespace(local=local)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "gemini", "KIRA_CHAT_BUDGET": ""}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["ask_chat"]("what is my name?", language="en")
        self.assertEqual(answer, "Your name is Zakaria.")
        fake_ai.chat.assert_not_called()
        local.assert_called_once()

    def test_name_statement_confirms_instantly_without_any_model(self):
        fake_ai = types.SimpleNamespace(cloud_ready=Mock(return_value=True),
                                        chat=Mock(), CLOUD_PROVIDER="gemini")
        local = Mock(return_value="Sir, I'm JARVIS. What can I assist you with today?")
        ns = self.namespace(local=local)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "gemini", "KIRA_CHAT_BUDGET": ""}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["ask_chat"]("my name is zakaria", language="en")
        self.assertEqual(answer, "Nice to meet you, Zakaria. I will remember your name.")
        local.assert_not_called()
        fake_ai.chat.assert_not_called()

    def test_personal_question_never_uses_cloud_rescue_either(self):
        fake_ai = types.SimpleNamespace(cloud_ready=Mock(return_value=True),
                                        chat=Mock(), CLOUD_PROVIDER="gemini")
        slow_local = Mock(return_value=None)  # local finds nothing
        ns = self.namespace(local=slow_local)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "", "KIRA_CHAT_BUDGET": "2"}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            ns["ask_chat"]("forget my name", language="en")
        fake_ai.chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
