"""Programming agent: sandboxed workspace, approval-gated writes, real edits.

kira_code jails every path inside ONE workspace root (KIRA_CODE_DIR or
kira_workspace/), refuses escapes, and returns structured data. The registry
tests cover the consequential flags; here the jail itself and the tools get
exercised against a real temporary directory.
"""
import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

import kira_agents
import kira_commands as commands
import kira_code


class WorkspaceJailTests(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("KIRA_CODE_DIR")
        self.root = Path(tempfile.mkdtemp(prefix="kira-code-test-"))
        os.environ["KIRA_CODE_DIR"] = str(self.root)

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("KIRA_CODE_DIR", None)
        else:
            os.environ["KIRA_CODE_DIR"] = self._previous

    def test_workspace_root_follows_the_env_var(self):
        self.assertEqual(kira_code.workspace_root(), self.root.resolve())

    def test_absolute_and_drive_paths_are_refused(self):
        self.assertEqual(kira_code.resolve_path("/etc/passwd")[1]["error_code"],
                         "path_outside_workspace")
        self.assertEqual(kira_code.resolve_path("C:/Windows/system32")[1]["error_code"],
                         "path_outside_workspace")
        self.assertEqual(kira_code.resolve_path("~/.ssh/id_rsa")[1]["error_code"],
                         "path_outside_workspace")

    def test_parent_escape_is_refused_everywhere(self):
        for tool in (kira_code.write_file, kira_code.read_file, kira_code.delete_path):
            result = tool("../escape.txt")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "path_outside_workspace")
        self.assertEqual(kira_code.scaffold_project("../outside")["error_code"],
                         "invalid_name")  # separators in the name are refused outright

    def test_deleting_the_whole_workspace_is_refused(self):
        # "." resolves to the root itself and is refused before deletion.
        result = kira_code.delete_path(".")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "path_required")


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("KIRA_CODE_DIR")
        self.root = Path(tempfile.mkdtemp(prefix="kira-code-test-"))
        os.environ["KIRA_CODE_DIR"] = str(self.root)

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("KIRA_CODE_DIR", None)
        else:
            os.environ["KIRA_CODE_DIR"] = self._previous

    def test_python_scaffold_creates_runnable_project(self):
        result = kira_code.scaffold_project("todo-app", template="python")
        self.assertTrue(result["ok"])
        main = self.root / "todo-app" / "main.py"
        self.assertTrue(main.exists())
        self.assertIn("def main", main.read_text(encoding="utf-8"))

    def test_each_template_produces_its_own_files(self):
        for template, expected in (("web", "index.html"), ("node", "package.json"),
                                   ("empty", None)):
            result = kira_code.scaffold_project(f"p-{template}", template=template)
            self.assertTrue(result["ok"], result)
            target = self.root / f"p-{template}" / expected if expected else self.root / f"p-{template}"
            if expected:
                self.assertTrue(target.exists())
            else:
                self.assertEqual(list(target.iterdir()), [])

    def test_duplicate_name_is_refused(self):
        kira_code.scaffold_project("twice")
        self.assertEqual(kira_code.scaffold_project("twice")["error_code"], "already_exists")

    def test_bad_names_are_refused(self):
        for name in ("", "..", "a/b", "a:b"):
            self.assertFalse(kira_code.scaffold_project(name)["ok"])


class EditAndSearchTests(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("KIRA_CODE_DIR")
        self.root = Path(tempfile.mkdtemp(prefix="kira-code-test-"))
        os.environ["KIRA_CODE_DIR"] = str(self.root)
        kira_code.write_file("app/util.py", "def add(a, b):\n    return a + b\n")

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("KIRA_CODE_DIR", None)
        else:
            os.environ["KIRA_CODE_DIR"] = self._previous

    def test_read_returns_the_file_content(self):
        result = kira_code.read_file("app/util.py")
        self.assertTrue(result["ok"])
        self.assertIn("return a + b", result["content"])

    def test_apply_edit_replaces_one_exact_block(self):
        result = kira_code.apply_edit("app/util.py", old="return a + b", new="return a + b  # sum")
        self.assertTrue(result["ok"])
        self.assertIn("# sum", kira_code.read_file("app/util.py")["content"])

    def test_apply_edit_refuses_missing_text(self):
        result = kira_code.apply_edit("app/util.py", old="not present anywhere")
        self.assertEqual(result["error_code"], "old_not_found")
        self.assertFalse(result["ok"])

    def test_apply_edit_refuses_ambiguous_match(self):
        kira_code.write_file("app/dup.py", "x = 1\nx = 1\n")
        result = kira_code.apply_edit("app/dup.py", old="x = 1", new="x = 2")
        self.assertEqual(result["error_code"], "ambiguous_match")

    def test_search_finds_matches_with_line_numbers(self):
        result = kira_code.search_code("add", path="app")
        self.assertTrue(result["ok"])
        self.assertEqual(result["matches"][0]["file"], "util.py")
        self.assertEqual(result["matches"][0]["line"], 1)

    def test_search_skips_ignored_directories(self):
        kira_code.write_file("app/node_modules/pkg/index.js", "add();")
        result = kira_code.search_code("add", path="app")
        self.assertTrue(all("node_modules" not in match["file"] for match in result["matches"]))

    def test_write_then_delete_roundtrip(self):
        kira_code.write_file("tmp/scratch.txt", "hello")
        self.assertTrue((self.root / "tmp" / "scratch.txt").exists())
        self.assertTrue(kira_code.delete_path("tmp/scratch.txt")["ok"])
        self.assertFalse((self.root / "tmp" / "scratch.txt").exists())


class RunCommandTests(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("KIRA_CODE_DIR")
        self.root = Path(tempfile.mkdtemp(prefix="kira-code-test-"))
        os.environ["KIRA_CODE_DIR"] = str(self.root)

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("KIRA_CODE_DIR", None)
        else:
            os.environ["KIRA_CODE_DIR"] = self._previous

    def test_runs_a_workspace_script(self):
        kira_code.scaffold_project("runnable", template="python")
        result = kira_code.run_command("python runnable/main.py")
        self.assertTrue(result["ok"])
        self.assertIn("Hello from runnable!", result["output"])

    def test_whitelist_blocks_other_executables(self):
        for command in ("del /q x", "curl http://example.com", "powershell -c x"):
            self.assertEqual(kira_code.run_command(command)["error_code"], "command_not_allowed")

    def test_missing_target_is_a_structured_failure(self):
        result = kira_code.run_command("python missing/thing.py")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "not_found")


class RegistryAndRoutingTests(unittest.TestCase):
    def setUp(self):
        kira_agents.ensure_builtins()

    def test_programming_agent_and_consequential_tools_are_declared(self):
        snapshot = {agent["id"]: agent for agent in kira_agents.agents_snapshot()}
        self.assertIn("programming", snapshot)
        for tool in ("scaffold_project", "code_write_file", "code_read_file",
                     "code_list_dir", "code_search", "code_apply_edit",
                     "code_run_command", "code_delete_path"):
            self.assertIn(tool, snapshot["programming"]["tools"])
        for gated in ("scaffold_project", "code_write_file", "code_apply_edit",
                      "code_run_command", "code_delete_path"):
            self.assertIn(gated, snapshot["programming"]["consequential_tools"])
        for open_tool in ("code_read_file", "code_list_dir", "code_search"):
            self.assertNotIn(open_tool, snapshot["programming"]["consequential_tools"])

    def test_gated_tool_parks_until_approved(self):
        root = Path(tempfile.mkdtemp(prefix="kira-code-test-"))
        self.addCleanup(lambda: None)
        with patch.dict(os.environ, {"KIRA_CODE_DIR": str(root)}):
            result = kira_agents.run("code_write_file", {"path": "x.txt", "content": "hi"})
            self.assertEqual(result.error_code, "approval_required")
            approval_id = result.extra["approval_id"]
            resolved = kira_agents.resolve_approval(approval_id, approve=True)
            self.assertTrue(resolved.ok)
            self.assertTrue((root / "x.txt").exists())

    def test_scaffold_request_parses_en_and_fr(self):
        parsed = commands.parse_scaffold_request("create a python project todo-app")
        self.assertEqual(parsed, {"name": "todo-app", "template": "python"})
        self.assertEqual(commands.parse_scaffold_request("crée un projet web mon-site"),
                         {"name": "mon-site", "template": "web"})
        self.assertEqual(commands.parse_scaffold_request("new project ideas"), None)
        self.assertEqual(commands.parse_scaffold_request("create a project ideas"), None)

    def test_scaffold_route_asks_for_confirmation(self):
        commands.clear_pending_approval()
        self.addCleanup(commands.clear_pending_approval)
        root = Path(tempfile.mkdtemp(prefix="kira-code-test-"))
        parsed = commands.parse_scaffold_request("create a python project demo")
        with patch.dict(os.environ, {"KIRA_CODE_DIR": str(root)}):
            payload = commands._direct_tool_route("scaffold_project", parsed, {}, "en")
            self.assertTrue(payload["needs_approval"])
            approval_id = payload["approval_id"]
            resolved = kira_agents.resolve_approval(approval_id, approve=True)
        self.assertTrue(resolved.ok)
        self.assertTrue((root / "demo").is_dir())

    def test_planner_invented_name_is_refused_not_parked(self):
        # Live regression 2026-09-29: the tiny planner planned scaffold_project
        # with name="python". No approval card for a junk name.
        commands.clear_pending_approval()
        self.addCleanup(commands.clear_pending_approval)
        payload = commands._direct_tool_route("scaffold_project", {"name": "python"}, {}, "en")
        self.assertFalse(payload.get("needs_approval", False))
        self.assertEqual(payload["error_code"], "invalid_name")
        self.assertIsNone(commands.pending_approval())

    def test_scaffold_request_routes_before_the_planner(self):
        # With the planner OFF, the deterministic route still fires and parks
        # an approval for the RIGHT name.
        commands.clear_pending_approval()
        self.addCleanup(commands.clear_pending_approval)
        root = Path(tempfile.mkdtemp(prefix="kira-code-test-"))
        backend = SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=Mock(return_value=None),
            ask_chat=Mock(return_value="chat"),
            execute_action=Mock(return_value=True),
            build_reply=Mock(return_value="Done."),
            call_ollama=Mock(return_value={"message": {"content": "x"}}),
        )
        with patch.dict(os.environ, {"KIRA_CODE_DIR": str(root)}):
            result = commands.process_command(backend, "create a python project happy-path")
        self.assertEqual(result["action"], "scaffold_project")
        self.assertTrue(result["needs_approval"])
        self.assertIn("happy-path", result["response"])
        backend.ask_chat.assert_not_called()

    def test_registry_activity_records_the_programming_agent(self):
        root = Path(tempfile.mkdtemp(prefix="kira-code-test-"))
        with patch.dict(os.environ, {"KIRA_CODE_DIR": str(root)}):
            kira_agents.run("code_list_dir", {}, source="test")
        entry = kira_agents.recent_activity(1)[0]
        self.assertEqual(entry["agent"], "programming")
        self.assertEqual(entry["tool"], "code_list_dir")


if __name__ == "__main__":
    unittest.main()
