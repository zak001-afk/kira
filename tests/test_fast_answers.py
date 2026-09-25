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


def load_names(names, extra=None):
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
    wanted.sort(key=lambda node: node.lineno)  # module order: constants before their users
    namespace = {"time": time, "threading": threading}
    namespace.update(extra or {})
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "fast_answers_subset", "exec"), namespace)
    return namespace


class ChatDeadlineTests(unittest.TestCase):
    """chat_answer_with_web: model → web → model → honest timeout."""

    def setUp(self):
        ns = load_names({"CHAT_ANSWER_BUDGET", "chat_answer_with_web", "_run_bounded"})
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

    def test_web_answer_is_reformulated_not_copy_pasted(self):
        raw = "raw snippets"

        def web(command, language):
            return raw, [{"title": "Dell", "body": "result one"}]

        def synthesize(command, language, results):
            return f"Réponse reformulée sur {results[0]['body']}"

        answer, source = self.answer("question", "fr", lambda c, l: None, web, synthesize, budget=2.0)
        self.assertEqual((answer, source), ("Réponse reformulée sur result one", "web"))

    def test_slow_synthesis_falls_back_to_the_raw_text(self):
        def web(command, language):
            return "raw snippets", [{"body": "x"}]

        def synthesize(command, language, results):
            time.sleep(5)
            return "trop tard"

        start = time.monotonic()
        answer, source = self.answer("question", "fr", lambda c, l: None, web, synthesize, budget=1.0)
        self.assertEqual((answer, source), ("raw snippets", "web"))
        self.assertLess(time.monotonic() - start, 1.6)

    def test_failing_synthesis_falls_back_to_the_raw_text(self):
        def web(command, language):
            return "raw snippets", [{"body": "x"}]

        def synthesize(command, language, results):
            raise RuntimeError("model down")

        answer, source = self.answer("question", "fr", lambda c, l: None, web, synthesize, budget=1.0)
        self.assertEqual((answer, source), ("raw snippets", "web"))

    def test_empty_payload_keeps_the_raw_text(self):
        def web(command, language):
            return "raw snippets", []

        answer, _source = self.answer("question", "fr", lambda c, l: None, web,
                                      lambda c, l, r: "never", budget=1.0)
        self.assertEqual(answer, "raw snippets")


class WebAnswerTests(unittest.TestCase):
    def setUp(self):
        def fake_call_ollama(messages, options):
            self.last_prompt = (messages[0]["content"], messages[1]["content"])
            return {"message": {"content": self.model_answer}}

        self.last_prompt = None
        self.model_answer = "Réponse reformulée proprement."

        def clean(text):
            return str(text or "").strip()

        ns = load_names({"_web_answer", "_web_results", "_format_web_results", "_web_lookup",
                         "_synthesize_web_answer", "WEB_SYNTHESIS_PROMPTS"},
                        extra={"call_ollama": fake_call_ollama, "clean_chat_response": clean})
        self.web_answer = ns["_web_answer"]
        self.web_lookup = ns["_web_lookup"]
        self.synthesize = ns["_synthesize_web_answer"]

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

    def test_lookup_returns_text_and_results(self):
        self._install_fake([
            {"title": "Dell", "body": "Entreprise américaine.", "href": "https://dell.com"},
        ])
        found = self.web_lookup("c'est quoi dell", "fr")
        self.assertIsInstance(found, tuple)
        text, results = found
        self.assertIn("Voici ce que j'ai trouvé", text)
        self.assertEqual(len(results), 1)

    def test_synthesis_reformulates_with_a_strict_prompt(self):
        self.model_answer = "  Dell est une entreprise américaine fondée par Michael Dell.  "
        results = [{"title": "Dell", "body": "Entreprise américaine.", "href": "https://dell.com"}]
        answer = self.synthesize("c'est quoi dell", "fr", results)
        self.assertEqual(answer, "Dell est une entreprise américaine fondée par Michael Dell.")
        system_prompt, user_prompt = self.last_prompt
        self.assertIn("Reformule", system_prompt)
        self.assertIn("c'est quoi dell", user_prompt)
        self.assertIn("- Dell: Entreprise américaine.", user_prompt)
        self.assertNotIn("https://dell.com", user_prompt)

    def test_synthesis_without_usable_results_returns_none(self):
        self.assertIsNone(self.synthesize("question", "fr", [{"title": "x", "body": ""}]))


if __name__ == "__main__":
    unittest.main()
