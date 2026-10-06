"""La secrétaire demande OÙ elle va chercher / appliquer AVANT d'agir.

À chaque question, ordre ou action, KIRA annonce la cible (agent, outil,
application ou Gemini) et attend « oui » / « non ». La cible est toujours
lue sur le registre d'outils vivant : Atlas existe parce qu'il est
enregistré ; les agents ajoutés plus tard sont connus sans rien coder en dur.
"""
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kira_agents
import kira_commands as commands
import kira_planner


def backend(**overrides):
    data = dict(normalize_command=lambda text: text,
                parse_simple_command=Mock(return_value={"action": "none"}),
                ask_chat=Mock(return_value="la réponse de gemini"),
                execute_action=Mock(return_value=True),
                build_reply=Mock(return_value="J'ouvre chrome."))
    data.update(overrides)
    return SimpleNamespace(**data)


def open_backend(**overrides):
    """Backend dont la grammaire résout « open chrome » en action bureau."""
    return backend(parse_simple_command=Mock(
        return_value={"action": "open_app", "target": "chrome"}), **overrides)


def confirm(own_backend, text, **options):
    """La première réponse DOIT être l'annonce ; « oui » exécute ensuite."""
    asked = commands.process_command(own_backend, text, **options)
    assert asked.get("needs_confirmation"), f"pas d'annonce d'intention: {asked}"
    assert asked["action"] == "intent", asked
    assert (asked.get("intent") or {}).get("target"), asked
    return commands.process_command(own_backend, "oui", **options)


class IntentAnnouncementTests(unittest.TestCase):
    def setUp(self):
        commands.clear_pending_intent()
        commands.clear_pending_agent_search()

    def tearDown(self):
        commands.clear_pending_intent()
        commands.clear_pending_agent_search()

    def test_action_is_announced_and_nothing_runs_before_the_yes(self):
        own_backend = open_backend()
        asked = commands.process_command(own_backend, "open chrome", reply_language="fr")
        self.assertEqual(asked["action"], "intent")
        self.assertTrue(asked["needs_confirmation"])
        self.assertIn("ouvrir", asked["response"])       # où elle va l'appliquer
        self.assertIn("chrome", asked["response"])
        own_backend.execute_action.assert_not_called()

    def test_confirm_executes_the_saved_request_exactly_once(self):
        own_backend = open_backend()
        confirm(own_backend, "open chrome")
        own_backend.execute_action.assert_called_once()
        self.assertEqual(own_backend.execute_action.call_args.args[0]["action"], "open_app")

    def test_refusal_cancels_and_runs_nothing(self):
        own_backend = open_backend()
        commands.process_command(own_backend, "open chrome", reply_language="fr")
        result = commands.process_command(own_backend, "non", reply_language="fr")
        self.assertEqual(result["action"], "intent")
        self.assertFalse(result.get("success"))
        self.assertIn("ne lance rien", result["response"])
        own_backend.execute_action.assert_not_called()
        self.assertIsNone(commands.pending_intent())

    def test_question_names_gemini_and_answers_after_confirmation(self):
        own_backend = backend()
        with patch.object(kira_planner, "plan_command", Mock(return_value=None)):
            asked = commands.process_command(own_backend, "c'est quoi la photosynthese ?",
                                             reply_language="fr")
            self.assertEqual(asked["action"], "intent")
            self.assertIn("Gemini", asked["response"])
            self.assertIn("tu confirmes", asked["response"])   # ton secrétaire
            own_backend.ask_chat.assert_not_called()
            result = commands.process_command(own_backend, "oui", reply_language="fr")
        self.assertEqual(result["action"], "chat")
        own_backend.ask_chat.assert_called_once()
        self.assertEqual(own_backend.ask_chat.call_args.args[0],
                         "c'est quoi la photosynthese ?")
        self.assertEqual(own_backend.ask_chat.call_args.kwargs.get("language"), "fr")

    def test_announcement_follows_the_question_language(self):
        with patch.object(kira_planner, "plan_command", Mock(return_value=None)):
            french = commands.process_command(backend(), "raconte-moi une histoire",
                                              reply_language="fr")
            english = commands.process_command(backend(), "tell me a story",
                                               reply_language="en")
        self.assertIn("Je vais", french["response"])
        self.assertIn("about to", english["response"])

    def test_planned_agent_is_named_before_it_runs(self):
        own_backend = backend()
        plan = Mock(return_value=("atlas_research", {"query": "photosynthese"}))
        fake = SimpleNamespace(
            ok=True, response="Synthèse.", data={}, extra={}, error="", error_code="",
            elapsed_ms=5,
            to_payload=lambda **meta: {"action": "atlas_research", "success": True,
                                       "response": "Synthèse.", **meta})
        with patch.object(kira_planner, "plan_command", plan), \
                patch.object(kira_agents, "run", Mock(return_value=fake)) as run:
            asked = commands.process_command(own_backend, "cherche la photosynthese",
                                             reply_language="fr")
            self.assertEqual(asked["action"], "intent")
            self.assertIn("Atlas research", asked["response"])   # nom de l'outil
            self.assertIn("research", asked["response"])         # nom de l'agent
            run.assert_not_called()                              # rien avant « oui »
            result = commands.process_command(own_backend, "oui", reply_language="fr")
        run.assert_called_once()
        self.assertEqual(result["action"], "atlas_research")

    def test_new_request_expires_the_pending_intention(self):
        own_backend = open_backend()
        commands.process_command(own_backend, "open chrome")
        self.assertIsNotNone(commands.pending_intent())
        greeting = commands.process_command(own_backend, "bonjour")
        self.assertIn("Bonjour", greeting["response"])
        self.assertIsNone(commands.pending_intent())
        # Un « oui » tardif ne doit plus rien déclencher.
        commands.process_command(own_backend, "oui")
        own_backend.execute_action.assert_not_called()

    def test_intention_expires_after_the_ttl(self):
        own_backend = open_backend()
        commands.process_command(own_backend, "open chrome")
        commands._INTENT_PENDING["time"] -= commands._INTENT_TTL + 1
        self.assertIsNone(commands.pending_intent())
        commands.process_command(own_backend, "oui")
        own_backend.execute_action.assert_not_called()


class ConfirmationWordTests(unittest.TestCase):
    def test_yes_and_no_in_the_supported_languages(self):
        for word in ("oui", "yes", "ok", "confirmer", "go ahead"):
            self.assertEqual(commands._confirmation_answer(word), "yes", word)
        for word in ("non", "no", "cancel", "annuler", "stop"):
            self.assertEqual(commands._confirmation_answer(word), "no", word)

    def test_a_real_sentence_is_never_a_confirmation(self):
        self.assertIsNone(commands._confirmation_answer(
            "quelle est la capitale de l'Australie"))


class AgentsRosterTests(unittest.TestCase):
    def setUp(self):
        commands.clear_pending_intent()

    def tearDown(self):
        commands.clear_pending_intent()

    def test_roster_lists_the_live_registry_including_atlas(self):
        result = commands.process_command(backend(), "quels agents as-tu ?",
                                          reply_language="fr")
        self.assertEqual(result["action"], "agents")
        self.assertIn("atlas_research", result["response"])
        self.assertIn("research", result["response"])
        self.assertIn("où je le fais", result["response"])
        ids = {agent["id"] for agent in result["agents"]}
        self.assertEqual(ids, {"research", "memory", "windows", "plugins", "programming"})

    def test_an_agent_added_later_is_known_without_coding_it_in(self):
        kira_agents.register_tool("tmp_translate_docs", "research",
                                  "Traduit des documents", {"query": {"type": str}},
                                  Mock(return_value={"ok": True}))
        self.addCleanup(kira_agents.unregister_tool, "tmp_translate_docs")
        roster = commands.process_command(backend(), "which agents", reply_language="en")
        self.assertIn("tmp_translate_docs", roster["response"])
        # …et il est annoncé comme cible quand le planneur le choisit.
        with patch.object(kira_planner, "plan_command",
                          Mock(return_value=("tmp_translate_docs", {"query": "x"}))):
            asked = commands.process_command(backend(), "translate this document",
                                             reply_language="en")
        self.assertEqual(asked["action"], "intent")
        self.assertIn("Tmp translate docs", asked["response"])
        self.assertIn("research", asked["response"])

    def test_a_search_request_is_not_a_roster_question(self):
        self.assertTrue(commands.parse_agents_request("quels agents as-tu ?"))
        self.assertTrue(commands.parse_agents_request("who are your agents"))
        self.assertTrue(commands.parse_agents_request("mes agents"))
        self.assertIsNone(commands.parse_agents_request(
            "quelle est la capitale de l'Australie ?"))
        self.assertIsNone(commands.parse_agents_request("cherche chez mes agents la météo"))
        self.assertIsNone(commands.parse_agents_request(
            "ask my agents about the stock market"))


class ScopeTests(unittest.TestCase):
    """Ce que la confirmation couvre — et ce qu'elle ne doit pas doubler."""

    def setUp(self):
        commands.clear_pending_intent()
        commands.clear_pending_approval()

    def tearDown(self):
        commands.clear_pending_intent()
        commands.clear_pending_approval()

    def test_consequential_tools_keep_their_single_approval_card(self):
        own_backend = backend(parse_simple_command=Mock(
            return_value={"action": "share_project_knowledge",
                          "topic": "t", "content": "c"}))
        web = types.SimpleNamespace(share_project_knowledge=Mock(return_value="partagé"))
        with patch.dict("sys.modules", kira_web=web):
            asked = commands.process_command(own_backend, "share knowledge t: c")
        self.assertTrue(asked.get("needs_approval"))
        self.assertFalse(asked.get("needs_confirmation"))   # pas de double question
        self.assertIsNone(commands.pending_intent())
        web.share_project_knowledge.assert_not_called()

    def test_chat_reset_is_not_treated_as_an_action(self):
        own_backend = backend(parse_simple_command=Mock(return_value={"action": "chat_reset"}),
                              reset_chat=Mock(return_value=True))
        result = commands.process_command(own_backend, "clear chat")
        self.assertEqual(result["action"], "chat_reset")
        own_backend.reset_chat.assert_called_once()

    def test_chat_only_route_never_asks_for_confirmation(self):
        own_backend = backend()
        with patch.object(kira_planner, "plan_command", Mock(return_value=None)):
            out = commands.process_command(own_backend, "tell me a joke",
                                           reply_language="en", chat_only=True)
        self.assertEqual(out["action"], "chat")
        self.assertFalse(out.get("needs_confirmation"))
        self.assertIsNone(commands.pending_intent())

    def test_canned_replies_answer_without_asking(self):
        result = commands.process_command(backend(), "quelle heure est il",
                                          reply_language="fr")
        self.assertEqual(result["action"], "chat")
        self.assertIn("Il est", result["response"])
        self.assertIsNone(commands.pending_intent())


if __name__ == "__main__":
    unittest.main()
