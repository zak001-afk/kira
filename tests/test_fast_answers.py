"""Every question is answered within 5 seconds: local model first, quick
web lookup when it is too slow, honest message when neither makes it.

The answer machinery lives in kira_voice_agent (not importable without
Windows desktop dependencies), so the helpers are executed from their AST,
like the other voice-agent tests.
"""
import ast
import sys
import threading
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_names(names):
    tree = ast.parse((ROOT / "kira_voice_agent.py").read_text())
    wanted = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            wanted.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in names for target in node.targets):
            wanted.append(node)
    missing = set(names) - {getattr(n, "name", None) for n in wanted} - {
        t.id for n in wanted if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    assert not missing, f"missing in kira_voice_agent.py: {missing}"
    namespace = {"time": time, "threading": threading}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "fast_answers_subset", "exec"), namespace)
    return namespace


class ChatDeadlineTests(unittest.TestCase):
    """chat_answer_with_web: model → web → model → honest timeout."""

    def setUp(self):
        ns = load_names({"CHAT_ANSWER_BUDGET", "chat_answer_with_web"})
        self.budget = ns["CHAT_ANSWER_BUDGET"]
        self.answer = ns["chat_answer_with_web"]

    def test_budget_is_five_seconds(self):
        self.assertEqual(self.budget, 5.0)

    def test_fast_model_answers_without_web(self):
        web_calls = []

        def model(command, language):
            return "Bonjour monsieur !"

        def web(command, language):
            web_calls.append(1)
            return "web answer"

        answer, source = self.answer("salut", "fr", model, web, budget=2.0)
        self.assertEqual((answer, source), ("Bonjour monsieur !", "model"))
        self.assertEqual(web_calls, [])

    def test_slow_model_falls_back_to_web_in_time(self):
        def model(command, language):
            time.sleep(1.0)
            return "trop tard"

        answer, source = self.answer("question", "fr", model,
                                     lambda c, l: "Réponse web", budget=1.0)
        self.assertEqual((answer, source), ("Réponse web", "web"))

    def test_web_failure_lets_the_model_finish(self):
        def model(command, language):
            time.sleep(0.9)
            return "réponse modèle"

        start = time.monotonic()
        answer, source = self.answer("question", "fr", model,
                                     lambda c, l: None, budget=1.0)
        elapsed = time.monotonic() - start
        self.assertEqual((answer, source), ("réponse modèle", "model"))
        self.assertLess(elapsed, 1.6, "the budget still bounds the total wait")

    def test_neither_makes_it_returns_timeout(self):
        def model(command, language):
            time.sleep(5)

        start = time.monotonic()
        answer, source = self.answer("question", "fr", model, lambda c, l: None, budget=1.0)
        self.assertEqual((answer, source), ("", "timeout"))
        self.assertLess(time.monotonic() - start, 1.6)


class WebAnswerTests(unittest.TestCase):
    def setUp(self):
        ns = load_names({"_web_answer"})
        self.web_answer = ns["_web_answer"]

    def tearDown(self):
        sys.modules.pop("duckduckgo_search", None)
        sys.modules.pop("ddgs", None)

    @staticmethod
    def _install_fake(results):
        class FakeDDGS:
            def __init__(self, timeout=None):
                self.timeout = timeout

            def text(self, query, max_results=4):
                return list(results)[:max_results]

        module = types.ModuleType("duckduckgo_search")
        module.DDGS = FakeDDGS
        sys.modules["duckduckgo_search"] = module

    def test_french_format_with_sources(self):
        self._install_fake([
            {"title": "Dell", "body": "Dell est une entreprise américaine.", "href": "https://dell.com"},
            {"title": "Dell Technologies", "body": "Fondée par Michael Dell.", "href": "https://dell.tech"},
        ])
        answer = self.web_answer("qu'est-ce que dell", "fr")
        self.assertTrue(answer.startswith("Voici ce que j'ai trouvé sur le web :"))
        self.assertIn("• Dell:", answer)
        self.assertIn("(https://dell.com)", answer)

    def test_no_results_returns_none(self):
        self._install_fake([])
        self.assertIsNone(self.web_answer("question", "fr"))

    def test_missing_package_returns_none(self):
        sys.modules["duckduckgo_search"] = None  # forces ImportError
        sys.modules["ddgs"] = None
        self.assertIsNone(self.web_answer("question", "fr"))


if __name__ == "__main__":
    unittest.main()
