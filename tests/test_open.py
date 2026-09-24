"""Files, applications and web pages: one open-resolver for EN/FR/AR.

KIRA must open things only when the user asks for it, resolve what was asked
(web page vs installed app vs local file), and answer in the conversation
language. All opening happens through kira_open so the behaviour is identical
for native, web and HTTP clients.
"""
import ast
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import kira_open
import kira_commands as commands

ROOT = Path(__file__).resolve().parent.parent


class ResolveTests(unittest.TestCase):
    def test_google_services_open_their_own_pages(self):
        expected = {
            "google": "https://www.google.com",
            "google maps": "https://www.google.com/maps",
            "gmail": "https://mail.google.com",
            "google translate": "https://translate.google.com",
            "youtube": "https://www.youtube.com",
            "google docs": "https://docs.google.com/document/create",
        }
        for name, url in expected.items():
            self.assertEqual(kira_open.resolve_open(name), {"kind": "url", "target": url}, name)

    def test_domains_and_links_are_web_pages(self):
        for target in ["github.com", "www.google.com/maps", "https://example.com/x"]:
            self.assertEqual(kira_open.resolve_open(target)["kind"], "url", target)

    def test_known_apps_stay_desktop_apps_even_when_a_web_version_exists(self):
        for name in ["chrome", "notepad", "spotify", "teams", "bloc notes", "vscode"]:
            self.assertEqual(kira_open.resolve_open(name)["kind"], "app", name)

    def test_well_known_folders_in_french_and_english(self):
        for name in ["downloads", "téléchargements", "bureau", "documents", "musique", "photos"]:
            self.assertEqual(kira_open.resolve_open(name)["kind"], "folder", name)

    def test_paths_and_file_names_are_files(self):
        for target in ["C:\\Users\\me\\doc.pdf", "~/notes.txt", "rapport.pdf", "photos/vacances.jpg"]:
            self.assertEqual(kira_open.resolve_open(target)["kind"], "file", target)

    def test_a_file_name_loses_its_politeness_words(self):
        self.assertEqual(kira_open.resolve_open("mon rapport.pdf"), {"kind": "file", "target": "rapport.pdf"})

    def test_unknown_names_default_to_an_application(self):
        self.assertEqual(kira_open.resolve_open("medibang paint")["kind"], "app")

    def test_a_local_text_file_is_not_treated_as_a_domain(self):
        self.assertEqual(kira_open.resolve_open("notes.txt")["kind"], "file")

    def test_empty_targets_are_rejected(self):
        self.assertIsNone(kira_open.resolve_open(""))
        self.assertIsNone(kira_open.resolve_open("   "))


class ParseOpenTests(unittest.TestCase):
    def parse(self, text):
        return kira_open.parse_open_command(text)

    def test_open_prefixes_in_three_languages(self):
        self.assertEqual(self.parse("open notepad"), {"action": "open_app", "target": "notepad"})
        self.assertEqual(self.parse("lance chrome"), {"action": "open_app", "target": "chrome"})
        self.assertEqual(self.parse("شغل كروم"), {"action": "open_app", "target": "كروم"})

    def test_pages_google_are_opened_by_name(self):
        self.assertEqual(self.parse("ouvre google maps"), {"action": "open_url", "target": "https://www.google.com/maps"})
        self.assertEqual(self.parse("open gmail"), {"action": "open_url", "target": "https://mail.google.com"})

    def test_files_with_politeness_words(self):
        self.assertEqual(self.parse("ouvre mon rapport.pdf"), {"action": "open_file", "target": "rapport.pdf"})
        self.assertEqual(self.parse("open my notes.txt"), {"action": "open_file", "target": "notes.txt"})

    def test_explicit_file_word_forces_a_file_even_without_extension(self):
        self.assertEqual(self.parse("ouvre le document budget"), {"action": "open_file", "target": "budget"})
        self.assertEqual(self.parse("open file C:\\x\\a.txt"), {"action": "open_file", "target": "C:\\x\\a.txt"})

    def test_politeness_and_filler_never_hide_the_target(self):
        # The exact sentence that failed in real use ("KIRA n'a pas pu effectuer open_app").
        self.assertEqual(self.parse("ouvre moi le'aplication google"), {"action": "open_url", "target": "https://www.google.com"})
        self.assertEqual(self.parse("ouvre moi l'application google"), {"action": "open_url", "target": "https://www.google.com"})
        self.assertEqual(self.parse("ouvre l'application chrome"), {"action": "open_app", "target": "chrome"})
        self.assertEqual(self.parse("open the google application"), {"action": "open_url", "target": "https://www.google.com"})
        self.assertEqual(self.parse("ouvre le site github"), {"action": "open_url", "target": "https://github.com"})

    def test_polite_questions_open_too(self):
        self.assertEqual(self.parse("ouvre-moi google"), {"action": "open_url", "target": "https://www.google.com"})
        self.assertEqual(self.parse("peux-tu m'ouvrir google"), {"action": "open_url", "target": "https://www.google.com"})
        self.assertEqual(self.parse("tu peux m ouvrir gmail"), {"action": "open_url", "target": "https://mail.google.com"})
        self.assertEqual(self.parse("s'il te plaît ouvre youtube"), {"action": "open_url", "target": "https://www.youtube.com"})
        self.assertEqual(self.parse("stp ouvre google maps"), {"action": "open_url", "target": "https://www.google.com/maps"})
        self.assertEqual(self.parse("please open google"), {"action": "open_url", "target": "https://www.google.com"})
        self.assertEqual(self.parse("est-ce que tu peux ouvrir wikipedia"), {"action": "open_url", "target": "https://www.wikipedia.org"})
        self.assertEqual(self.parse("من فضلك افتح كروم"), {"action": "open_app", "target": "كروم"})

    def test_questions_about_opening_are_not_commands(self):
        self.assertIsNone(self.parse("comment ouvrir un fichier pdf ?"))
        self.assertIsNone(self.parse("open the folder"))

    def test_open_wishes_are_recognized(self):
        self.assertEqual(self.parse("je veux que tu ouvres facebook"), {"action": "open_url", "target": "https://www.facebook.com"})
        self.assertEqual(self.parse("je veux ouvrir facebook"), {"action": "open_url", "target": "https://www.facebook.com"})
        self.assertEqual(self.parse("j'aimerais ouvrir google maps"), {"action": "open_url", "target": "https://www.google.com/maps"})
        self.assertEqual(self.parse("je veux bien ouvrir chrome"), {"action": "open_app", "target": "chrome"})
        self.assertEqual(self.parse("i want you to open youtube"), {"action": "open_url", "target": "https://www.youtube.com"})
        self.assertIsNone(self.parse("je veux que tu ouvriez gmail"))

    def test_folder_requests(self):
        self.assertEqual(self.parse("open folder downloads"), {"action": "open_folder", "target": "downloads"})
        self.assertEqual(self.parse("open the dossier documents"), {"action": "open_folder", "target": "documents"})

    def test_combined_open_and_search_stays_with_the_caller(self):
        self.assertIsNone(self.parse("open chrome and search news"))
        self.assertIsNone(self.parse("ouvre chrome et cherche actualités"))

    def test_bare_prefix_without_target_is_ignored(self):
        self.assertIsNone(self.parse("open"))
        self.assertIsNone(self.parse("ouvre "))


class FindFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        home = Path(cls._tmp.name)
        for sub in ("Desktop", "Documents/sub", "Downloads"):
            (home / sub).mkdir(parents=True, exist_ok=True)
        (home / "Documents" / "rapport.pdf").write_text("x", encoding="utf-8")
        (home / "Documents" / "sub" / "budget.xlsx").write_text("x", encoding="utf-8")
        (home / "Desktop" / "CV_2026.docx").write_text("x", encoding="utf-8")
        cls.dirs = kira_open.common_file_dirs(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_searches_the_common_folders_by_stem(self):
        found = kira_open.find_file("rapport", search_dirs=self.dirs)
        self.assertTrue(found and found.endswith("rapport.pdf"), found)

    def test_exact_name_with_extension_wins(self):
        found = kira_open.find_file("budget.xlsx", search_dirs=self.dirs)
        self.assertTrue(found and found.endswith("budget.xlsx"), found)

    def test_finds_files_in_subfolders(self):
        found = kira_open.find_file("budget", search_dirs=self.dirs)
        self.assertTrue(found and found.endswith("budget.xlsx"), found)

    def test_short_prefix_matches_like_cv(self):
        found = kira_open.find_file("cv", search_dirs=self.dirs)
        self.assertTrue(found and found.endswith("CV_2026.docx"), found)

    def test_unknown_names_return_none(self):
        self.assertIsNone(kira_open.find_file("zzzqqqww", search_dirs=self.dirs))

    def test_direct_paths_are_returned_when_they_exist(self):
        direct = os.path.join(self._tmp.name, "Documents", "rapport.pdf")
        self.assertEqual(kira_open.find_file(direct, search_dirs=self.dirs), direct)


class StartMenuTests(unittest.TestCase):
    def test_matches_shortcut_names_without_accents_or_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            programs = Path(tmp) / "Programs" / "Mozilla Firefox.lnk"
            programs.parent.mkdir(parents=True)
            programs.write_text("", encoding="utf-8")
            found = kira_open.find_start_menu_app("mozilla firefox", dirs=[str(Path(tmp) / "Programs")])
            self.assertTrue(found and found.endswith("Mozilla Firefox.lnk"), found)
        self.assertIsNone(kira_open.find_start_menu_app("nothing here", dirs=[tmp]))


class VoiceAgentIntegrationTests(unittest.TestCase):
    """parse_simple_command runs inside kira_voice_agent, which cannot be
    imported without Windows desktop dependencies; the function is executed
    from its AST with stub neighbours, like the language prompt tests."""

    def parse_with_stubs(self):
        tree = ast.parse((ROOT / "kira_voice_agent.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "parse_simple_command")

        class Stub:
            def __getattr__(self, name):
                return lambda *args, **kwargs: None

        namespace = {
            "re": re, "kira_open": kira_open,
            "kira_tasks": Stub(), "kira_plugins": Stub(), "kira_memory": Stub(),
            "USER_MEMORY": {}, "CONFIG": {"shortcuts": {}}, "ADDRESS_OPTIONS": {},
            "WAKE_WORD": "kira", "APP_ALIASES": {},
            "normalize_for_language": lambda text: text,
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), "parse_subset", "exec"), namespace)
        return namespace["parse_simple_command"]

    def setUp(self):
        self.parse = self.parse_with_stubs()

    def action(self, text):
        result = self.parse(text)
        return result.get("action") if isinstance(result, dict) else result

    def test_existing_commands_keep_priority_over_opening(self):
        self.assertEqual(self.action("start conversation"), "conversation_on")
        self.assertEqual(self.action("stop conversation"), "conversation_off")
        self.assertEqual(self.action("screenshot"), "screenshot")
        self.assertEqual(self.action("volume up"), "volume_up")
        self.assertEqual(self.action("what time is it"), "time")

    def test_open_requests_reach_the_new_resolver(self):
        self.assertEqual(self.action("open notepad"), "open_app")
        self.assertEqual(self.action("ouvre google maps"), "open_url")
        self.assertEqual(self.action("ouvre le document budget"), "open_file")
        self.assertEqual(self.action("open folder downloads"), "open_folder")
        self.assertEqual(self.action("open C:\\Users\\me\\doc.pdf"), "open_file")

    def test_filler_and_politeness_still_reach_the_resolver(self):
        self.assertEqual(self.action("ouvre moi le'aplication google"), "open_url")
        self.assertEqual(self.action("peux-tu m'ouvrir google"), "open_url")
        self.assertEqual(self.action("tu peux m ouvrir gmail"), "open_url")

    def test_combined_open_and_search_sequence_is_preserved(self):
        self.assertEqual(self.action("open chrome and search news"), "sequence")

    def test_a_bare_known_name_opens_but_a_mention_does_not(self):
        self.assertEqual(self.action("google"), "open_url")
        self.assertEqual(self.action("notepad"), "open_app")
        self.assertEqual(self.action("téléchargements"), "open_folder")
        self.assertIsNone(self.action("qui a créé google ?"))
        self.assertIsNone(self.action("write a poem about youtube"))

    def test_language_commands_are_still_not_actions(self):
        self.assertIsNone(self.action("réponds-moi en français"))
        self.assertIsNone(self.action("what does reply in french mean"))


class ReplyAndDescriptionTests(unittest.TestCase):
    def namespace(self, names):
        tree = ast.parse((ROOT / "kira_voice_agent.py").read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names | {"preferred_address"}]
        nodes += [n for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id in {"ADDRESS_OPTIONS"} for t in n.targets)]
        namespace = {"kira_language": __import__("kira_language"), "CONFIG": {"preferred_address": "sir"}}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "reply_subset", "exec"), namespace)
        return namespace

    def test_open_file_reply_is_localized(self):
        ns = self.namespace({"build_reply", "address_for_language"})
        self.assertIn("rapport.pdf", ns["build_reply"]("fr", "open_file", "rapport.pdf"))
        self.assertIn("الملف", ns["build_reply"]("ar", "open_file", "rapport.pdf"))
        self.assertIn("rapport.pdf", ns["build_reply"]("en", "open_file", "rapport.pdf"))

    def test_describe_action_covers_folders_and_files(self):
        ns = self.namespace({"describe_action"})
        self.assertEqual(ns["describe_action"]({"action": "open_file", "target": "a.txt"}), "open the file a.txt")
        self.assertEqual(ns["describe_action"]({"action": "open_folder", "target": "downloads"}), "open the downloads folder")


class OpenActionRoutingTests(unittest.TestCase):
    """process_command must execute open actions through the backend exactly
    once, in the conversation language, without calling the chat model."""

    @staticmethod
    def backend(action="open_file", target="rapport.pdf", success=True):
        return SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=Mock(return_value={"action": action, "target": target}),
            execute_action=Mock(return_value=success),
            build_reply=lambda language, name, target_text: f"{name}:{target_text}:{language}",
        )

    def test_open_file_action_executes_once_in_french(self):
        result = commands.process_command(self.backend(), "ouvre mon rapport.pdf", reply_language="fr")
        self.assertEqual(result["action"], "open_file")
        self.assertTrue(result["success"])
        self.assertEqual(result["response"], "open_file:rapport.pdf:fr")
        self.assertEqual(result["language"], "fr")

    def test_failed_open_is_admitted_in_the_interface_language(self):
        result = commands.process_command(self.backend(target="ghost.pdf", success=False), "ouvre ghost.pdf", reply_language="fr", interface_language="fr")
        self.assertFalse(result["success"])
        self.assertIn("ghost.pdf", result["response"])

    def test_open_actions_are_blocked_in_chat_only_mode(self):
        backend = self.backend()
        backend.ask_chat = Mock(return_value="chat answer")
        result = commands.process_command(backend, "open chrome", reply_language="en", chat_only=True)
        backend.parse_simple_command.assert_not_called()
        backend.execute_action.assert_not_called()
        self.assertEqual(result["action"], "chat")

    def test_builtin_help_mentions_files(self):
        for language, word in [("en", "files"), ("fr", "fichiers")]:
            self.assertIn(word, commands.builtin_reply("help", language))


class OpenAppFallbackTests(unittest.TestCase):
    """The requested flow: check the installed app first; never scan the
    user's documents; otherwise open a correct browser page."""

    def run_open_app(self, name):
        opened = []
        with patch.object(kira_open.subprocess, "Popen", side_effect=OSError("not installed")), \
             patch.object(kira_open, "find_start_menu_app", return_value=None), \
             patch.object(kira_open, "find_installed_exe", return_value=None), \
             patch.object(kira_open.webbrowser, "open", side_effect=lambda url: opened.append(url) or True), \
             patch.object(kira_open, "find_file", side_effect=AssertionError("open_app must not scan user files")):
            result = kira_open.open_app(name)
        return result, opened

    def test_unknown_app_opens_a_browser_search_for_the_name(self):
        result, opened = self.run_open_app("jardimage")
        self.assertTrue(result)
        self.assertEqual(opened, ["https://www.google.com/search?q=jardimage"])

    def test_known_web_version_wins_over_the_generic_search(self):
        result, opened = self.run_open_app("spotify")
        self.assertTrue(result)
        self.assertEqual(opened, ["https://open.spotify.com"])

    def test_facebook_app_request_falls_back_to_the_facebook_page(self):
        result, opened = self.run_open_app("facebook")
        self.assertTrue(result)
        self.assertEqual(opened, ["https://www.facebook.com"])

    def test_installed_exe_lookup_in_given_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(kira_open.find_installed_exe("ghostapp", bases=[tmp]))
            vendor = Path(tmp) / "Vendor"
            vendor.mkdir()
            (vendor / "ghostapp.exe").write_text("", encoding="utf-8")
            found = kira_open.find_installed_exe("ghost app", bases=[tmp])
            self.assertTrue(found and found.endswith("ghostapp.exe"), found)


class FindFileSpeedTests(unittest.TestCase):
    def test_system_folders_are_pruned_from_the_search(self):
        with tempfile.TemporaryDirectory() as home:
            noise = Path(home) / "AppData" / "Roaming" / "deep"
            noise.mkdir(parents=True)
            (noise / "rapport.pdf").write_text("x", encoding="utf-8")
            self.assertIsNone(kira_open.find_file("rapport", search_dirs=[home], time_budget=2.0))

    def test_user_documents_are_found_quickly(self):
        with tempfile.TemporaryDirectory() as home:
            documents = Path(home) / "Documents"
            documents.mkdir()
            (documents / "rapport.pdf").write_text("x", encoding="utf-8")
            started = time.monotonic()
            found = kira_open.find_file("rapport", search_dirs=[home])
            self.assertLess(time.monotonic() - started, 3.0)
            self.assertTrue(found and found.endswith("rapport.pdf"), found)

    def test_time_budget_stops_a_hopeless_search(self):
        with tempfile.TemporaryDirectory() as home:
            for index in range(300):
                folder = Path(home) / f"folder{index:03d}"
                folder.mkdir()
                (folder / f"file{index}.txt").write_text("x", encoding="utf-8")
            started = time.monotonic()
            self.assertIsNone(kira_open.find_file("zzzznope", search_dirs=[home], time_budget=0.5))
            self.assertLess(time.monotonic() - started, 3.0)


if __name__ == "__main__":
    unittest.main()
