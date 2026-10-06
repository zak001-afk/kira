"""Consequential tools require conversational approval before they run.

Default behavior (KIRA_REQUIRE_APPROVAL unset): share_project_knowledge and
clear_completed_tasks are parked, the user is asked in their language, and
only "confirm" executes the parked call. Anything else expires the question.
The gate can be disabled explicitly with KIRA_REQUIRE_APPROVAL=0.
"""
import os
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import kira_agents
import kira_commands as commands


def make_backend(parsed):
    return SimpleNamespace(
        normalize_command=lambda text: text,
        parse_simple_command=Mock(return_value=parsed),
        ask_chat=Mock(return_value="chat"),
        execute_action=Mock(return_value=True),
        build_reply=Mock(return_value="Done."),
        call_ollama=Mock(return_value={"message": {"content": "x"}}),
    )


SHARE_PARSED = {"action": "share_project_knowledge", "kind": "project_knowledge",
                "topic": "deploy", "content": "use the bat script"}


class ApprovalFlowTests(unittest.TestCase):
    def setUp(self):
        commands.clear_pending_approval()
        self.addCleanup(commands.clear_pending_approval)

    def share_web(self):
        return types.SimpleNamespace(
            share_project_knowledge=Mock(return_value="I've shared that project knowledge about 'deploy'."))

    def test_share_is_parked_not_executed(self):
        backend = make_backend(SHARE_PARSED)
        web = self.share_web()
        with patch.dict("sys.modules", kira_web=web):
            result = commands.process_command(backend, "share knowledge deploy: use the bat script")
        self.assertFalse(result["success"])
        self.assertTrue(result["needs_approval"])
        self.assertIn("approval_id", result)
        self.assertIn("confirmation", result["response"])
        web.share_project_knowledge.assert_not_called()   # Nothing ran yet.
        backend.execute_action.assert_not_called()

    def test_confirm_executes_the_parked_call(self):
        backend = make_backend(SHARE_PARSED)
        web = self.share_web()
        with patch.dict("sys.modules", kira_web=web):
            commands.process_command(backend, "share knowledge deploy: use the bat script")
            confirm_backend = make_backend(None)  # parse must not even be consulted
            result = commands.process_command(confirm_backend, "confirm")
        self.assertTrue(result["success"])
        self.assertIn("deploy", result["response"])
        web.share_project_knowledge.assert_called_once_with("deploy", "use the bat script")
        confirm_backend.parse_simple_command.assert_not_called()

    def test_cancel_discards_and_nothing_runs(self):
        backend = make_backend(SHARE_PARSED)
        web = self.share_web()
        with patch.dict("sys.modules", kira_web=web):
            commands.process_command(backend, "share knowledge deploy: use the bat script")
            result = commands.process_command(make_backend(None), "cancel")
        self.assertFalse(result["success"])
        self.assertEqual(result["approval"], "rejected")
        self.assertIn("nothing was changed", result["response"].lower())
        web.share_project_knowledge.assert_not_called()

    def test_unrelated_message_expires_the_question(self):
        backend = make_backend(SHARE_PARSED)
        web = self.share_web()
        with patch.dict("sys.modules", kira_web=web):
            commands.process_command(backend, "share knowledge deploy: use the bat script")
            chat_backend = make_backend(None)
            commands.process_command(chat_backend, "tell me a joke")
            # A later "confirm" must NOT execute the stale share.
            commands.process_command(make_backend(None), "confirm")
        web.share_project_knowledge.assert_not_called()
        self.assertIsNone(commands.pending_approval())

    def test_french_confirmation_words_and_prompt(self):
        backend = make_backend(SHARE_PARSED)
        web = self.share_web()
        with patch.dict("sys.modules", kira_web=web):
            asked = commands.process_command(backend, "partage la connaissance deploy: script",
                                             reply_language="fr")
            self.assertIn("confirmation", asked["response"])
            self.assertTrue(asked["response"].startswith("⚠️ Le partage"))
            result = commands.process_command(make_backend(None), "confirmer", reply_language="fr")
        self.assertTrue(result["success"])
        web.share_project_knowledge.assert_called_once()

    def test_clear_completed_asks_then_reports_count(self):
        tasks = types.SimpleNamespace(clear_completed=Mock(return_value=3))
        backend = make_backend({"action": "clear_completed_tasks"})
        with patch.dict("sys.modules", kira_tasks=tasks):
            asked = commands.process_command(backend, "clear completed tasks")
            self.assertTrue(asked["needs_approval"])
            tasks.clear_completed.assert_not_called()
            result = commands.process_command(make_backend(None), "yes")
        self.assertTrue(result["success"])
        self.assertIn("3 completed tasks", result["response"])
        self.assertEqual(result["cleared"], 3)

    def test_non_consequential_tools_run_immediately(self):
        tasks = types.SimpleNamespace(add_task=Mock(return_value="id1"))
        backend = make_backend({"action": "add_todo", "title": "milk"})
        with patch.dict("sys.modules", kira_tasks=tasks):
            result = commands.process_command(backend, "add todo milk")
        self.assertTrue(result["success"])
        tasks.add_task.assert_called_once()
        self.assertIsNone(commands.pending_approval())

    def test_gate_can_be_disabled_explicitly(self):
        backend = make_backend(SHARE_PARSED)
        web = self.share_web()
        with patch.dict(os.environ, {"KIRA_REQUIRE_APPROVAL": "0"}), \
                patch.dict("sys.modules", kira_web=web):
            result = commands.process_command(backend, "share knowledge deploy: use the bat script")
        self.assertTrue(result["success"])
        web.share_project_knowledge.assert_called_once()


class ApprovalRegistryTests(unittest.TestCase):
    def test_unknown_or_expired_approval_is_structured(self):
        result = kira_agents.resolve_approval("nope", approve=True)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "unknown_approval")

    def test_approval_id_is_single_use(self):
        handler = Mock(return_value="done")
        kira_agents.register_tool("tmp_conseq", "windows", "t", {}, handler, consequential=True)
        self.addCleanup(kira_agents.unregister_tool, "tmp_conseq")
        parked = kira_agents.run("tmp_conseq", {})
        self.assertEqual(parked.error_code, "approval_required")
        approval_id = parked.extra["approval_id"]
        first = kira_agents.resolve_approval(approval_id, approve=True)
        self.assertTrue(first.ok)
        second = kira_agents.resolve_approval(approval_id, approve=True)
        self.assertEqual(second.error_code, "unknown_approval")
        handler.assert_called_once()

    def test_activity_records_the_gate_truthfully(self):
        handler = Mock(return_value="done")
        kira_agents.register_tool("tmp_conseq2", "windows", "t", {}, handler, consequential=True)
        self.addCleanup(kira_agents.unregister_tool, "tmp_conseq2")
        parked = kira_agents.run("tmp_conseq2", {})
        entry = kira_agents.recent_activity(1)[0]
        self.assertEqual(entry["error_code"], "approval_required")
        kira_agents.resolve_approval(parked.extra["approval_id"], approve=False)
        entry = kira_agents.recent_activity(1)[0]
        self.assertEqual(entry["error_code"], "approval_rejected")
        handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
