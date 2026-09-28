"""Groq: the fast cloud provider. Same privacy gates as Gemini (KIRA_CLOUD_AI
opt-in, key in .env only, scrubbed from errors), same model self-healing."""

import ast
import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kira_ai


def load_names(names, extra=None):
    tree = ast.parse((ROOT / "kira_voice_agent.py").read_text(encoding="utf-8"))
    nodes = [node for node in tree.body
             if (isinstance(node, ast.FunctionDef) and node.name in names)
             or (isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id in names for t in node.targets))]
    nodes.sort(key=lambda node: node.lineno)
    namespace = dict(extra or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "groq_subset", "exec"), namespace)
    return namespace


def http(status, payload=None, text=""):
    return SimpleNamespace(status_code=status, text=text or str(payload),
                           json=Mock(return_value=payload))


GROQ_OK = {"choices": [{"message": {"content": "pong"}}]}


class GateTests(unittest.TestCase):
    def test_groq_refused_without_cloud_opt_in(self):
        with patch.dict(os.environ, {"KIRA_CLOUD_AI": "", "GROQ_API_KEY": "k"}), \
                patch.object(kira_ai.requests, "post") as post:
            reply = kira_ai.chat("hi", provider="groq")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "cloud_disabled")
        post.assert_not_called()

    def test_groq_refused_without_key(self):
        with patch.dict(os.environ, {"KIRA_CLOUD_AI": "1", "GROQ_API_KEY": ""}), \
                patch.object(kira_ai.requests, "post") as post:
            reply = kira_ai.chat("hi", provider="groq")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "missing_api_key")
        post.assert_not_called()

    def test_provider_ready_per_provider(self):
        with patch.dict(os.environ, {"KIRA_CLOUD_AI": "1", "GROQ_API_KEY": "k",
                                     "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
            self.assertTrue(kira_ai.provider_ready("ollama"))
            self.assertTrue(kira_ai.provider_ready("groq"))
            self.assertFalse(kira_ai.provider_ready("gemini"))
            self.assertFalse(kira_ai.provider_ready("nonsense"))


class ChatTests(unittest.TestCase):
    ENV = {"KIRA_CLOUD_AI": "1", "GROQ_API_KEY": "sk-secret-groq"}

    def test_success_uses_bearer_header_and_openai_format(self):
        with patch.dict(os.environ, self.ENV), \
                patch.object(kira_ai.requests, "post", return_value=http(200, GROQ_OK)) as post:
            reply = kira_ai.chat("say pong", provider="groq")
        self.assertTrue(reply.ok)
        self.assertEqual(reply.text, "pong")
        self.assertEqual(reply.provider, "groq")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-secret-groq")
        self.assertIn("api.groq.com", post.call_args.args[0])
        self.assertNotIn("sk-secret-groq", post.call_args.args[0])  # header, never URL
        self.assertEqual(kwargs["json"]["messages"][0]["content"], "say pong")

    def test_key_is_scrubbed_from_errors(self):
        error = http(500, text="boom sk-secret-groq boom")
        with patch.dict(os.environ, self.ENV), \
                patch.object(kira_ai.requests, "post", return_value=error):
            reply = kira_ai.chat("hi", provider="groq")
        self.assertFalse(reply.ok)
        self.assertNotIn("sk-secret-groq", reply.error)
        self.assertIn("***", reply.error)

    def test_decommissioned_model_self_heals_via_discovery(self):
        kira_ai._GROQ_RESOLVED["model"] = ""
        dead = http(400, payload={"error": {"code": "model_decommissioned"}},
                    text='{"error": {"message": "The model `old-llama` has been decommissioned"}}')
        models = http(200, {"data": [{"id": "whisper-large-v3"},
                                     {"id": "llama-3.3-70b-versatile"}]})
        with patch.dict(os.environ, self.ENV), \
                patch.object(kira_ai.requests, "post", side_effect=[dead, http(200, GROQ_OK)]) as post, \
                patch.object(kira_ai.requests, "get", return_value=models):
            reply = kira_ai.chat("hi", provider="groq", model="old-llama")
        self.assertTrue(reply.ok)
        self.assertEqual(reply.model, "llama-3.3-70b-versatile")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(kira_ai.active_groq_model(), "llama-3.3-70b-versatile")
        kira_ai._GROQ_RESOLVED["model"] = ""

    def test_availability_reports_groq_without_key_material(self):
        with patch.dict(os.environ, self.ENV):
            info = kira_ai.availability()
        self.assertIn("groq", info)
        self.assertTrue(info["groq"]["key_present"])
        self.assertNotIn("sk-secret-groq", str(info))


class PreferredCloudTests(unittest.TestCase):
    """Policy: Groq wins when ready unless the user pinned Gemini; one
    missing key never silences the cloud."""

    def helper(self, fake_ai, provider_env=""):
        ns = load_names({"_preferred_cloud", "chat_provider"}, extra={"os": os})
        env = {"KIRA_CHAT_PROVIDER": provider_env}
        def run():
            with patch.dict(os.environ, env), patch.dict(sys.modules, kira_ai=fake_ai):
                return ns["_preferred_cloud"]()
        return run

    def fake(self, groq=True, gemini=True):
        return types.SimpleNamespace(
            ensure_env_loaded=lambda path=None: None,
            provider_ready=lambda name: {"groq": groq, "gemini": gemini}.get(name, False),
            cloud_ready=lambda: gemini)

    def test_auto_prefers_groq_when_ready(self):
        self.assertEqual(self.helper(self.fake(groq=True, gemini=True))(), "groq")

    def test_auto_falls_back_to_gemini_without_groq_key(self):
        self.assertEqual(self.helper(self.fake(groq=False, gemini=True))(), "gemini")

    def test_pinned_gemini_stays_gemini(self):
        self.assertEqual(self.helper(self.fake(True, True), provider_env="gemini")(), "gemini")

    def test_pinned_gemini_still_rescued_by_groq(self):
        self.assertEqual(self.helper(self.fake(True, False), provider_env="gemini")(), "groq")

    def test_nothing_ready_means_none(self):
        self.assertIsNone(self.helper(self.fake(False, False))())

    def test_old_kira_ai_without_provider_ready_degrades_to_gemini(self):
        fake = types.SimpleNamespace(ensure_env_loaded=lambda path=None: None,
                                     cloud_ready=lambda: True)
        self.assertEqual(self.helper(fake)(), "gemini")

    def test_chat_provider_accepts_groq_and_fast(self):
        ns = load_names({"chat_provider"}, extra={"os": os})
        for raw, expected in [("groq", "groq"), ("fast", "groq"), ("gemini", "gemini"),
                              ("cloud", "gemini"), ("local", "ollama"), ("", "auto")]:
            with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": raw}):
                self.assertEqual(ns["chat_provider"](), expected, raw)


if __name__ == "__main__":
    unittest.main()
