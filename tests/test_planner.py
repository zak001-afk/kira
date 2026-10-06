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
            asked = kira_commands.process_command(self.backend(), "look for python info", reply_language="en")
            # La secrétaire annonce OÙ elle cherche avant de l'exécuter.
            self.assertEqual(asked["action"], "intent")
            self.assertTrue(asked["needs_confirmation"])
            self.assertIn("Web search", asked["response"])
            self.assertIn("research", asked["response"])
            result = kira_commands.process_command(self.backend(), "yes", reply_language="en")
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
            asked = kira_commands.process_command(backend, "tell me a joke", reply_language="en")
            self.assertEqual(asked["action"], "intent")
            self.assertIn("Gemini", asked["response"])   # elle dit où elle cherche
            result = kira_commands.process_command(backend, "yes", reply_language="en")
        self.assertEqual(result["action"], "chat")
        self.assertEqual(result["response"], "chat answer")

    def test_failed_planned_tool_falls_back_to_chat(self):
        backend = self.backend()
        plan = Mock(return_value=("web_search", {"query": "python"}))
        fake_web = types.SimpleNamespace(search_web=Mock(side_effect=RuntimeError("no network")))
        with patch.object(kira_planner, "plan_command", plan), \
                patch.dict(sys.modules, kira_web=fake_web):
            kira_commands.process_command(backend, "look for python info", reply_language="en")
            result = kira_commands.process_command(backend, "yes", reply_language="en")
        self.assertEqual(result["action"], "chat")

    def test_an_agent_that_crashes_falls_back_to_chat_not_an_error(self):
        """The linked agents are asked first; a crashing one must hand the
        question straight to Gemini instead of surfacing an error card."""
        backend = self.backend()
        plan = Mock(return_value=("web_search", {"query": "python"}))
        with patch.object(kira_planner, "plan_command", plan), \
                patch.object(kira_agents, "run", Mock(side_effect=RuntimeError("agent down"))):
            kira_commands.process_command(backend, "look for python info", reply_language="en")
            result = kira_commands.process_command(backend, "yes", reply_language="en")
        self.assertEqual(result["action"], "chat")
        self.assertEqual(result["response"], "chat answer")

    def test_questions_are_asked_of_the_linked_agents_too(self):
        """'quelle est la capitale de X ?' must reach the planner (Atlas…) —
        on a tight timeout so the 4 s budget still holds — before Gemini
        answers the question itself."""
        plan = Mock(return_value=None)
        with patch.object(kira_planner, "plan_command", plan):
            asked = kira_commands.process_command(
                self.backend(), "quelle est la capitale de l'Australie ?",
                reply_language="fr")
            self.assertEqual(asked["action"], "intent")
            self.assertIn("Gemini", asked["response"])
            result = kira_commands.process_command(
                self.backend(), "oui", reply_language="fr")
        plan.assert_called_once()                     # « oui » ne re-planifie pas
        self.assertEqual(plan.call_args.kwargs.get("timeout"), 2.5)
        self.assertEqual(result["action"], "chat")
        self.assertEqual(result["response"], "chat answer")

    def test_failed_atlas_research_falls_back_to_chat(self):
        """« fais une recherche sur X » goes to Atlas; when Atlas comes back
        empty the question must reach Gemini instead of an error card."""
        backend = self.backend()
        failed = types.SimpleNamespace(
            ok=False, error="Atlas timed out", error_code="timeout", elapsed_ms=1,
            to_payload=lambda **kw: {"action": "atlas_research", "success": False,
                                     "error": "Atlas timed out",
                                     "error_code": "timeout", **kw})
        with patch.object(kira_planner, "plan_command", Mock(return_value=None)), \
                patch.object(kira_agents, "run", Mock(return_value=failed)):
            asked = kira_commands.process_command(
                backend, "fais une recherche sur la photosynthese", reply_language="fr")
            self.assertEqual(asked["action"], "intent")   # annonce Atlas d'abord
            self.assertIn("Atlas research", asked["response"])
            result = kira_commands.process_command(backend, "oui", reply_language="fr")
        self.assertEqual(result["action"], "chat")
        self.assertEqual(result["response"], "chat answer")

class AgentSearchTests(unittest.TestCase):
    """« Cherche chez mes agents » : les agents passent en premier, Gemini
    n'intervient qu'après confirmation de l'utilisateur."""

    def backend(self):
        return SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=lambda text: {"action": "none"},
            ask_chat=Mock(return_value="answer from gemini"),
            execute_action=Mock(side_effect=AssertionError("planner must not reach execute_action")),
        )

    def setUp(self):
        kira_commands.clear_pending_agent_search()

    def tearDown(self):
        kira_commands.clear_pending_agent_search()

    def test_only_an_explicit_agent_request_is_recognised(self):
        parse = kira_commands.parse_agent_search_request
        self.assertEqual(parse("cherche chez mes agents la vitesse de la lumiere"),
                         "la vitesse de la lumiere")
        self.assertEqual(parse("interroge tes agents sur la lune"), "la lune")
        self.assertEqual(parse("ask my agents about the stock market"), "the stock market")
        self.assertEqual(parse("cherche chez les agents"), "")   # sujet à redemander
        self.assertIsNone(parse("quelle est la capitale de l'Australie ?"))
        self.assertIsNone(parse("cherche la capitale de l'Australie"))
        self.assertIsNone(parse("search the web for agents of change"))

    def test_no_agent_able_to_answer_asks_for_confirmation(self):
        backend = self.backend()
        with patch.object(kira_planner, "plan_command", Mock(return_value=None)):
            result = kira_commands.process_command(
                backend, "cherche chez mes agents comment fonctionne la photosynthese",
                reply_language="fr")
        self.assertEqual(result["action"], "agent_search")
        self.assertTrue(result["needs_confirmation"])
        self.assertIn("Gemini", result["response"])
        backend.ask_chat.assert_not_called()          # Gemini is NOT reached yet
        self.assertEqual(kira_commands.pending_agent_search()["query"],
                         "comment fonctionne la photosynthese")

    def test_confirmation_sends_the_question_to_gemini(self):
        backend = self.backend()
        with patch.object(kira_planner, "plan_command", Mock(return_value=None)):
            kira_commands.process_command(backend,
                                          "cherche chez mes agents la vitesse de la lumiere",
                                          reply_language="fr")
        result = kira_commands.process_command(backend, "oui", reply_language="fr")
        self.assertEqual(result["action"], "chat")
        self.assertIn("answer from gemini", result["response"])
        self.assertIn("Gemini", result["response"])   # she says what she is doing
        backend.ask_chat.assert_called_once()
        self.assertEqual(backend.ask_chat.call_args.args[0], "la vitesse de la lumiere")
        self.assertIsNone(kira_commands.pending_agent_search())

    def test_declining_keeps_the_answer_with_the_agents(self):
        backend = self.backend()
        with patch.object(kira_planner, "plan_command", Mock(return_value=None)):
            kira_commands.process_command(backend,
                                          "cherche chez mes agents la vitesse de la lumiere",
                                          reply_language="fr")
        result = kira_commands.process_command(backend, "non", reply_language="fr")
        self.assertIn("mes agents", result["response"])
        backend.ask_chat.assert_not_called()
        self.assertIsNone(kira_commands.pending_agent_search())

    def test_a_new_request_expires_the_waiting_confirmation(self):
        backend = self.backend()
        with patch.object(kira_planner, "plan_command", Mock(return_value=None)):
            kira_commands.process_command(backend,
                                          "cherche chez mes agents la vitesse de la lumiere",
                                          reply_language="fr")
            result = kira_commands.process_command(
                backend, "quelle est la capitale de l'Australie ?", reply_language="fr")
            # La nouvelle demande remplace l'attente : elle annonce sa propre
            # cible (Gemini) au lieu de reprendre l'ancienne confirmation.
            self.assertEqual(result["action"], "intent")
            self.assertIsNone(kira_commands.pending_agent_search())
            backend.ask_chat.assert_not_called()
            result = kira_commands.process_command(backend, "oui", reply_language="fr")
        self.assertEqual(result["action"], "chat")
        self.assertEqual(result["response"], "answer from gemini")
        self.assertIsNone(kira_commands.pending_agent_search())

    def test_bare_agent_request_asks_for_the_topic(self):
        result = kira_commands.process_command(self.backend(), "cherche chez les agents",
                                               reply_language="fr")
        self.assertEqual(result["action"], "agent_search")
        self.assertFalse(result.get("needs_confirmation"))
        self.assertIn("Que dois-je demander", result["response"])


class AgentAnswerPresentationTests(unittest.TestCase):
    """Une secrétaire reformule : la sortie d'un agent n'est jamais collée
    telle quelle quand le cloud est là pour l'écrire proprement."""

    LONG = "Matiere brute issue de l agent. " * 6

    def backend(self, present=None):
        backend = SimpleNamespace()
        if present is not None:
            backend.present_answer = present
        return backend

    def test_research_output_is_reformulated_not_copied(self):
        present = Mock(return_value="La photosynthese transforme la lumiere en energie.")
        payload = {"action": "web_search", "success": True, "response": self.LONG}
        out = kira_commands._present_information(payload, "c'est quoi la photosynthese",
                                                 "fr", self.backend(present))
        self.assertTrue(out["reformulated"])
        self.assertEqual(out["response"],
                         "La photosynthese transforme la lumiere en energie.")
        present.assert_called_once_with("c'est quoi la photosynthese",
                                        self.LONG.strip(), "fr")
        self.assertEqual(payload["response"], self.LONG)  # original untouched

    def test_short_confirmations_and_action_outputs_are_left_alone(self):
        present = Mock(return_value="x")
        backend = self.backend(present)
        for payload in ({"action": "web_search", "success": True, "response": "ok"},
                        {"action": "add_todo", "success": True, "response": self.LONG},
                        {"action": "web_search", "success": False, "response": self.LONG},
                        {"action": "web_search", "success": True,
                         "response": self.LONG, "needs_approval": True}):
            self.assertIs(kira_commands._present_information(payload, "q", "fr", backend), payload)
        present.assert_not_called()

    def test_without_a_cloud_helper_the_payload_is_untouched(self):
        payload = {"action": "wiki_summary", "success": True, "response": self.LONG}
        self.assertIs(kira_commands._present_information(payload, "q", "fr",
                                                         self.backend()), payload)

    def test_a_failing_helper_never_breaks_an_existing_answer(self):
        present = Mock(side_effect=RuntimeError("cloud down"))
        payload = {"action": "atlas_research", "success": True, "response": self.LONG}
        out = kira_commands._present_information(payload, "q", "fr", self.backend(present))
        self.assertIs(out, payload)
        self.assertEqual(out["response"], self.LONG)


class ChatOnlyPromptTests(unittest.TestCase):
    def backend(self):
        return SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=lambda text: {"action": "none"},
            ask_chat=Mock(return_value="chat answer"),
            execute_action=Mock(side_effect=AssertionError("planner must not reach execute_action")),
        )

    def test_chat_only_route_never_plans(self):
        plan = Mock()
        backend = self.backend()
        with patch.object(kira_planner, "plan_command", plan):
            kira_commands.process_command(backend, "look for python info",
                                          reply_language="en", chat_only=True)
        plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
