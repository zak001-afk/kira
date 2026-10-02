"""Specialist model roles + the OpenRouter provider: each kind of work can
get its own brain, and one key can front 100+ models. Privacy gates and
self-healing hold for every provider equally."""

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
import kira_planner


def load_names(names, extra=None):
    tree = ast.parse((ROOT / "src/kira/services/kira_voice_agent.py").read_text(encoding="utf-8"))
    nodes = [node for node in tree.body
             if (isinstance(node, ast.FunctionDef) and node.name in names)
             or (isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id in names for t in node.targets))]
    nodes.sort(key=lambda node: node.lineno)
    namespace = dict(extra or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "roles_subset", "exec"), namespace)
    return namespace


def http(status, payload=None, text=""):
    return SimpleNamespace(status_code=status, text=text or str(payload),
                           json=Mock(return_value=payload))


OPENAI_OK = {"choices": [{"message": {"content": "salut"}}]}


class OpenRouterProviderTests(unittest.TestCase):
    ENV = {"KIRA_CLOUD_AI": "1", "OPENROUTER_API_KEY": "sk-or-secret"}

    def test_gates_mirror_the_other_clouds(self):
        with patch.dict(os.environ, {"KIRA_CLOUD_AI": "", "OPENROUTER_API_KEY": "k"}), \
                patch.object(kira_ai.requests, "post") as post:
            self.assertEqual(kira_ai.chat("hi", provider="openrouter").error_code, "cloud_disabled")
        with patch.dict(os.environ, {"KIRA_CLOUD_AI": "1", "OPENROUTER_API_KEY": ""}), \
                patch.object(kira_ai.requests, "post") as post:
            self.assertEqual(kira_ai.chat("hi", provider="openrouter").error_code, "missing_api_key")
        post.assert_not_called()

    def test_success_and_key_hygiene(self):
        with patch.dict(os.environ, self.ENV), \
                patch.object(kira_ai.requests, "post", return_value=http(200, OPENAI_OK)) as post:
            reply = kira_ai.chat("dis salut", provider="openrouter")
        self.assertTrue(reply.ok)
        self.assertEqual(reply.text, "salut")
        self.assertEqual(reply.provider, "openrouter")
        self.assertIn("openrouter.ai", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer sk-or-secret")
        self.assertNotIn("sk-or-secret", post.call_args.args[0])

    def test_error_scrubs_the_key(self):
        with patch.dict(os.environ, self.ENV), \
                patch.object(kira_ai.requests, "post", return_value=http(500, text="x sk-or-secret x")):
            reply = kira_ai.chat("hi", provider="openrouter")
        self.assertNotIn("sk-or-secret", reply.error)
        self.assertIn("***", reply.error)

    def test_retired_model_self_heals_to_a_free_one(self):
        kira_ai._OPENROUTER_RESOLVED["model"] = ""
        dead = http(404, text='{"error": {"message": "No endpoints found for old/model"}}')
        models = http(200, {"data": [{"id": "openai/gpt-4o"},
                                     {"id": "qwen/qwen-2.5-72b:free"},
                                     {"id": "deepseek/deepseek-chat-v3.2:free"}]})
        with patch.dict(os.environ, self.ENV), \
                patch.object(kira_ai.requests, "post", side_effect=[dead, http(200, OPENAI_OK)]), \
                patch.object(kira_ai.requests, "get", return_value=models):
            reply = kira_ai.chat("hi", provider="openrouter", model="old/model")
        self.assertTrue(reply.ok)
        self.assertEqual(reply.model, "deepseek/deepseek-chat-v3.2:free")  # free + deepseek preferred
        kira_ai._OPENROUTER_RESOLVED["model"] = ""

    def test_provider_ready_and_availability(self):
        with patch.dict(os.environ, self.ENV):
            self.assertTrue(kira_ai.provider_ready("openrouter"))
            info = kira_ai.availability()
        self.assertIn("openrouter", info)
        self.assertIn("roles", info)
        self.assertNotIn("sk-or-secret", str(info))


class RoleRouteTests(unittest.TestCase):
    READY = {"KIRA_CLOUD_AI": "1", "GROQ_API_KEY": "k", "GEMINI_API_KEY": "g",
             "GOOGLE_API_KEY": "", "OPENROUTER_API_KEY": ""}

    def test_unset_role_routes_nowhere(self):
        with patch.dict(os.environ, {**self.READY, "KIRA_MODEL_CHAT": ""}):
            self.assertEqual(kira_ai.role_route("chat"), (None, ""))
        self.assertEqual(kira_ai.role_route("no-such-role"), (None, ""))

    def test_provider_and_model_parse(self):
        with patch.dict(os.environ, {**self.READY, "KIRA_MODEL_PLANNER": "groq:llama-3.1-8b-instant"}):
            self.assertEqual(kira_ai.role_route("planner"), ("groq", "llama-3.1-8b-instant"))
        with patch.dict(os.environ, {**self.READY, "KIRA_MODEL_ARABIC": "gemini"}):
            self.assertEqual(kira_ai.role_route("arabic"), ("gemini", ""))

    def test_model_with_colons_survives(self):
        env = {**self.READY, "OPENROUTER_API_KEY": "k",
               "KIRA_MODEL_CODE": "openrouter:qwen/qwen-2.5-coder-32b:free"}
        with patch.dict(os.environ, env):
            self.assertEqual(kira_ai.role_route("code"), ("openrouter", "qwen/qwen-2.5-coder-32b:free"))

    def test_unready_provider_means_no_route(self):
        env = {**self.READY, "OPENROUTER_API_KEY": "", "KIRA_MODEL_CHAT": "openrouter"}
        with patch.dict(os.environ, env):
            self.assertEqual(kira_ai.role_route("chat"), (None, ""))
        with patch.dict(os.environ, {**self.READY, "KIRA_MODEL_CHAT": "nonsense:model"}):
            self.assertEqual(kira_ai.role_route("chat"), (None, ""))


class PlannerRoleTests(unittest.TestCase):
    def test_planner_role_wins_over_legacy_provider(self):
        fake_ai = types.SimpleNamespace(role_route=lambda role: ("groq", "llama-3.1-8b-instant"),
                                        cloud_ready=lambda: True,
                                        ensure_env_loaded=lambda path=None: None)
        with patch.dict(sys.modules, kira_ai=fake_ai), \
                patch.dict(os.environ, {"KIRA_PLANNER_PROVIDER": "gemini"}):
            self.assertEqual(kira_planner.planner_route(), ("groq", "llama-3.1-8b-instant"))

    def test_without_role_the_legacy_choice_stands(self):
        fake_ai = types.SimpleNamespace(role_route=lambda role: (None, ""),
                                        cloud_ready=lambda: True,
                                        ensure_env_loaded=lambda path=None: None)
        with patch.dict(sys.modules, kira_ai=fake_ai), \
                patch.dict(os.environ, {"KIRA_PLANNER_PROVIDER": "gemini"}):
            self.assertEqual(kira_planner.planner_route(), ("gemini", ""))
        with patch.dict(sys.modules, kira_ai=fake_ai), \
                patch.dict(os.environ, {"KIRA_PLANNER_PROVIDER": ""}):
            self.assertEqual(kira_planner.planner_route(), ("ollama", ""))


class ArabicRoleRoutingTests(unittest.TestCase):
    """The whole point: Arabic questions go to the Arabic specialist,
    everything else to the fast chat brain — per question, automatically."""

    def namespace(self):
        return load_names({"_cloud_chat_answer", "CLOUD_CHAT_PROMPTS",
                           "_preferred_cloud", "chat_provider", "_role_cloud"},
                          extra={"os": os})

    def fake(self, routes, chat):
        return types.SimpleNamespace(
            ensure_env_loaded=lambda path=None: None,
            role_route=lambda role: routes.get(role, (None, "")),
            provider_ready=lambda name: name in {"groq", "gemini"},
            cloud_ready=lambda: True, chat=chat)

    def run_one(self, fake_ai, command, language):
        ns = self.namespace()
        with patch.dict(os.environ, {"KIRA_CHAT_PROVIDER": ""}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            return ns["_cloud_chat_answer"](command, language)

    def test_arabic_question_uses_the_arabic_role(self):
        chat = Mock(return_value=SimpleNamespace(ok=True, text="جواب"))
        routes = {"arabic": ("gemini", ""), "chat": ("groq", "")}
        self.assertEqual(self.run_one(self.fake(routes, chat), "ما هي تونس؟", "ar"), "جواب")
        self.assertEqual(chat.call_args.kwargs["provider"], "gemini")

    def test_french_question_uses_the_chat_role(self):
        chat = Mock(return_value=SimpleNamespace(ok=True, text="réponse"))
        routes = {"arabic": ("gemini", ""), "chat": ("groq", "llama-x")}
        self.assertEqual(self.run_one(self.fake(routes, chat), "bonjour ça va ?", "fr"), "réponse")
        self.assertEqual(chat.call_args.kwargs["provider"], "groq")
        self.assertEqual(chat.call_args.kwargs["model"], "llama-x")

    def test_failed_role_falls_over_to_the_next_cloud(self):
        chat = Mock(side_effect=[SimpleNamespace(ok=False, text="", error="quota"),
                                 SimpleNamespace(ok=True, text="secours")])
        routes = {"arabic": ("gemini", ""), "chat": (None, "")}
        self.assertEqual(self.run_one(self.fake(routes, chat), "سؤال", "ar"), "secours")
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(chat.call_args_list[0].kwargs["provider"], "gemini")
        self.assertEqual(chat.call_args_list[1].kwargs["provider"], "groq")

    def test_no_roles_keeps_the_yesterday_behavior(self):
        chat = Mock(return_value=SimpleNamespace(ok=True, text="fast"))
        self.assertEqual(self.run_one(self.fake({}, chat), "hello", "en"), "fast")
        self.assertEqual(chat.call_args.kwargs["provider"], "groq")


if __name__ == "__main__":
    unittest.main()
