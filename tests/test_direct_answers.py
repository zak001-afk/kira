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
    tree = ast.parse((ROOT / "kira_voice_agent.py").read_text())
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
                "_TIME_QUESTIONS", "_DATE_QUESTIONS", "_MATH_LEADINS", "_MATH_WORDS"}


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


class AskChatWiringTests(unittest.TestCase):
    """direct_answer preempts every model; personal questions skip the cloud."""

    def namespace(self, local=None):
        import kira_commands
        from types import SimpleNamespace
        extra = {
            "kira_commands": kira_commands,
            "kira_language": SimpleNamespace(normalize_language=lambda l, d=None: l or d,
                                             ensure_reply_language=lambda a, l, m: a),
            "kira_memory": SimpleNamespace(save_message=lambda *a, **k: None),
            "call_ollama": Mock(),
            "detect_language": lambda text: "en",
            "_web_lookup": lambda c, l: None,
            "_synthesize_web_answer": lambda c, l, p: None,
            "_ask_chat_response": local or Mock(return_value="local answer"),
            "_CHAT_HISTORY": [],
            "_SESSION_ID": "test",
            "_LAST_REPLY_LANGUAGE": "en",
        }
        return load_names(DIRECT_NAMES | {"ask_chat", "chat_budget", "chat_provider",
                                          "_local_chat_answer", "chat_answer_with_web",
                                          "_run_bounded", "CHAT_ANSWER_BUDGET",
                                          "_cloud_chat_answer", "CLOUD_CHAT_PROMPTS"},
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
