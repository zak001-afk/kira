"""Chat budget: configurable, and the cloud (opt-in) rescues a slow model.

Order inside the budget: local model (~70 %) → cloud (if the user opted in)
→ web → whatever the local model produced → honest timeout. Privacy: the
cloud helper sends ONLY the current question, never history or memories.
"""
import ast
import os
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent


def load_names(names, extra=None):
    tree = ast.parse((ROOT / "src/kira/services/kira_voice_agent.py").read_text(encoding="utf-8"))
    wanted = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            wanted.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in names for t in node.targets):
            wanted.append(node)
    missing = set(names) - {getattr(n, "name", None) for n in wanted} - {
        t.id for n in wanted if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    assert not missing, f"missing in kira_voice_agent.py: {missing}"
    wanted.sort(key=lambda node: node.lineno)
    namespace = {"time": time, "threading": threading}
    namespace.update(extra or {})
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "chat_cloud_subset", "exec"), namespace)
    return namespace


class CloudStageTests(unittest.TestCase):
    def setUp(self):
        ns = load_names({"CHAT_ANSWER_BUDGET", "chat_answer_with_web", "_run_bounded"})
        self.answer = ns["chat_answer_with_web"]

    def test_cloud_rescues_a_slow_model(self):
        def slow_model(_command, _language):
            time.sleep(5)
            return "late"
        cloud = Mock(return_value="Gemini answer.")
        web = Mock(return_value=("web", None))
        text, source = self.answer("q", "en", slow_model, ask_web=web,
                                   budget=3, ask_cloud=cloud)
        self.assertEqual((text, source), ("Gemini answer.", "cloud"))
        web.assert_not_called()   # The cloud answered first; no web snippets.

    def test_fast_local_model_wins_and_cloud_is_never_called(self):
        cloud = Mock(return_value="Gemini answer.")
        text, source = self.answer("q", "en", lambda _command, _language: "local", budget=2,
                                   ask_cloud=cloud)
        self.assertEqual((text, source), ("local", "model"))
        cloud.assert_not_called()

    def test_cloud_failure_falls_back_to_web(self):
        def slow_model(_command, _language):
            time.sleep(5)
            return None
        cloud = Mock(return_value=None)
        web = Mock(return_value=("web text", None))
        text, source = self.answer("q", "en", slow_model, ask_web=web,
                                   budget=1.5, ask_cloud=cloud)
        self.assertEqual((text, source), ("web text", "web"))

    def test_without_cloud_behavior_is_unchanged(self):
        def slow_model(_command, _language):
            time.sleep(5)
            return None
        web = Mock(return_value=("web text", None))
        text, source = self.answer("q", "en", slow_model, ask_web=web, budget=1.2)
        self.assertEqual((text, source), ("web text", "web"))


class ChatBudgetTests(unittest.TestCase):
    def setUp(self):
        ns = load_names({"CHAT_ANSWER_BUDGET", "chat_budget"})
        self.budget = ns["chat_budget"]

    def test_default_is_five_seconds(self):
        with patch.dict(os.environ, {"KIRA_CHAT_BUDGET": ""}):
            self.assertEqual(self.budget(), 5.0)

    def test_env_override_and_clamping(self):
        for raw, expected in [("12", 12.0), ("1", 2.0), ("999", 60.0), ("abc", 5.0)]:
            with patch.dict(os.environ, {"KIRA_CHAT_BUDGET": raw}):
                self.assertEqual(self.budget(), expected, raw)


class CloudChatPrivacyTests(unittest.TestCase):
    def helper(self, fake_ai):
        ns = load_names({"_cloud_chat_answer", "CLOUD_CHAT_PROMPTS", "_preferred_cloud", "chat_provider", "_role_cloud"})
        # The helper imports kira_ai lazily; inject the fake.
        with patch.dict(sys.modules, kira_ai=fake_ai):
            return ns["_cloud_chat_answer"]

    def test_disabled_cloud_returns_none_without_a_call(self):
        fake = types.SimpleNamespace(cloud_ready=Mock(return_value=False),
                                     chat=Mock(), CLOUD_PROVIDER="gemini")
        helper = self.helper(fake)
        with patch.dict(sys.modules, kira_ai=fake):
            self.assertIsNone(helper("hello", "en"))
        fake.chat.assert_not_called()

    def test_only_the_current_question_is_sent(self):
        reply = types.SimpleNamespace(ok=True, text="answer")
        fake = types.SimpleNamespace(cloud_ready=Mock(return_value=True),
                                     chat=Mock(return_value=reply), CLOUD_PROVIDER="gemini")
        helper = self.helper(fake)
        with patch.dict(sys.modules, kira_ai=fake):
            self.assertEqual(helper("what is python?", "fr"), "answer")
        messages = fake.chat.call_args.args[0]
        self.assertEqual(len(messages), 2)                    # system + question only
        self.assertEqual(messages[1]["content"], "what is python?")
        self.assertTrue(messages[0]["content"].startswith("Tu es KIRA"))
        self.assertEqual(fake.chat.call_args.kwargs["provider"], "gemini")

    def test_cloud_errors_never_raise(self):
        fake = types.SimpleNamespace(cloud_ready=Mock(side_effect=RuntimeError("x")),
                                     chat=Mock(), CLOUD_PROVIDER="gemini")
        helper = self.helper(fake)
        with patch.dict(sys.modules, kira_ai=fake):
            self.assertIsNone(helper("hello", "en"))


class ChatProviderTests(unittest.TestCase):
    """KIRA_CHAT_PROVIDER=gemini puts the cloud first; the offline apology
    from the local pipeline can no longer block rescues."""

    def namespace(self, fake_ai, local=None):
        import kira_commands
        from types import SimpleNamespace
        ns_extra = {
            "kira_commands": kira_commands,
            "kira_language": SimpleNamespace(normalize_language=lambda value, default=None: value or default,
                                             ensure_reply_language=lambda answer, _language, _mode: answer),
            "kira_memory": SimpleNamespace(save_message=lambda *a, **k: None),
            "call_ollama": Mock(),
            "detect_language": lambda text: "en",
            "_web_lookup": lambda _command, _language: None,
            "_synthesize_web_answer": lambda _command, _language, _prompt: None,
            "_ask_chat_response": local or Mock(return_value="local answer"),
            "_CHAT_HISTORY": [],
            "_SESSION_ID": "test",
            "_LAST_REPLY_LANGUAGE": "en",
        }
        ns = load_names({"ask_chat", "chat_budget", "chat_provider", "_local_chat_answer",
                         "chat_answer_with_web", "_run_bounded", "CHAT_ANSWER_BUDGET",
                         "_cloud_chat_answer", "CLOUD_CHAT_PROMPTS", "_preferred_cloud", "_role_cloud",
                         "direct_answer", "_is_personal", "_safe_math",
                         "_FR_DAYS", "_FR_MONTHS", "_EN_DAYS", "_EN_MONTHS",
                         "_AR_DAYS", "_AR_MONTHS", "_TIME_QUESTIONS",
                         "_DATE_QUESTIONS", "_MATH_LEADINS", "_MATH_WORDS",
                         "_name_capture", "_NAME_STATEMENTS", "_diagnostic_answer", "_cloud_test_answer"}, extra=ns_extra)
        # _cloud_chat_answer imports kira_ai lazily; patch happens per test.
        return ns

    def test_gemini_first_skips_the_local_model(self):
        reply = types.SimpleNamespace(ok=True, text="A real joke.")
        fake_ai = types.SimpleNamespace(cloud_ready=Mock(return_value=True),
                                        chat=Mock(return_value=reply), CLOUD_PROVIDER="gemini")
        local = Mock(return_value="local answer")
        ns = self.namespace(fake_ai, local=local)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "gemini", "KIRA_CHAT_BUDGET": ""}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["ask_chat"]("tell me a joke", language="en")
        self.assertEqual(answer, "A real joke.")
        local.assert_not_called()
        self.assertEqual(ns["_CHAT_HISTORY"][-1]["content"], "A real joke.")

    def test_gemini_first_falls_back_to_local_when_cloud_fails(self):
        fake_ai = types.SimpleNamespace(cloud_ready=Mock(return_value=False),
                                        chat=Mock(), CLOUD_PROVIDER="gemini")
        ns = self.namespace(fake_ai)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "gemini", "KIRA_CHAT_BUDGET": ""}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["ask_chat"]("tell me a joke", language="en")
        self.assertEqual(answer, "local answer")

    def test_offline_apology_no_longer_blocks_the_cloud_rescue(self):
        import kira_commands
        offline = kira_commands.message("model_offline", "en")
        reply = types.SimpleNamespace(ok=True, text="Cloud saves the day.")
        fake_ai = types.SimpleNamespace(cloud_ready=Mock(return_value=True),
                                        chat=Mock(return_value=reply), CLOUD_PROVIDER="gemini")
        local = Mock(return_value=offline)   # Ollama down -> apology text
        ns = self.namespace(fake_ai, local=local)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "", "KIRA_CHAT_BUDGET": "4"}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            answer = ns["ask_chat"]("tell me a joke", language="en")
        self.assertEqual(answer, "Cloud saves the day.")

    def test_provider_parsing(self):
        ns = load_names({"chat_provider"})
        for raw, expected in [("gemini", "gemini"), ("cloud", "gemini"), ("ollama", "ollama"),
                              ("local", "ollama"), ("", "auto"), ("weird", "auto")]:
            with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": raw}):
                self.assertEqual(ns["chat_provider"](), expected, raw)

    def test_ollama_provider_never_touches_the_cloud(self):
        fake_ai = types.SimpleNamespace(cloud_ready=Mock(return_value=True),
                                        chat=Mock(), CLOUD_PROVIDER="gemini")
        slow_local = Mock(return_value=None)
        ns = self.namespace(fake_ai, local=slow_local)
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": "ollama", "KIRA_CHAT_BUDGET": "2"}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            ns["ask_chat"]("tell me a joke", language="en")
        fake_ai.chat.assert_not_called()


class CloudReadyTests(unittest.TestCase):
    def test_cloud_ready_requires_both_flag_and_key(self):
        import kira_ai
        cases = [({"KIRA_CLOUD_AI": "1", "GEMINI_API_KEY": "k", "GOOGLE_API_KEY": ""}, True),
                 ({"KIRA_CLOUD_AI": "1", "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, False),
                 ({"KIRA_CLOUD_AI": "", "GEMINI_API_KEY": "k", "GOOGLE_API_KEY": ""}, False)]
        for env, expected in cases:
            with patch.dict(os.environ, env):
                self.assertEqual(kira_ai.cloud_ready(), expected, env)


if __name__ == "__main__":
    unittest.main()
