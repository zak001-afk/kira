"""Planner v1: a model may pick ONE registered tool; it gets no bypass.

Off by default; failures always mean 'just chat', never a user-facing error."""

import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kira_agents
import kira_commands
import kira_planner

ENABLED = {"KIRA_PLANNER": "1", "KIRA_PLANNER_PROVIDER": ""}


class GateTests(unittest.TestCase):
    def test_disabled_by_default_no_model_call(self):
        ask = Mock()
        with patch.dict(os.environ, {"KIRA_PLANNER": ""}):
            self.assertIsNone(kira_planner.plan_command("add a task", ask=ask))
        ask.assert_not_called()

    def test_personal_content_never_reaches_the_model(self):
        ask = Mock()
        with patch.dict(os.environ, ENABLED):
            for text in ["remember my name is Zakaria", "what is my name",
                         "oublie mon nom", "souviens-toi de ça", "اسمي زكريا"]:
                self.assertIsNone(kira_planner.plan_command(text, ask=ask), text)
        ask.assert_not_called()

    def test_provider_defaults_local_and_needs_cloud_ready_for_gemini(self):
        fake_ai = types.SimpleNamespace(cloud_ready=lambda: False,
                                        ensure_env_loaded=lambda path=None: None)
        with patch.dict(os.environ, {"KIRA_PLANNER_PROVIDER": "gemini"}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            self.assertEqual(kira_planner.planner_provider(), "ollama")
        fake_ai = types.SimpleNamespace(cloud_ready=lambda: True,
                                        ensure_env_loaded=lambda path=None: None)
        with patch.dict(os.environ, {"KIRA_PLANNER_PROVIDER": "gemini"}), \
                patch.dict(sys.modules, kira_ai=fake_ai):
            self.assertEqual(kira_planner.planner_provider(), "gemini")


class CatalogAndPromptTests(unittest.TestCase):
    def test_catalog_is_serializable_and_complete(self):
        catalog = kira_agents.tool_catalog()
        names = {spec["name"] for spec in catalog}
        for tool in ("add_todo", "list_tasks", "web_learn", "web_search",
                     "share_project_knowledge", "search_shared_knowledge"):
            self.assertIn(tool, names)
        todo = next(spec for spec in catalog if spec["name"] == "add_todo")
        self.assertEqual(todo["args"]["title"], {"type": "str", "required": True})
        self.assertFalse(todo["consequential"])
        share = next(spec for spec in catalog if spec["name"] == "share_project_knowledge")
        self.assertTrue(share["consequential"])

    def test_prompt_lists_tools_and_demands_json_only(self):
        catalog = kira_agents.tool_catalog()
        prompt = kira_planner.build_planner_prompt(catalog, "add a task buy milk")
        self.assertIn("add_todo", prompt)
        self.assertIn('{"tool": "none"}', prompt)
        self.assertIn("Never invent tool names", prompt)
        self.assertIn("add a task buy milk", prompt)


class ParsePlanTests(unittest.TestCase):
    def setUp(self):
        self.catalog = kira_agents.tool_catalog()

    def test_clean_and_fenced_json_parse(self):
        self.assertEqual(
            kira_planner.parse_plan('{"tool": "add_todo", "args": {"title": "buy milk"}}', self.catalog),
            ("add_todo", {"title": "buy milk"}))
        fenced = 'Sure!\n```json\n{"tool": "list_tasks", "args": {}}\n```'
        self.assertEqual(kira_planner.parse_plan(fenced, self.catalog), ("list_tasks", {}))

    def test_none_unknown_and_garbage_are_rejected(self):
        self.assertIsNone(kira_planner.parse_plan('{"tool": "none"}', self.catalog))
        self.assertIsNone(kira_planner.parse_plan('{"tool": "rm_rf_slash"}', self.catalog))
        self.assertIsNone(kira_planner.parse_plan("I would use add_todo here", self.catalog))
        self.assertIsNone(kira_planner.parse_plan("", self.catalog))
        # Non-dict args degrade to an empty dict; the registry validation
        # will then report any missing required argument.
        self.assertEqual(kira_planner.parse_plan('{"tool": "add_todo", "args": "x"}', self.catalog),
                         ("add_todo", {}))

    def test_model_failure_means_no_plan(self):
        with patch.dict(os.environ, ENABLED):
            self.assertIsNone(kira_planner.plan_command(
                "add a task", ask=Mock(side_effect=RuntimeError("model down"))))


class RoutingTests(unittest.TestCase):
    """process_command: planner plans run through the same gates as typed
    commands; failures fall back to chat."""

    def backend(self):
        return SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=lambda text: {"action": "none"},
            ask_chat=Mock(return_value="chat answer"),
            execute_action=Mock(side_effect=AssertionError("planner must not reach execute_action")),
        )

    def test_planned_web_search_returns_tool_data(self):
        plan = Mock(return_value=("web_search", {"query": "python"}))
        rows = [{"title": "Python", "url": "https://python.org"}]
        fake_web = types.SimpleNamespace(search_web=Mock(return_value=rows))
        with patch.object(kira_planner, "plan_command", plan), \
                patch.dict(sys.modules, kira_web=fake_web):
            result = kira_commands.process_command(self.backend(), "look for python info", reply_language="en")
        self.assertEqual(result["action"], "web_search")
        self.assertTrue(result["success"])

    def test_planned_consequential_tool_still_asks_for_approval(self):
        kira_commands.clear_pending_approval()
        plan = Mock(return_value=("share_project_knowledge",
                                  {"topic": "deploy", "content": "use the bat script"}))
        with patch.object(kira_planner, "plan_command", plan), \
                patch.dict(os.environ, {"KIRA_REQUIRE_APPROVAL": "1"}):
            result = kira_commands.process_command(self.backend(), "publish our deploy steps", reply_language="en")
        self.assertTrue(result.get("needs_approval"))
        self.assertIn("approval_id", result)
        kira_commands.clear_pending_approval()

    def test_no_plan_falls_back_to_chat(self):
        backend = self.backend()
        with patch.object(kira_planner, "plan_command", Mock(return_value=None)):
            result = kira_commands.process_command(backend, "tell me a joke", reply_language="en")
        self.assertEqual(result["action"], "chat")
        self.assertEqual(result["response"], "chat answer")

    def test_failed_planned_tool_falls_back_to_chat(self):
        backend = self.backend()
        plan = Mock(return_value=("web_search", {"query": "python"}))
        fake_web = types.SimpleNamespace(search_web=Mock(side_effect=RuntimeError("no network")))
        with patch.object(kira_planner, "plan_command", plan), \
                patch.dict(sys.modules, kira_web=fake_web):
            result = kira_commands.process_command(backend, "look for python info", reply_language="en")
        self.assertEqual(result["action"], "chat")

    def test_chat_only_route_never_plans(self):
        plan = Mock()
        backend = self.backend()
        with patch.object(kira_planner, "plan_command", plan):
            kira_commands.process_command(backend, "look for python info",
                                          reply_language="en", chat_only=True)
        plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
