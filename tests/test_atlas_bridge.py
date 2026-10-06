"""Pont KIRA -> Atlas : « fais-moi une recherche sur X » délègue à l'agent Atlas.

Couvre les trois pièces du pont :
1. le registre d'outils (le planner voit `atlas_research`, non conséquentiel) ;
2. le parseur déterministe FR/EN des tournures explicites de recherche ;
3. la route : process_command -> _direct_tool_route -> kira_agents.run, plus
   le handler (sous-processus `atlas_cli.py`) avec un subprocess simulé.

Le vrai sous-processus est testé dans research-agent/atlas_cli.py (CLI réelle,
exécutée manuellement) — ici tout est hors-ligne.

    python -m unittest tests.test_atlas_bridge -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kira_agents
import kira_commands as commands
from kira_commands import parse_research_request

_CLI_OK = (
    "[atlas] clés cloud réutilisées depuis kira/.env\n"
    + json.dumps({
        "ok": True,
        "answer": "La vitamine D est une vitamine liposoluble.",
        "sources": [{"title": "Wikipédia", "url": "https://fr.wikipedia.org/wiki/Vitamine_D",
                     "host": "fr.wikipedia.org", "snippet": "..."}],
        "interpretation": "",
        "pages": 4,
        "elapsed": 12.0,
    }, ensure_ascii=False)
    + "\n"
)


class AtlasCliCase(unittest.TestCase):
    """Base pour les tests qui passent par le sous-processus Atlas.

    ``_atlas_research`` refuse de démarrer si ``atlas_cli.py`` manque : le CLI
    est donc fourni dans un répertoire temporaire (le sous-processus, lui,
    reste simulé). Les tests restent hors-ligne sur n'importe quelle machine,
    y compris CI, où le dossier frère ``research-agent`` n'existe pas.
    """

    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        Path(directory.name, "atlas_cli.py").write_text("# faux CLI de test\n", encoding="utf-8")
        environ = patch.dict(os.environ, {"ATLAS_DIR": directory.name})
        environ.start()
        self.addCleanup(environ.stop)


class RegistryTests(unittest.TestCase):
    """L'outil est visible du planner et rattaché à l'agent research."""

    def test_registered_on_research_agent(self):
        kira_agents.ensure_builtins()
        snapshot = {agent["id"]: agent for agent in kira_agents.agents_snapshot()}
        self.assertIn("atlas_research", snapshot["research"]["tools"])

    def test_in_planner_catalog_and_not_consequential(self):
        kira_agents.ensure_builtins()
        names = {spec["name"] for spec in kira_agents.tool_catalog()}
        self.assertIn("atlas_research", names)
        self.assertFalse(kira_agents._REGISTRY["atlas_research"].consequential)


class ParserTests(unittest.TestCase):
    """Le parseur déterministe ne détient que ses tournures explicites."""

    def test_french_phrases(self):
        cases = {
            "fais-moi une recherche sur paythen": "paythen",
            "fait une recherche sur le RGPD": "le RGPD",
            "fais une recherche web sur les véhicules électriques":
                "les véhicules électriques",
            "recherche sur paythen": "paythen",
            "une recherche approfondie sur la loi 15,9": "la loi 15,9",
            "lance la recherche sur Atlas": "Atlas",
        }
        for text, query in cases.items():
            parsed = parse_research_request(text)
            self.assertIsNotNone(parsed, text)
            self.assertEqual(parsed["query"], query, text)

    def test_english_phrases(self):
        for text in ("research on paythen", "make a research on paythen",
                     "do a deep research about vitamin D"):
            parsed = parse_research_request(text)
            self.assertIsNotNone(parsed, text)
            self.assertTrue(parsed["query"], text)

    def test_non_research_requests_stay_out(self):
        for text in ("salut ça va ?", "quelle heure est-il ?",
                     "cherche mes fichiers", "ouvre firefox",
                     "recherche partagée sur le projet"):
            self.assertIsNone(parse_research_request(text), text)


class HandlerTests(AtlasCliCase):
    """Le handler subprocess renvoie une réponse structurée dans les 2 sens."""

    def test_success_returns_a_clean_answer(self):
        """Réponse propre type ChatGPT : pas de liste de liens, pas de [n]."""
        proc = SimpleNamespace(returncode=0, stdout=_CLI_OK, stderr="")
        with patch("subprocess.run", return_value=proc) as run:
            result = kira_agents.run("atlas_research", {"query": "vitamine d"})
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.response, "La vitamine D est une vitamine liposoluble.")
        self.assertNotIn("Sources", result.response)
        self.assertNotIn("http", result.response)
        # Les sources restent disponibles dans les données du résultat.
        self.assertEqual(result.data["sources"][0]["title"], "Wikipédia")
        argv = run.call_args[0][0]
        self.assertTrue(argv[0].endswith("python.exe"), argv)
        self.assertTrue(argv[1].endswith("atlas_cli.py"), argv)
        self.assertEqual(argv[2], "vitamine d")

    def test_atlas_failure_is_structured(self):
        payload = json.dumps({"ok": False, "error": "Gemini en feu",
                              "error_code": "atlas_failed"})
        proc = SimpleNamespace(returncode=1, stdout=payload + "\n", stderr="")
        with patch("subprocess.run", return_value=proc):
            result = kira_agents.run("atlas_research", {"query": "x"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Gemini en feu")
        self.assertEqual(result.error_code, "atlas_failed")
        self.assertTrue(result.response)  # le client voit une phrase, pas un dict

    def test_missing_atlas_install_is_structured(self):
        with patch.dict(os.environ, {"ATLAS_DIR": r"C:\does\not\exist\atlas"}):
            result = kira_agents.run("atlas_research", {"query": "x"})
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "atlas_missing")

    def test_empty_query_is_refused(self):
        result = kira_agents.run("atlas_research", {"query": "   "})
        self.assertFalse(result.ok)
        # Le registre valide d'abord (required non vide) ; le handler garde sa
        # propre garde pour un appel direct.
        self.assertIn(result.error_code, {"invalid_args", "bad_request"})


class AnswerLanguageTests(AtlasCliCase):
    """La réponse Atlas doit sortir dans la langue de la question (FR -> FR)."""

    _EN_ANSWER = ("The best hotels in Paris are the Ritz and the Peninsula. "
                  "Both offer luxurious spa facilities, private terraces and "
                  "exceptional service in the heart of the city.")
    _FR_ANSWER = ("Les meilleurs hôtels de Paris sont le Ritz et le Peninsula. "
                  "Tous deux offrent un spa de luxe, des terrasses privées et "
                  "un service exceptionnel au cœur de la ville.")

    def test_language_flag_is_sent_to_the_atlas_cli(self):
        proc = SimpleNamespace(returncode=0, stdout=_CLI_OK, stderr="")
        with patch("subprocess.run", return_value=proc) as run:
            result = kira_agents.run("atlas_research",
                                     {"query": "vitamine d", "language": "fr"})
        self.assertTrue(result.ok, result.error)
        argv = run.call_args[0][0]
        self.assertEqual(argv[2], "vitamine d")
        self.assertEqual(argv[3:], ["--lang", "fr"])

    def test_no_language_flag_without_a_detected_language(self):
        proc = SimpleNamespace(returncode=0, stdout=_CLI_OK, stderr="")
        with patch("subprocess.run", return_value=proc) as run:
            kira_agents.run("atlas_research", {"query": "vitamine d"})
        self.assertEqual(run.call_args[0][0][3:], [])

    def test_english_answer_is_translated_once_to_french(self):
        fake_ai = SimpleNamespace(
            chat=Mock(return_value=SimpleNamespace(ok=True, text=self._FR_ANSWER)))
        with patch.dict(sys.modules, kira_ai=fake_ai):
            text = kira_agents._ensure_atlas_language(self._EN_ANSWER, "fr")
        self.assertEqual(text, self._FR_ANSWER)
        self.assertEqual(fake_ai.chat.call_count, 1)  # une seule traduction

    def test_already_local_answer_costs_nothing(self):
        fake_ai = SimpleNamespace(chat=Mock())
        with patch.dict(sys.modules, kira_ai=fake_ai):
            text = kira_agents._ensure_atlas_language(self._FR_ANSWER, "fr")
        self.assertEqual(text, self._FR_ANSWER)
        fake_ai.chat.assert_not_called()  # détection locale uniquement

    def test_missing_language_never_touches_the_answer(self):
        fake_ai = SimpleNamespace(chat=Mock())
        with patch.dict(sys.modules, kira_ai=fake_ai):
            text = kira_agents._ensure_atlas_language(self._EN_ANSWER, "")
        self.assertEqual(text, self._EN_ANSWER)
        fake_ai.chat.assert_not_called()


class RouteTests(unittest.TestCase):
    """« fais-moi une recherche sur X » part en outil, jamais en chat."""

    def backend(self):
        return SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=lambda text: {"action": "none"},
            execute_action=Mock(side_effect=AssertionError(
                "la recherche doit partir en outil, pas en execute_action")),
        )

    def test_french_request_routes_to_atlas(self):
        fake = SimpleNamespace(
            ok=True, response="Synthèse complète.", data={}, extra={},
            error="", error_code="", elapsed_ms=12,
            to_payload=lambda **meta: {"action": "atlas_research",
                                       "success": True,
                                       "response": "Synthèse complète.", **meta})
        with patch.object(kira_agents, "run", return_value=fake) as run:
            asked = commands.process_command(
                self.backend(), "fais-moi une recherche sur paythen",
                reply_language="fr")
            # La secrétaire dit CHEZ QUI elle va chercher avant de l'envoyer.
            self.assertEqual(asked["action"], "intent")
            self.assertTrue(asked["needs_confirmation"])
            self.assertIn("Atlas research", asked["response"])
            self.assertIn("research", asked["response"])
            run.assert_not_called()                       # rien avant « oui »
            result = commands.process_command(self.backend(), "oui", reply_language="fr")
        run.assert_called_once()
        self.assertEqual(run.call_args[0][0], "atlas_research")
        # La langue détectée de la question part avec la requête : la
        # synthèse Atlas doit sortir dans cette langue (FR -> FR).
        self.assertEqual(run.call_args[0][1], {"query": "paythen", "language": "fr"})
        self.assertEqual(result["action"], "atlas_research")
        self.assertTrue(result["success"])
        self.assertIn("Synthèse complète", result["response"])

    def test_plain_chat_does_not_trigger_atlas(self):
        with patch.object(kira_agents, "run") as run:
            commands.process_command(self.backend(), "salut ça va ?",
                                     reply_language="fr")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
