"""Specialist registry: validated args, structured failures, honest activity.

The controller architecture starts here: every tool belongs to one agent,
arguments are validated before execution, results are data, and the activity
feed records metadata only (never queries, titles or results).
"""
import types
import unittest
from unittest.mock import Mock, patch

import kira_agents


class RegistryTests(unittest.TestCase):
    def test_builtin_tools_belong_to_the_declared_agents(self):
        kira_agents.ensure_builtins()
        snapshot = {agent["id"]: agent for agent in kira_agents.agents_snapshot()}
        self.assertEqual(set(snapshot), {"research", "memory", "windows", "plugins", "programming"})
        self.assertIn("search_shared_knowledge", snapshot["research"]["tools"])
        self.assertIn("share_project_knowledge", snapshot["research"]["tools"])
        self.assertIn("recall_memory", snapshot["memory"]["tools"])
        for tool in ("add_reminder", "add_todo", "list_tasks", "clear_completed_tasks"):
            self.assertIn(tool, snapshot["windows"]["tools"])

    def test_consequential_flags_mark_outward_changes(self):
        snapshot = {agent["id"]: agent for agent in kira_agents.agents_snapshot()}
        self.assertIn("share_project_knowledge", snapshot["research"]["consequential_tools"])
        self.assertIn("clear_completed_tasks", snapshot["windows"]["consequential_tools"])
        self.assertNotIn("recall_memory", snapshot["memory"]["consequential_tools"])

    def test_direct_tool_actions_are_all_registered(self):
        import kira_commands
        kira_agents.ensure_builtins()
        snapshot = kira_agents.agents_snapshot()
        registered = {tool for agent in snapshot for tool in agent["tools"]}
        self.assertTrue(set(kira_commands.DIRECT_TOOL_ACTIONS) <= registered)

    def test_unknown_agent_is_rejected_at_registration(self):
        with self.assertRaises(ValueError):
            kira_agents.register_tool("t", "skynet", "d", {}, lambda: None)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.handler = Mock(return_value="done")
        kira_agents.register_tool("tmp_tool", "research", "test tool",
                                  {"query": {"type": str, "required": True},
                                   "limit": {"type": int, "required": False}},
                                  self.handler)
        self.addCleanup(kira_agents.unregister_tool, "tmp_tool")

    def test_missing_required_argument_never_runs_the_handler(self):
        result = kira_agents.run("tmp_tool", {"limit": 3})
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_args")
        self.handler.assert_not_called()

    def test_type_coercion_and_unknown_keys_dropped(self):
        result = kira_agents.run("tmp_tool", {"query": "q", "limit": "5", "evil": "x"})
        self.assertTrue(result.ok)
        self.handler.assert_called_once_with(query="q", limit=5)

    def test_uncoercible_argument_is_a_structured_failure(self):
        result = kira_agents.run("tmp_tool", {"query": "q", "limit": "many"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_args")
        self.handler.assert_not_called()

    def test_unknown_tool_is_a_structured_failure(self):
        result = kira_agents.run("no_such_tool", {})
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "unknown_tool")

    def test_handler_exception_stays_structured(self):
        self.handler.side_effect = RuntimeError("boom")
        result = kira_agents.run("tmp_tool", {"query": "q"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "tool_failed")
        self.assertIn("boom", result.error)


class ActivityTests(unittest.TestCase):
    def test_runs_are_recorded_with_metadata_only(self):
        handler = Mock(return_value="secret result about PRIVATE-TOPIC")
        kira_agents.register_tool("tmp_activity", "memory", "test",
                                  {"query": {"type": str, "required": True}}, handler)
        self.addCleanup(kira_agents.unregister_tool, "tmp_activity")
        kira_agents.run("tmp_activity", {"query": "PRIVATE-QUERY"}, source="test")
        entry = kira_agents.recent_activity(1)[0]
        self.assertEqual(entry["tool"], "tmp_activity")
        self.assertEqual(entry["agent"], "memory")
        self.assertTrue(entry["ok"])
        self.assertEqual(entry["source"], "test")
        self.assertGreaterEqual(entry["elapsed_ms"], 0)
        self.assertNotIn("PRIVATE-QUERY", str(entry))   # Content is never stored.
        self.assertNotIn("PRIVATE-TOPIC", str(entry))

    def test_failures_are_recorded_truthfully(self):
        kira_agents.run("no_such_tool_2", {})
        # unknown tools have no spec/agent, so they are not attributed to one
        kira_agents.run("recall_memory", {})  # missing required query
        entry = kira_agents.recent_activity(1)[0]
        self.assertEqual(entry["tool"], "recall_memory")
        self.assertFalse(entry["ok"])
        self.assertEqual(entry["error_code"], "invalid_args")

    def test_snapshot_reports_last_activity_per_agent(self):
        handler = Mock(return_value="x")
        kira_agents.register_tool("tmp_last", "research", "test",
                                  {}, handler)
        self.addCleanup(kira_agents.unregister_tool, "tmp_last")
        kira_agents.run("tmp_last", {})
        snapshot = {agent["id"]: agent for agent in kira_agents.agents_snapshot()}
        self.assertIsNotNone(snapshot["research"]["last_activity"])


class RegistryRoutingTests(unittest.TestCase):
    """The command routes now execute through the registry."""

    def test_shared_search_route_records_research_activity(self):
        import kira_commands
        from types import SimpleNamespace
        backend = SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=Mock(return_value={"action": "search_shared_knowledge", "query": "q"}),
            ask_chat=Mock(), execute_action=Mock(), build_reply=Mock(), call_ollama=Mock())
        web = types.SimpleNamespace(search_shared_knowledge=Mock(return_value="found"))
        with patch.dict("sys.modules", kira_web=web):
            result = kira_commands.process_command(backend, "search shared knowledge for q")
        self.assertTrue(result["success"])
        web.search_shared_knowledge.assert_called_once_with("q", limit=3)
        entry = kira_agents.recent_activity(1)[0]
        self.assertEqual(entry["tool"], "search_shared_knowledge")
        self.assertEqual(entry["agent"], "research")
        self.assertNotIn("q", entry["tool"])  # sanity: metadata only

    def test_api_agents_endpoint_shape(self):
        import kira_api
        handler = object.__new__(kira_api.KiraAPIHandler)
        sent = {}
        handler._send_json = lambda data, status=200: sent.update(payload=data, status=status)
        handler._handle_agents()
        self.assertEqual(sent["status"], 200)
        self.assertIn("agents", sent["payload"])
        self.assertIn("activity", sent["payload"])
        agent_ids = {agent["id"] for agent in sent["payload"]["agents"]}
        self.assertEqual(agent_ids, {"research", "memory", "windows", "plugins", "programming"})


if __name__ == "__main__":
    unittest.main()
