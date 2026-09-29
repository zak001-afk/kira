"""Task and share routes answer as data: no backend speech, no model calls.

The kira_voice_agent handlers for add_reminder / add_todo / list_tasks /
clear_completed_tasks / share_project_knowledge speak() every result
synchronously. That is correct for the standalone microphone loop, but on the
HTTP/UI path it blocked the response and double-spoke (backend voice plus the
browser voice). These regressions pin the direct tool routes added in
kira_commands: execute_action and Ollama must never run for them.
"""
import os
import shutil
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import kira_commands as commands


def approvals_off():
    """These tests pin execution mechanics; test_approval.py covers the gate."""
    return patch.dict(os.environ, {"KIRA_REQUIRE_APPROVAL": "0"})


def make_backend(parsed):
    return SimpleNamespace(
        normalize_command=lambda text: text,
        parse_simple_command=Mock(return_value=parsed),
        ask_chat=Mock(return_value="chat"),
        execute_action=Mock(return_value=True),
        build_reply=Mock(return_value="Done."),
        call_ollama=Mock(return_value={"message": {"content": "irrelevant"}}),
    )


def fake_tasks(task_id="abc123", tasks=(), cleared=0, error=None):
    def raise_or(value):
        def call(*args, **kwargs):
            if error is not None:
                raise error
            return value
        return call
    module = types.SimpleNamespace(
        add_task=Mock(side_effect=raise_or(task_id)),
        list_tasks=Mock(side_effect=raise_or(list(tasks))),
        clear_completed=Mock(side_effect=raise_or(cleared)),
    )
    return module


class TaskRouteTests(unittest.TestCase):
    def run_route(self, parsed, text, tasks_module=None, **options):
        backend = make_backend(parsed)
        with patch.dict("sys.modules", kira_tasks=tasks_module or fake_tasks()):
            result = commands.process_command(backend, text, **options)
        return backend, result

    def test_add_reminder_returns_data_without_backend_speech(self):
        tasks = fake_tasks(task_id="id42")
        backend, result = self.run_route(
            {"action": "add_reminder", "title": "call mom", "due_at": "2026-09-27T18:00:00"},
            "remind me to call mom at 6pm", tasks_module=tasks)
        self.assertTrue(result["success"])
        self.assertIn("call mom", result["response"])
        self.assertEqual(result["task_id"], "id42")
        self.assertIn("elapsed_ms", result)
        backend.execute_action.assert_not_called()  # The voice handler would speak.
        backend.call_ollama.assert_not_called()
        tasks.add_task.assert_called_once_with(title="call mom", task_type="reminder",
                                               due_at="2026-09-27T18:00:00")

    def test_add_todo_speaks_french_via_messages_not_ollama(self):
        backend, result = self.run_route(
            {"action": "add_todo", "title": "acheter du lait"},
            "ajoute une tâche acheter du lait", reply_language="fr")
        self.assertTrue(result["success"])
        self.assertTrue(result["response"].startswith("Tâche ajoutée"))
        backend.call_ollama.assert_not_called()

    def test_missing_title_is_a_structured_failure(self):
        backend, result = self.run_route({"action": "add_todo", "title": "  "}, "add a todo")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "task_title_missing")
        backend.execute_action.assert_not_called()

    def test_list_tasks_returns_numbered_titles_and_data(self):
        tasks = fake_tasks(tasks=[{"id": "1", "title": "Buy milk", "type": "todo", "due_at": ""},
                                  {"id": "2", "title": "Ship KIRA", "type": "todo", "due_at": ""}])
        backend, result = self.run_route({"action": "list_tasks"}, "list my tasks", tasks_module=tasks)
        self.assertTrue(result["success"])
        self.assertIn("1. Buy milk", result["response"])
        self.assertIn("2. Ship KIRA", result["response"])
        self.assertEqual(len(result["tasks"]), 2)
        self.assertEqual(result["tasks"][0]["id"], "1")
        backend.execute_action.assert_not_called()

    def test_list_tasks_empty_is_honest(self):
        backend, result = self.run_route({"action": "list_tasks"}, "list my tasks")
        self.assertTrue(result["success"])
        self.assertEqual(result["response"], "You have no pending tasks.")
        self.assertEqual(result["tasks"], [])

    def test_clear_completed_reports_count(self):
        for cleared, fragment in [(0, "No completed tasks"), (1, "1 completed task"), (3, "3 completed tasks")]:
            with approvals_off():
                backend, result = self.run_route({"action": "clear_completed_tasks"}, "clear completed tasks",
                                                 tasks_module=fake_tasks(cleared=cleared))
            self.assertTrue(result["success"])
            self.assertIn(fragment, result["response"])
            self.assertEqual(result["cleared"], cleared)
            backend.execute_action.assert_not_called()

    def test_tool_failure_stays_structured(self):
        backend, result = self.run_route({"action": "add_todo", "title": "x"}, "add todo x",
                                         tasks_module=fake_tasks(error=RuntimeError("db locked")))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "tool_failed")
        self.assertIn("db locked", result["error"])
        backend.execute_action.assert_not_called()


class ShareRouteTests(unittest.TestCase):
    def test_share_project_knowledge_returns_status_text(self):
        backend = make_backend({"action": "share_project_knowledge", "kind": "project_knowledge",
                                "topic": "deploy", "content": "use the bat script"})
        web = types.SimpleNamespace(
            share_project_knowledge=Mock(return_value="I've shared that project knowledge about 'deploy'."))
        with approvals_off(), patch.dict("sys.modules", kira_web=web):
            result = commands.process_command(backend, "share knowledge deploy: use the bat script")
        self.assertTrue(result["success"])
        self.assertIn("deploy", result["response"])
        web.share_project_knowledge.assert_called_once_with("deploy", "use the bat script")
        backend.execute_action.assert_not_called()
        backend.call_ollama.assert_not_called()

    def test_share_failure_is_structured(self):
        backend = make_backend({"action": "share_project_knowledge", "kind": "project_knowledge",
                                "topic": "t", "content": "c"})
        web = types.SimpleNamespace(share_project_knowledge=Mock(side_effect=RuntimeError("offline")))
        with approvals_off(), patch.dict("sys.modules", kira_web=web):
            result = commands.process_command(backend, "share knowledge t: c")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "tool_failed")
        backend.execute_action.assert_not_called()


class RouteBoundaryTests(unittest.TestCase):
    def test_every_direct_action_bypasses_execute_action(self):
        sandbox = tempfile.mkdtemp(prefix="kira-code-route-")
        self.addCleanup(shutil.rmtree, sandbox, ignore_errors=True)
        samples = {
            "search_shared_knowledge": {"action": "search_shared_knowledge", "query": "q"},
            "share_project_knowledge": {"action": "share_project_knowledge", "topic": "t", "content": "c"},
            "add_reminder": {"action": "add_reminder", "title": "t", "due_at": ""},
            "add_todo": {"action": "add_todo", "title": "t"},
            "list_tasks": {"action": "list_tasks"},
            "clear_completed_tasks": {"action": "clear_completed_tasks"},
            "get_weather": {"action": "get_weather", "city": "Nabeul"},
            "get_holidays": {"action": "get_holidays", "country": "TN", "year": ""},
            "convert_currency": {"action": "convert_currency", "amount": "1",
                                 "from_currency": "eur", "to_currency": "usd"},
            "wiki_summary": {"action": "wiki_summary", "topic": "Tunis"},
            "translate_text": {"action": "translate_text", "text": "hello",
                               "target_language": "fr"},
            "scaffold_project": {"action": "scaffold_project", "name": "route-check",
                                 "template": "empty"},
        }
        self.assertEqual(set(samples), set(commands.DIRECT_TOOL_ACTIONS))
        web = types.SimpleNamespace(search_shared_knowledge=Mock(return_value="found"),
                                    share_project_knowledge=Mock(return_value="shared"))
        info = types.SimpleNamespace(
            default_city=Mock(return_value=""),
            get_weather=Mock(return_value={"city": "Nabeul", "country": "Tunisia",
                                           "temperature": 20, "feels_like": 20, "humidity": 50,
                                           "wind_kmh": 10, "condition": {"en": "clear sky"},
                                           "today_min": 15, "today_max": 25, "rain_chance_today": 0}),
            get_holidays=Mock(return_value={"country": "TN", "year": 2026, "holidays": [], "upcoming": []}),
            convert_currency=Mock(return_value={"amount": 1.0, "from": "EUR", "to": "USD",
                                                "rate": 1.1, "result": 1.1, "date": "2026-01-01"}),
            wiki_summary=Mock(return_value={"title": "Tunis", "summary": "Capital of Tunisia.",
                                            "url": "https://en.wikipedia.org/wiki/Tunis", "language": "en"}),
            translate_text=Mock(return_value={"translated": "bonjour", "source": "en",
                                              "target": "fr", "match": 0.99}),
        )
        for action, parsed in samples.items():
            backend = make_backend(parsed)
            with approvals_off(), patch.dict(os.environ, {"KIRA_CODE_DIR": sandbox}), \
                    patch.dict("sys.modules", kira_web=web, kira_tasks=fake_tasks(),
                               kira_info=info):
                result = commands.process_command(backend, "anything")
            self.assertEqual(result["action"], action)
            self.assertIn("elapsed_ms", result)
            backend.execute_action.assert_not_called()
            backend.call_ollama.assert_not_called()
            backend.build_reply.assert_not_called()

    def test_desktop_actions_still_use_execute_action(self):
        backend = make_backend({"action": "open_app", "target": "chrome"})
        result = commands.process_command(backend, "open chrome")
        backend.execute_action.assert_called_once()
        self.assertTrue(result["success"])

    def test_chat_only_route_never_reaches_tools(self):
        backend = make_backend({"action": "add_todo", "title": "t"})
        commands.process_command(backend, "add todo t", chat_only=True)
        backend.parse_simple_command.assert_not_called()
        backend.ask_chat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
