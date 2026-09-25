"""Files, applications and web pages: one open-resolver for EN/FR/AR.

KIRA must open things only when the user asks for it, resolve what was asked
(web page vs installed app vs local file), and answer in the conversation
language. All opening happens through kira_open so the behaviour is identical
for native, web and HTTP clients.
"""
import ast
import os
import re
import shutil
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
        self.assertIsNone(self.parse("how do I open a pdf file ?"))

    def test_this_pc_and_drives(self):
        self.assertEqual(self.parse("ouvre ce pc"), {"action": "open_folder", "target": "ce pc"})
        self.assertEqual(self.parse("open this pc"), {"action": "open_folder", "target": "this pc"})
        self.assertEqual(self.parse("ouvre mon pc"), {"action": "open_folder", "target": "pc"})
        self.assertEqual(self.parse("ouvre le disque c"), {"action": "open_folder", "target": "disque c"})
        self.assertEqual(self.parse("open c drive"), {"action": "open_folder", "target": "c drive"})
        self.assertEqual(self.parse("ouvre c:"), {"action": "open_folder", "target": "c"})
        self.assertEqual(self.parse("ouvre disque dur"), {"action": "open_folder", "target": "disque dur"})
        self.assertEqual(self.parse("ouvre corbeille"), {"action": "open_folder", "target": "corbeille"})

    def test_all_requests_ask_for_every_match(self):
        self.assertEqual(self.parse("ouvre tous les rapports"), {"action": "open_file", "target": "rapports", "all": True})
        self.assertEqual(self.parse("open all reports"), {"action": "open_file", "target": "reports", "all": True})
        self.assertEqual(self.parse("ouvre toutes les photos"), {"action": "open_folder", "target": "photos", "all": True})
        self.assertEqual(self.parse("ouvre tous les dossiers"), {"action": "open_folder", "target": "dossiers", "all": True})
        self.assertIsNone(self.parse("ouvre tous"))

    def test_nested_folder_locations_are_understood(self):
        self.assertEqual(
            self.parse("ouvre le dossier projets dans documents"),
            {"action": "open_folder", "target": "projets", "parent": "documents"},
        )
        self.assertEqual(
            self.parse("ouvre le dossier missions dans le dossier travail"),
            {"action": "open_folder", "target": "missions", "parent": "travail"},
        )
        self.assertEqual(
            self.parse("open projects in documents"),
            {"action": "open_folder", "target": "projects", "parent": "documents"},
        )
        self.assertEqual(
            self.parse("ouvre le dossier missions sur le disque d"),
            {"action": "open_folder", "target": "missions", "parent": "d"},
        )
        self.assertEqual(
            self.parse("ouvre le fichier rapport dans le disque d"),
            {"action": "open_file", "target": "rapport", "parent": "d"},
        )

    def test_a_filename_with_extension_is_never_split_at_in(self):
        self.assertEqual(self.parse("open my notes in english.txt"), {"action": "open_file", "target": "notes in english.txt"})

    def test_a_bare_folder_request_opens_documents(self):
        self.assertEqual(self.parse("open folder"), {"action": "open_folder", "target": "documents"})
        self.assertEqual(self.parse("ouvre le dossier"), {"action": "open_folder", "target": "documents"})

    def test_open_wishes_are_recognized(self):
        self.assertEqual(self.parse("je veux que tu ouvres facebook"), {"action": "open_url", "target": "https://www.facebook.com"})
        self.assertEqual(self.parse("je veux ouvrir facebook"), {"action": "open_url", "target": "https://www.facebook.com"})
        self.assertEqual(self.parse("j'aimerais ouvrir google maps"), {"action": "open_url", "target": "https://www.google.com/maps"})
        self.assertEqual(self.parse("je veux bien ouvrir chrome"), {"action": "open_app", "target": "chrome"})
        self.assertEqual(self.parse("i want you to open youtube"), {"action": "open_url", "target": "https://www.youtube.com"})
        self.assertIsNone(self.parse("je veux que tu ouvriez gmail"))

    def test_nicknames_and_typos_reach_the_real_service(self):
        self.assertEqual(self.parse("ouvre insta"), {"action": "open_url", "target": "https://www.instagram.com"})
        self.assertEqual(self.parse("ouvre instagrame"), {"action": "open_url", "target": "https://www.instagram.com"})
        self.assertEqual(self.parse("ouvre insta gram"), {"action": "open_url", "target": "https://www.instagram.com"})
        self.assertEqual(self.parse("open facebok"), {"action": "open_url", "target": "https://www.facebook.com"})
        self.assertEqual(self.parse("open yutube"), {"action": "open_url", "target": "https://www.youtube.com"})
        self.assertEqual(self.parse("ouvre fb"), {"action": "open_url", "target": "https://www.facebook.com"})

    def test_a_file_with_extension_stays_a_file_despite_similar_app_names(self):
        self.assertEqual(self.parse("open nots.txt"), {"action": "open_file", "target": "nots.txt"})

    def test_named_browser_overrides_the_default(self):
        self.assertEqual(self.parse("ouvre facebook sur firefox"), {"action": "open_url", "target": "https://www.facebook.com", "browser": "firefox"})
        self.assertEqual(self.parse("open google maps in edge"), {"action": "open_url", "target": "https://www.google.com/maps", "browser": "edge"})
        self.assertEqual(self.parse("ouvre github dans google chrome"), {"action": "open_url", "target": "https://github.com", "browser": "chrome"})
        self.assertEqual(self.parse("open spotify with brave"), {"action": "open_url", "target": "https://open.spotify.com", "browser": "brave"})
        self.assertEqual(self.parse("ouvre chrome"), {"action": "open_app", "target": "chrome"})

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

    def test_search_can_name_its_browser(self):
        self.assertEqual(self.parse("search weather on firefox"), {"action": "search", "query": "weather", "browser": "firefox"})
        self.assertEqual(self.parse("recherche la météo sur chrome"), {"action": "search", "query": "la météo", "browser": "chrome"})

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


class DriveParsingTests(unittest.TestCase):
    def test_drive_phrases(self):
        for phrase, letter in [
            ("c", "c"), ("C:", "c"), ("c:\\", "c"), ("disque c", "c"),
            ("le disque c", "c"), ("lecteur d", "d"), ("c drive", "c"),
            ("drive e", "e"), ("disque dur", "c"), ("hard drive", "c"),
            ("hard disk", "c"), ("disque local", "c"), ("قرص سي", "c"),
            ("القرص دي", "d"),
        ]:
            self.assertEqual(kira_open.parse_drive(phrase), letter, phrase)

    def test_non_drive_phrases(self):
        for phrase in ["chrome", "documents", "", "téléchargements"]:
            self.assertIsNone(kira_open.parse_drive(phrase), phrase)

    def test_drives_are_resolved_as_folders(self):
        for phrase in ["ce pc", "this pc", "mon pc", "poste de travail", "disque c", "c:", "disque dur", "hard drive"]:
            self.assertEqual(kira_open.resolve_open(phrase)["kind"], "folder", phrase)


class FolderSearchTests(unittest.TestCase):
    def test_find_folder_by_name_in_the_home(self):
        with tempfile.TemporaryDirectory() as home:
            documents = Path(home) / "Documents"
            documents.mkdir()
            projects = documents / "Projets Web"
            projects.mkdir()
            self.assertEqual(
                kira_open.find_folder("projets web", search_dirs=[home]),
                str(projects),
            )
            self.assertIsNone(kira_open.find_folder("zzzqqq", search_dirs=[home]))

    def test_open_folder_routes_alias_search_and_documents(self):
        with tempfile.TemporaryDirectory() as home:
            documents = Path(home) / "Documents"
            documents.mkdir()
            projects = documents / "Projets Web"
            projects.mkdir()
            opened = []
            with patch.object(kira_open, "open_path", side_effect=lambda path: opened.append(path) or True), \
                 patch.object(kira_open, "common_file_dirs", return_value=[home]):
                self.assertTrue(kira_open.open_folder("documents", base_home=home))
                self.assertTrue(kira_open.open_folder("documents"))
                opened.clear()
                self.assertTrue(kira_open.open_folder("Projets Web", base_home=home))
                self.assertTrue(str(opened[-1]).endswith("Projets Web"))


class OpenAppFallbackTests(unittest.TestCase):
    """The requested flow: check the installed app first; never scan the
    user's documents; otherwise open a correct browser page."""

    def run_open_app(self, name):
        opened = []
        with patch.object(kira_open.subprocess, "Popen", side_effect=OSError("not installed")), \
             patch.object(kira_open.shutil, "which", return_value=None), \
             patch.object(kira_open, "find_start_menu_app", return_value=None), \
             patch.object(kira_open, "find_installed_exe", return_value=None), \
             patch.object(kira_open, "find_installed_exe_deep", return_value=None), \
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


class BrowserPreferenceTests(unittest.TestCase):
    """Pages and searches open in Chrome by default, unless the request
    names another browser (or the user remembered one)."""

    def test_default_browser_is_chrome_and_can_be_changed(self):
        self.assertEqual(kira_open.DEFAULT_BROWSER, "chrome")
        try:
            kira_open.set_default_browser("Mozilla Firefox")
            self.assertEqual(kira_open.default_browser(), "firefox")
        finally:
            kira_open.set_default_browser("chrome")
        self.assertEqual(kira_open.default_browser(), "chrome")

    def test_open_url_uses_the_named_browser_controller(self):
        controller = Mock()
        with patch.object(kira_open.webbrowser, "get", return_value=controller) as get, \
             patch.object(kira_open.webbrowser, "open") as fallback:
            self.assertTrue(kira_open.open_url("https://example.com", browser="firefox"))
            get.assert_called_once_with("firefox")
            controller.open.assert_called_once_with("https://example.com")
            fallback.assert_not_called()

    def test_the_default_browser_applies_without_an_override(self):
        controller = Mock()
        with patch.object(kira_open.webbrowser, "get", return_value=controller) as get, \
             patch.object(kira_open.webbrowser, "open"):
            self.assertTrue(kira_open.open_url("example.com"))
            get.assert_called_once_with("chrome")
            controller.open.assert_called_once_with("https://example.com")

    def test_open_url_falls_back_to_the_system_default(self):
        with patch.object(kira_open.webbrowser, "get", side_effect=kira_open.webbrowser.Error("none")), \
             patch.object(kira_open.webbrowser, "open", return_value=True) as fallback:
            self.assertTrue(kira_open.open_url("https://example.com", browser="firefox"))
            fallback.assert_called_once_with("https://example.com")

    def test_find_browser_exe_searches_windows_install_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(kira_open.find_browser_exe("chrome", roots=[tmp]))
            application = Path(tmp) / "Google" / "Chrome" / "Application"
            application.mkdir(parents=True)
            (application / "chrome.exe").write_text("", encoding="utf-8")
            self.assertEqual(kira_open.find_browser_exe("google chrome", roots=[tmp]), str(application / "chrome.exe"))
            self.assertIsNone(kira_open.find_browser_exe("lynx", roots=[tmp]))


class WholePcCoverageTests(unittest.TestCase):
    """KIRA must reach files, folders and apps anywhere on the PC."""

    def test_file_outside_the_common_folders_is_found_on_the_drives(self):
        with tempfile.TemporaryDirectory() as drive, tempfile.TemporaryDirectory() as home:
            (Path(drive) / "Divers").mkdir()
            target = Path(drive) / "Divers" / "rapport annuel.pdf"
            target.write_text("x", encoding="utf-8")
            opened = []
            with patch.object(kira_open, "deep_search_dirs", return_value=[drive]), \
                 patch.object(kira_open, "open_path", side_effect=lambda path: opened.append(path) or True):
                self.assertTrue(kira_open.open_file("rapport annuel.pdf", base_home=home))
                self.assertTrue(str(opened[-1]).endswith("rapport annuel.pdf"))

    def test_folder_anywhere_on_the_pc_is_found(self):
        with tempfile.TemporaryDirectory() as drive, tempfile.TemporaryDirectory() as home:
            folder = Path(drive) / "Divers" / "Projets 2026"
            folder.mkdir(parents=True)
            opened = []
            with patch.object(kira_open, "deep_search_dirs", return_value=[drive]), \
                 patch.object(kira_open, "open_path", side_effect=lambda path: opened.append(path) or True):
                self.assertTrue(kira_open.open_folder("Projets 2026", base_home=home))
                self.assertTrue(str(opened[-1]).endswith("Projets 2026"))

    def test_missing_everywhere_returns_false_quickly(self):
        with tempfile.TemporaryDirectory() as drive, tempfile.TemporaryDirectory() as home:
            with patch.object(kira_open, "deep_search_dirs", return_value=[drive]):
                started = time.monotonic()
                self.assertFalse(kira_open.open_file("zzqqxxx.pdf", base_home=home))
                self.assertLess(time.monotonic() - started, 5.0)

    def test_deep_exe_walk_finds_portable_apps(self):
        with tempfile.TemporaryDirectory() as apps:
            vendor = Path(apps) / "SomeVendor" / "MyTool" / "bin"
            vendor.mkdir(parents=True)
            (vendor / "mytool.exe").write_text("", encoding="utf-8")
            found = kira_open.find_installed_exe_deep("my tool", roots=[apps])
            self.assertTrue(found and found.endswith("mytool.exe"), found)
            self.assertIsNone(kira_open.find_installed_exe_deep("absent tool", roots=[apps]))

    def test_open_app_uses_the_path_lookup(self):
        located = os.path.join(os.sep, "usr", "bin", "mytool")
        opened = []
        with patch.object(kira_open.shutil, "which", return_value=located) as which, \
             patch.object(kira_open.subprocess, "Popen", side_effect=OSError("no exec in tests")), \
             patch.object(kira_open, "open_path", side_effect=lambda path: opened.append(path) or True):
            self.assertTrue(kira_open.open_app("mytool"))
            which.assert_called_once_with("mytool")
            self.assertEqual(opened, [located])

    def test_available_drives_have_a_root_form(self):
        for drive in kira_open.available_drives():
            self.assertTrue(drive.endswith(":\\" ) or drive == os.sep, drive)


class NestedLocationTests(unittest.TestCase):
    """A folder inside a folder, possibly on another drive, must open."""

    def test_resolve_parent_dir_from_path_alias_and_name(self):
        with tempfile.TemporaryDirectory() as home:
            documents = Path(home) / "Documents"
            documents.mkdir()
            parent = documents / "travail"
            parent.mkdir()
            self.assertEqual(kira_open.resolve_parent_dir(str(parent)), str(parent))
            self.assertEqual(kira_open.resolve_parent_dir("documents", base_home=home), str(documents))
            self.assertIsNone(kira_open.resolve_parent_dir("zzqq", base_home=home))

    def test_folder_inside_a_named_parent_opens_directly(self):
        with tempfile.TemporaryDirectory() as home:
            missions = Path(home) / "missions"
            missions.mkdir()
            secretariat = missions / "secretariat"
            secretariat.mkdir()
            opened = []
            with patch.object(kira_open, "open_path", side_effect=lambda path: opened.append(path) or True):
                self.assertTrue(kira_open.open_folder("secretariat", base_home=home, parent="missions"))
                self.assertTrue(str(opened[-1]).endswith("secretariat"))

    def test_file_inside_a_named_parent_opens(self):
        with tempfile.TemporaryDirectory() as home:
            missions = Path(home) / "missions"
            missions.mkdir()
            report = missions / "rapport final.pdf"
            report.write_text("x", encoding="utf-8")
            opened = []
            with patch.object(kira_open, "open_path", side_effect=lambda path: opened.append(path) or True):
                self.assertTrue(kira_open.open_file("rapport final.pdf", base_home=home, parent="missions"))
                self.assertTrue(str(opened[-1]).endswith("rapport final.pdf"))

    def test_deep_folder_search_reaches_the_second_drive(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            deep = Path(second) / "travail" / "missions" / "secretariat"
            deep.mkdir(parents=True)
            opened = []
            with patch.object(kira_open, "deep_search_dirs", return_value=[first, second]), \
                 patch.object(kira_open, "open_path", side_effect=lambda path: opened.append(path) or True):
                self.assertTrue(kira_open.open_folder("secretariat"))
                self.assertTrue(str(opened[-1]).endswith("secretariat"))


class AskWhichOneTests(unittest.TestCase):
    """Several same-named files: KIRA asks, the answer opens the right one."""

    def setUp(self):
        commands.clear_pending_open()
        self.drive_c = tempfile.mkdtemp()
        self.drive_d = tempfile.mkdtemp()
        for index in (4, 3, 2, 1):
            folder = Path(self.drive_c) / f"doc{index}" / "notes"
            folder.mkdir(parents=True)
            (folder / f"rapport{index}.pdf").write_text("x", encoding="utf-8")
        extra = Path(self.drive_d) / "archives" / "rapport5.pdf"
        extra.parent.mkdir(parents=True)
        extra.write_text("x", encoding="utf-8")
        self.opened = []
        self.backend = SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=lambda text: kira_open.parse_open_command(text),
            execute_action=lambda data: self._execute(data),
            build_reply=lambda language, name, target: f"J'ouvre {target}.",
            resolve_open_matches=lambda parsed: (
                None if (parsed["action"] == "open_folder"
                         and (kira_open.fold(parsed["target"]) in kira_open.FOLDER_ALIASES
                              or kira_open.parse_drive(parsed["target"])))
                else kira_open.file_matches(parsed["target"], parent=parsed.get("parent"))
            ),
        )
        self.drive_home = tempfile.mkdtemp()  # empty "standard" folders
        patcher = patch.multiple(kira_open, deep_search_dirs=lambda: [self.drive_c, self.drive_d],
                                 common_file_dirs=lambda base_home=None: [self.drive_home])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._cleanup_dirs)

    def _cleanup_dirs(self):
        import shutil
        for path in (self.drive_c, self.drive_d, self.drive_home):
            shutil.rmtree(path, ignore_errors=True)

    def _execute(self, data):
        if data.get("all"):
            matches = kira_open.file_matches(data["target"], parent=data.get("parent"), deep_always=True)
            opened = 0
            for path in matches[:20]:
                self.opened.append(path)
                opened += 1
            return opened
        self.opened.append(data.get("target"))
        return True

    def tearDown(self):
        commands.clear_pending_open()

    def test_multiple_matches_ask_which_one(self):
        result = commands.process_command(self.backend, "ouvre le fichier rapport", reply_language="fr")
        self.assertTrue(result["needs_choice"])
        self.assertIn("Lequel", result["response"])
        self.assertEqual(len(result["candidates"]), 5)
        names = [Path(path).name for path in result["candidates"]]
        self.assertEqual(names, sorted(names), "candidates must be listed in a stable order")

    def test_the_question_explains_how_to_answer(self):
        result = commands.process_command(self.backend, "ouvre le fichier rapport", reply_language="fr")
        self.assertIn("numéro", result["response"])
        self.assertIn("tous", result["response"])
        self.assertIn("annule", result["response"])

    def test_answers_are_understood_in_many_forms(self):
        for answer in ["le 2", "n°2", "n2", "numero 2", "le deuxième", "2"]:
            commands.clear_pending_open()
            commands.process_command(self.backend, "ouvre le fichier rapport", reply_language="fr")
            self.opened.clear()
            result = commands.process_command(self.backend, answer, reply_language="fr")
            self.assertEqual(len(self.opened), 1, answer)
            self.assertTrue(self.opened[0].endswith("rapport2.pdf"), answer)

    def test_a_stray_choice_without_a_pending_question_is_explained(self):
        commands.clear_pending_open()
        result = commands.process_command(self.backend, "2", reply_language="fr")
        self.assertEqual(result["action"], "none")
        self.assertIn("rien à choisir", result["response"])
        self.assertEqual(self.opened, [])

    def test_the_choice_stays_available_for_ten_minutes(self):
        commands.process_command(self.backend, "ouvre le fichier rapport", reply_language="fr")
        import time as time_module
        stale = commands._PENDING_OPEN["time"] - 400  # 6-7 minutes old
        commands._PENDING_OPEN["time"] = stale
        result = commands.process_command(self.backend, "2", reply_language="fr")
        self.assertEqual(len(self.opened), 1)

    def test_the_answer_opens_the_chosen_one(self):
        commands.process_command(self.backend, "ouvre le fichier rapport", reply_language="fr")
        result = commands.process_command(self.backend, "2", reply_language="fr")
        self.assertEqual(len(self.opened), 1)
        self.assertTrue(self.opened[0].endswith(".pdf"))
        self.assertIsNone(commands.pending_open())

    def test_all_answer_opens_every_candidate(self):
        commands.process_command(self.backend, "ouvre le fichier rapport", reply_language="fr")
        result = commands.process_command(self.backend, "tous", reply_language="fr")
        self.assertEqual(len(self.opened), 5)
        self.assertTrue(result["success"])

    def test_cancel_answer_closes_the_question(self):
        commands.process_command(self.backend, "ouvre le fichier rapport", reply_language="fr")
        result = commands.process_command(self.backend, "annule", reply_language="fr")
        self.assertIn("annule", result["response"])
        self.assertIsNone(commands.pending_open())
        self.assertEqual(self.opened, [])

    def test_ordinal_words_pick_too(self):
        commands.process_command(self.backend, "ouvre le fichier rapport", reply_language="fr")
        commands.process_command(self.backend, "le premier", reply_language="fr")
        self.assertEqual(len(self.opened), 1)
        self.assertTrue(self.opened[0].endswith("rapport1.pdf"))

    def test_all_request_opens_everything_at_once(self):
        result = commands.process_command(self.backend, "ouvre tous les fichiers rapport", reply_language="fr")
        self.assertTrue(result["success"])
        self.assertEqual(result["response"], commands.message("opened_all", "fr", count=5))
        self.assertEqual(len(self.opened), 5)

    def test_aliases_and_drives_are_never_disambiguated(self):
        result = commands.process_command(self.backend, "ouvre téléchargements", reply_language="fr")
        self.assertFalse(result.get("needs_choice"))
        self.assertEqual(len(self.opened), 1)

    def test_one_in_common_plus_others_on_drives_still_asks(self):
        """The reported bug: one match in the usual places must not be opened
        while same-named files exist elsewhere on the PC."""
        documents = Path(self.drive_home) / "Documents"
        documents.mkdir()
        (documents / "bilan.pdf").write_text("x", encoding="utf-8")
        extra = Path(self.drive_d) / "travail" / "missions"
        extra.mkdir(parents=True)
        (extra / "bilan.pdf").write_text("x", encoding="utf-8")
        deep = Path(self.drive_c) / "divers" / "2025"
        deep.mkdir(parents=True)
        (deep / "bilan.pdf").write_text("x", encoding="utf-8")
        result = commands.process_command(self.backend, "ouvre le fichier bilan", reply_language="fr")
        self.assertTrue(result["needs_choice"], "one local match plus others must ask")
        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(self.opened, [])

    def test_one_single_file_deep_on_a_drive_opens_directly(self):
        deep = Path(self.drive_d) / "secret" / "tres" / "profond"
        deep.mkdir(parents=True)
        (deep / "unique.txt").write_text("x", encoding="utf-8")
        result = commands.process_command(self.backend, "ouvre le fichier unique.txt", reply_language="fr")
        self.assertFalse(result.get("needs_choice"))
        self.assertEqual(len(self.opened), 1)
        self.assertTrue(self.opened[0].endswith("unique.txt"))

    def test_a_named_location_limits_the_search(self):
        archives = Path(self.drive_d) / "archives"
        (archives / "special.pdf").write_text("x", encoding="utf-8")
        elsewhere = Path(self.drive_c) / "somewhere"
        elsewhere.mkdir(parents=True)
        (elsewhere / "special.pdf").write_text("x", encoding="utf-8")
        result = commands.process_command(self.backend, "ouvre le fichier special dans le dossier archives", reply_language="fr")
        self.assertFalse(result.get("needs_choice"))
        self.assertEqual(len(self.opened), 1)
        self.assertTrue(self.opened[0].endswith("special.pdf"))

    def test_a_single_match_opens_without_asking(self):
        for index in (2, 3, 4):
            (Path(self.drive_c) / f"doc{index}" / "notes" / f"rapport{index}.pdf").unlink()
        (Path(self.drive_d) / "archives" / "rapport5.pdf").unlink()
        result = commands.process_command(self.backend, "ouvre le fichier rapport", reply_language="fr")
        self.assertFalse(result.get("needs_choice"))
        self.assertEqual(len(self.opened), 1)


if __name__ == "__main__":
    unittest.main()


class FindOpenParseTests(unittest.TestCase):
    """« Cherche/trouve … sur le disque X et ouvre chaque … » is an open-all
    search command, not a chat message."""

    def parse(self, text):
        return kira_open.parse_open_command(text)

    def test_dell_request_collapses_to_open_all_on_c(self):
        self.assertEqual(
            self.parse("cherche moi les dossier dell sur le c et ouvre chaque dossier qui porte le nom dell"),
            {"action": "open_folder", "target": "dell", "parent": "c", "all": True})

    def test_find_files_on_drive_and_open_each(self):
        self.assertEqual(
            self.parse("cherche les fichiers rapport sur le disque d et ouvre chaque fichier"),
            {"action": "open_file", "target": "rapport", "parent": "d", "all": True})

    def test_named_phrase_without_drive(self):
        self.assertEqual(
            self.parse("ouvre chaque dossier qui porte le nom dell"),
            {"action": "open_folder", "target": "dell", "all": True})

    def test_english_find_and_open(self):
        self.assertEqual(
            self.parse("open every folder named dell"),
            {"action": "open_folder", "target": "dell", "all": True})

    def test_bare_all_folders_keep_the_name(self):
        self.assertEqual(
            self.parse("ouvre tous les dossiers"),
            {"action": "open_folder", "target": "dossiers", "all": True})

    def test_ordinary_requests_are_unchanged(self):
        self.assertEqual(self.parse("open folder downloads"), {"action": "open_folder", "target": "downloads"})
        self.assertEqual(
            self.parse("ouvre le dossier missions dans le dossier travail"),
            {"action": "open_folder", "target": "missions", "parent": "travail"})
        self.assertIsNone(self.parse("open chrome and search news"))

    def test_bare_find_in_local_drive_c(self):
        self.assertEqual(
            self.parse("cherche le dossier dell dans tous le local c"),
            {"action": "open_folder", "target": "dell", "parent": "c"})

    def test_bare_find_plural_opens_all(self):
        self.assertEqual(
            self.parse("cherche les dossiers dell dans tout le local c"),
            {"action": "open_folder", "target": "dell", "parent": "c", "all": True})

    def test_bare_find_whole_pc_and_polite_forms(self):
        self.assertEqual(self.parse("cherche le dossier dell"), {"action": "open_folder", "target": "dell"})
        self.assertEqual(self.parse("cherche dell dans le c"), {"action": "open_folder", "target": "dell", "parent": "c"})
        self.assertEqual(self.parse("peux-tu chercher le dossier dell dans le local c"),
                         {"action": "open_folder", "target": "dell", "parent": "c"})
        self.assertEqual(self.parse("find the dell folder on my pc"), {"action": "open_folder", "target": "dell"})
        self.assertEqual(self.parse("cherche les fichiers rapport sur le disque d"),
                         {"action": "open_file", "target": "rapport", "parent": "d", "all": True})

    def test_generic_searches_stay_out_of_the_local_finder(self):
        self.assertIsNone(self.parse("cherche la recette de gâteau"))
        self.assertIsNone(self.parse("cherche le dossier recette sur internet"))


class FindOpenPruneTests(unittest.TestCase):
    """On a drive root (« sur le c ») system folders must be searched too;
    inside a named folder, pruning stays on for speed."""

    def setUp(self):
        self.tree = tempfile.mkdtemp()
        self.expected = []
        for sub in ["Program Files", "Windows/Temp", "Users/test/AppData/Local", "travail"]:
            folder = Path(self.tree) / sub / "dell"
            folder.mkdir(parents=True)
            self.expected.append(str(folder))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tree, ignore_errors=True)

    def test_no_pruning_on_a_drive_root(self):
        found = kira_open.find_folder_matches("dell", search_dirs=[self.tree], prune_system=False,
                                              max_entries=100000, time_budget=10.0, limit=10)
        self.assertEqual(sorted(found), sorted(self.expected))

    def test_pruning_is_the_default_inside_a_folder(self):
        found = kira_open.find_folder_matches("dell", search_dirs=[self.tree], limit=10)
        self.assertIn(str(Path(self.tree) / "travail" / "dell"), found)
        self.assertNotIn(str(Path(self.tree) / "Program Files" / "dell"), found)

    def test_parent_branch_passes_the_right_prune_flag(self):
        calls = []
        real_find = kira_open.find_folder_matches

        def spy(name, search_dirs=None, **kwargs):
            calls.append(kwargs.get("prune_system"))
            return real_find(name, search_dirs=search_dirs, **kwargs)

        with patch.multiple(kira_open, find_folder_matches=spy,
                            resolve_parent_dir=lambda parent, base_home=None: self.tree):
            kira_open.folder_matches("dell", parent="c")
        self.assertEqual(calls, [True], "a non-root parent keeps system folders pruned")

        calls.clear()
        with patch.multiple(kira_open, find_folder_matches=spy,
                            resolve_parent_dir=lambda parent, base_home=None: "C:\\"):
            kira_open.folder_matches("dell", parent="c")
        self.assertEqual(calls, [False], "a drive root must search system folders")


class FindOpenExecutionTests(unittest.TestCase):
    """The whole sentence runs as one search and opens every match."""

    def setUp(self):
        commands.clear_pending_open()
        self.folders_c = [
            "C:\\Program Files\\dell",
            "C:\\Users\\test\\AppData\\Local\\dell",
            "C:\\Windows\\Temp\\dell",
            "C:\\travail\\dell",
        ]
        self.searches = []
        self.opened = []

        def fake_folder_matches(name, parent=None, base_home=None, limit=10, deep_always=True):
            self.searches.append({"name": name, "parent": parent})
            return list(self.folders_c) if kira_open.fold(parent) == "c" else []

        self.backend = SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=lambda text: kira_open.parse_open_command(text),
            execute_action=lambda data: self._execute(data),
            build_reply=lambda language, name, target: f"J'ouvre {target}.",
            resolve_open_matches=lambda parsed: (
                None if (parsed["action"] == "open_folder"
                         and (kira_open.fold(parsed["target"]) in kira_open.FOLDER_ALIASES
                              or kira_open.parse_drive(parsed["target"])))
                else kira_open.folder_matches(parsed["target"], parent=parsed.get("parent"))
            ),
        )
        patcher = patch.object(kira_open, "folder_matches", fake_folder_matches)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(commands.clear_pending_open)

    def _execute(self, data):
        if data.get("all"):
            matches = data.get("candidates")
            if not (isinstance(matches, list) and matches
                    and all(isinstance(path, str) for path in matches)):
                matches = kira_open.folder_matches(data["target"], parent=data.get("parent"))
            opened = 0
            for path in matches[:20]:
                self.opened.append(path)
                opened += 1
            return opened
        self.opened.append(data.get("target"))
        return True

    def test_dell_sentence_opens_every_folder_on_c_once(self):
        result = commands.process_command(
            self.backend,
            "cherche moi les dossier dell sur le c et ouvre chaque dossier qui porte le nom dell",
            reply_language="fr")
        self.assertTrue(result["success"])
        self.assertIn("4", result["response"])
        self.assertEqual(self.searches, [{"name": "dell", "parent": "c"}],
                         "the search must run exactly once")
        self.assertEqual(self.opened, self.folders_c)
        self.assertTrue(all(path.startswith("C:\\") for path in self.opened))

    def test_bare_find_singular_asks_with_the_list(self):
        result = commands.process_command(
            self.backend,
            "cherche le dossier dell dans tous le local c",
            reply_language="fr")
        self.assertTrue(result["needs_choice"])
        self.assertNotEqual(result.get("action"), "chat")
        self.assertEqual(self.searches, [{"name": "dell", "parent": "c"}])
        self.assertEqual(result["candidates"], self.folders_c)

    def test_bare_find_plural_opens_all_once(self):
        result = commands.process_command(
            self.backend,
            "cherche les dossiers dell dans tout le local c",
            reply_language="fr")
        self.assertTrue(result["success"])
        self.assertIn("4", result["response"])
        self.assertEqual(self.searches, [{"name": "dell", "parent": "c"}])
        self.assertEqual(self.opened, self.folders_c)

    def test_voice_agent_reuses_the_candidates(self):
        source = (ROOT / "kira_voice_agent.py").read_text()
        self.assertIn('action_data.get("candidates")', source,
                      "the voice agent must reuse the single search result")


class BreadthFirstSearchTests(unittest.TestCase):
    """A huge sibling tree (Program Files on a real C:) must not swallow the
    whole budget before the other matches are reached: the walk is
    breadth-first, so shallow matches are always found first."""

    def test_folders_behind_a_huge_tree_are_found(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        huge = root / "aaa_Program_Files"
        huge.mkdir()
        for index in range(600):
            (huge / f"pad{index:04d}").mkdir()
        expected = []
        for sub in ["mmm", "zzz1", "zzz2"]:
            folder = root / sub / "dell"
            folder.mkdir(parents=True)
            expected.append(str(folder))
        found = kira_open.find_folder_matches("dell", search_dirs=[str(root)], prune_system=False,
                                              max_entries=100, time_budget=30.0, limit=10)
        self.assertEqual(sorted(found), sorted(expected))

    def test_files_behind_a_huge_tree_are_found(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        huge = root / "aaa_big"
        huge.mkdir()
        for index in range(300):
            folder = huge / f"pad{index:04d}"
            folder.mkdir()
            (folder / "junk.log").write_text("x", encoding="utf-8")
        expected = []
        for sub in ["mmm", "zzz"]:
            target = root / sub / "dell.txt"
            target.parent.mkdir(parents=True)
            target.write_text("x", encoding="utf-8")
            expected.append(str(target))
        found = kira_open.find_file_matches("dell.txt", search_dirs=[str(root)], prune_system=False,
                                            max_entries=100, time_budget=30.0, limit=10)
        self.assertEqual(sorted(found), sorted(expected))

    def test_drive_root_budgets_cover_system_folders(self):
        source = (ROOT / "kira_open.py").read_text()
        self.assertIn("max_entries=500000 if is_root else 150000", source)
        self.assertIn("time_budget=45.0 if is_root else 20.0", source)
        self.assertIn("prune_system=not is_root,\n                                     max_entries=500000",
                      source, "file searches on a drive root must include system folders too")

    def test_open_all_cap_is_twenty(self):
        source = (ROOT / "kira_voice_agent.py").read_text()
        self.assertIn("for path in matches[:20]:", source)
        self.assertIn("kira_open.folder_matches(target, parent=parent, limit=20)", source)
