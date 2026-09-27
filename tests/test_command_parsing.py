"""EN/FR command grammar for the direct tool routes.

Regression source: live Windows test on 2026-09-27 where 'add a todo test
kira', 'list my tasks', 'share knowledge test topic: kira approval works' and
'partage la connaissance essai: bonjour' all fell through to the chat model.
Clear commands must reach tools deterministically, without model calls.
"""
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import kira_commands as commands
from kira_commands import parse_tool_command


class GrammarTests(unittest.TestCase):
    def test_todo_phrasings(self):
        for text in ["add a todo test kira", "add todo test kira", "add task test kira",
                     "create a task test kira", "new todo test kira", "Add a note test kira",
                     "ajoute une tâche test kira", "Ajouter une tache test kira",
                     "crée une tâche test kira", "nouvelle tâche test kira"]:
            parsed = parse_tool_command(text)
            self.assertEqual(parsed, {"action": "add_todo", "title": "test kira"}, text)

    def test_list_phrasings(self):
        for text in ["list my tasks", "list tasks", "show my tasks", "what are my tasks?",
                     "my tasks", "display all tasks", "liste mes tâches", "affiche mes taches",
                     "montre-moi mes tâches", "mes tâches ?"]:
            parsed = parse_tool_command(text)
            self.assertEqual(parsed, {"action": "list_tasks"}, text)

    def test_clear_phrasings(self):
        for text in ["clear completed tasks", "clear completed", "delete completed tasks",
                     "supprime les tâches terminées", "efface mes taches terminées"]:
            parsed = parse_tool_command(text)
            self.assertEqual(parsed, {"action": "clear_completed_tasks"}, text)

    def test_share_topic_colon_content(self):
        for text, topic, content in [
            ("share knowledge test topic: kira approval works", "test topic", "kira approval works"),
            ("share knowledge deploy: use the bat script", "deploy", "use the bat script"),
            ("publish knowledge build - run build_kira.bat", "build", "run build_kira.bat"),
            ("partage la connaissance essai: bonjour", "essai", "bonjour"),
            ("Partager la connaissance déploiement: script bat", "déploiement", "script bat"),
        ]:
            parsed = parse_tool_command(text)
            self.assertIsNotNone(parsed, text)
            self.assertEqual(parsed["action"], "share_project_knowledge", text)
            self.assertEqual(parsed["topic"], topic, text)
            self.assertEqual(parsed["content"], content, text)

    def test_search_shared_phrasings(self):
        for text, query in [
            ("search shared knowledge for python", "python"),
            ("look up shared research about decorators", "decorators"),
            ("cherche dans la connaissance partagée python", "python"),
            ("recherche partagée sur les décorateurs", "les décorateurs"),
        ]:
            parsed = parse_tool_command(text)
            self.assertEqual(parsed, {"action": "search_shared_knowledge", "query": query}, text)

    def test_non_commands_are_left_alone(self):
        for text in ["tell me a joke", "open chrome", "what time is it",
                     "add a todo", "share knowledge nocolon here",
                     "explain shared knowledge to me", "je voudrais une tâche facile",
                     "remind me to call mom at 6pm", ""]:
            self.assertIsNone(parse_tool_command(text), text)


class IntegrationTests(unittest.TestCase):
    """The live-failure phrases must now reach tools even when the backend
    parser (kira_voice_agent grammar) returns None."""

    def backend(self):
        return SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=Mock(return_value=None),   # backend grammar misses
            ask_chat=Mock(return_value="chat fallback"),
            execute_action=Mock(return_value=True),
            build_reply=Mock(return_value="Done."),
            call_ollama=Mock(return_value={"message": {"content": "x"}}),
        )

    def test_add_a_todo_reaches_the_tool_not_the_model(self):
        tasks = types.SimpleNamespace(add_task=Mock(return_value="id9"))
        backend = self.backend()
        with patch.dict("sys.modules", kira_tasks=tasks):
            result = commands.process_command(backend, "add a todo test kira")
        self.assertTrue(result["success"])
        self.assertIn("test kira", result["response"])
        tasks.add_task.assert_called_once_with(title="test kira", task_type="todo")
        backend.ask_chat.assert_not_called()
        backend.call_ollama.assert_not_called()

    def test_list_my_tasks_reaches_the_tool(self):
        tasks = types.SimpleNamespace(list_tasks=Mock(return_value=[]))
        backend = self.backend()
        with patch.dict("sys.modules", kira_tasks=tasks):
            result = commands.process_command(backend, "list my tasks")
        self.assertTrue(result["success"])
        self.assertEqual(result["response"], "You have no pending tasks.")
        backend.ask_chat.assert_not_called()

    def test_share_with_topic_before_colon_asks_for_approval(self):
        commands.clear_pending_approval()
        self.addCleanup(commands.clear_pending_approval)
        backend = self.backend()
        web = types.SimpleNamespace(share_project_knowledge=Mock(return_value="shared"))
        with patch.dict("sys.modules", kira_web=web):
            result = commands.process_command(backend, "share knowledge test topic: kira approval works")
        self.assertTrue(result.get("needs_approval"))
        self.assertIn("test topic", result["response"])
        web.share_project_knowledge.assert_not_called()
        backend.ask_chat.assert_not_called()

    def test_french_share_asks_in_french_then_confirms(self):
        commands.clear_pending_approval()
        self.addCleanup(commands.clear_pending_approval)
        backend = self.backend()
        web = types.SimpleNamespace(share_project_knowledge=Mock(return_value="partagé"))
        with patch.dict("sys.modules", kira_web=web):
            asked = commands.process_command(backend, "partage la connaissance essai: bonjour",
                                             reply_language="fr")
            self.assertTrue(asked.get("needs_approval"))
            self.assertIn("essai", asked["response"])
            self.assertIn("confirmation", asked["response"])
            result = commands.process_command(self.backend(), "confirmer", reply_language="fr")
        self.assertTrue(result["success"])
        web.share_project_knowledge.assert_called_once_with("essai", "bonjour")

    def test_backend_grammar_still_wins_when_ours_misses(self):
        backend = self.backend()
        backend.parse_simple_command.return_value = {"action": "open_app", "target": "chrome"}
        result = commands.process_command(backend, "open chrome")
        backend.execute_action.assert_called_once()
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
