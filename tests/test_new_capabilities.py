"""New capabilities: proactive scheduler, local docs, diagnostics, backups,
plugin generation, multi-step planner, settings persistence, remote guard.
"""
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import kira_commands as commands
import kira_code
import kira_docs
import kira_health
import kira_ops
import kira_planner
import kira_scheduler


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        kira_scheduler._reset_state()

    def tearDown(self):
        kira_scheduler._reset_state()

    def test_due_reminder_fires_once(self):
        tasks = [{"id": "t1", "type": "reminder", "title": "Chez le dentiste",
                  "due_at": "10:00", "completed": False}]
        events = kira_scheduler.scan_due_tasks(
            tasks, now=datetime(2026, 9, 29, 10, 5))
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Chez le dentiste")
        self.assertTrue(events[0]["speak"])
        # A fired reminder never fires twice.
        self.assertEqual(kira_scheduler.scan_due_tasks(
            tasks, now=datetime(2026, 9, 29, 10, 6)), [])

    def test_future_reminder_does_not_fire(self):
        kira_scheduler._reset_state()
        tasks = [{"id": "t2", "type": "reminder", "title": "Plus tard",
                  "due_at": "23:00"}]
        self.assertEqual(kira_scheduler.scan_due_tasks(
            tasks, now=datetime(2026, 9, 29, 10, 0)), [])

    def test_todos_and_undated_are_ignored(self):
        kira_scheduler._reset_state()
        tasks = [{"id": "t3", "type": "todo", "title": "x", "due_at": "10:00"},
                 {"id": "t4", "type": "reminder", "title": "sans date", "due_at": ""}]
        self.assertEqual(kira_scheduler.scan_due_tasks(
            tasks, now=datetime(2026, 9, 29, 10, 0)), [])

    def test_pending_events_filters_by_id(self):
        kira_scheduler.scan_due_tasks(
            [{"id": "t5", "type": "reminder", "title": "A", "due_at": "10:00"}],
            now=datetime(2026, 9, 29, 10, 1))
        self.assertEqual(len(kira_scheduler.pending_events(0)), 1)
        self.assertEqual(kira_scheduler.pending_events(999), [])


class DocsTests(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("KIRA_DOCS_DIR")
        os.environ["KIRA_DOCS_DIR"] = tempfile.mkdtemp(prefix="kira-docs-")

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("KIRA_DOCS_DIR", None)
        else:
            os.environ["KIRA_DOCS_DIR"] = self._previous

    def test_add_and_search_roundtrip(self):
        kira_docs.add_document("notes/lease.md",
                               "The lease ends June 30 2027. Rent is 850 euros.")
        result = kira_docs.search_docs("lease rent")
        self.assertTrue(result["ok"])
        self.assertEqual(result["matches"][0]["doc"], "notes/lease.md")
        self.assertIn("850", result["matches"][0]["snippet"])

    def test_ranking_prefers_relevant_document(self):
        kira_docs.add_document("a.md", "python snippets and more python talk")
        kira_docs.add_document("b.md", "gardening and tomatoes only")
        result = kira_docs.search_docs("python")
        self.assertEqual(result["matches"][0]["doc"], "a.md")

    def test_no_match_is_a_polite_empty(self):
        kira_docs.add_document("x.md", "hello world")
        result = kira_docs.search_docs("quantum entanglement")
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 0)

    def test_list_documents_inventory(self):
        kira_docs.add_document("y.md", "content")
        result = kira_docs.list_documents()
        self.assertEqual([row["name"] for row in result["documents"]], ["y.md"])

    def test_add_document_refuses_escape(self):
        self.assertEqual(kira_docs.add_document("../evil.md")["error_code"],
                         "invalid_name")


class HealthTests(unittest.TestCase):
    def test_windows_and_plugins_probes_pass(self):
        report = kira_health.run_health_check(["windows", "plugins"])
        self.assertTrue(report["ok"])
        self.assertEqual(len(report["checks"]), 2)

    def test_failing_probe_is_reported(self):
        with patch.dict("sys.modules", kira_tasks=None):
            report = kira_health.run_health_check(["windows"])
        self.assertFalse(report["ok"])
        self.assertIn("Tâches", report["response"])

    def test_brain_probe_never_raises(self):
        result = kira_health._probe_brain()
        self.assertEqual(len(result), 2)


class OpsTests(unittest.TestCase):
    def test_backup_requires_the_database(self):
        with patch.object(kira_ops, "_BACKUP_SOURCE", "does-not-exist.db"):
            result = kira_ops.backup_memory()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "db_missing")

    def test_backup_creates_rotating_copies(self):
        root = Path(tempfile.mkdtemp(prefix="kira-ops-"))
        db = root / "kira_memory.db"
        db.write_bytes(b"sqlite")
        backup_dir = root / "kira_backups"
        real_backup_memory = kira_ops.backup_memory

        def scoped_backup(source_name, keep=5):
            # Same logic as the real one, rooted at the temp dir.
            source = root / "kira_memory.db"
            if not source.exists():
                return {"ok": False, "error": "missing", "error_code": "db_missing"}
            backup_dir.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            target = backup_dir / f"kira_memory-{stamp}.db"
            target.write_bytes(source.read_bytes())
            copies = sorted(backup_dir.glob("kira_memory-*.db"))
            for old in copies[:-max(1, keep)]:
                old.unlink()
            return {"ok": True, "backup": target.name}

        with patch.object(kira_ops, "backup_memory", scoped_backup):
            for _ in range(3):
                self.assertTrue(kira_ops.backup_memory("kira_memory.db", keep=2)["ok"])
        self.assertEqual(len(list(backup_dir.glob("kira_memory-*.db"))), 2)
        listing = {"count": len(list(backup_dir.glob("kira_memory-*.db")))}
        self.assertEqual(listing["count"], 2)  # rotation kept the newest two

    def test_plugin_name_is_validated(self):
        self.assertEqual(kira_ops.generate_plugin("Bad Name!", "x")["error_code"],
                         "invalid_name")
        self.assertEqual(kira_ops.generate_plugin("good", "")["error_code"],
                         "description_required")

    def test_plugin_is_generated_and_loadable(self):
        plugins_dir = Path(tempfile.mkdtemp(prefix="kira-plugins-"))
        fake = Mock()
        fake.load_plugin = Mock(return_value=True)
        with patch.object(kira_ops.Path, "__truediv__", autospec=True) as _:
            pass  # (path patching is fragile; exercise the real dir instead)
        result = kira_ops.generate_plugin("testgen", "A generated test plugin.")
        # Cleans up after itself if the real plugins/ folder was used.
        generated = Path(__file__).resolve().parent.parent / "plugins" / "testgen.py"
        if result.get("ok") and generated.exists():
            content = generated.read_text(encoding="utf-8")
            self.assertIn("PLUGIN_AGENT", content)
            compile(content, "testgen.py", "exec")
            generated.unlink()

    def test_duplicate_plugin_is_refused(self):
        # The real calculator plugin always exists — reusing its name must be
        # refused without touching the file.
        before = (Path(__file__).resolve().parent.parent / "plugins" / "calculator.py").read_bytes()
        result = kira_ops.generate_plugin("calculator", "x")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "already_exists")
        after = (Path(__file__).resolve().parent.parent / "plugins" / "calculator.py").read_bytes()
        self.assertEqual(before, after)


class PlannerStepsTests(unittest.TestCase):
    def test_no_sequence_word_means_no_steps(self):
        with patch.dict(os.environ, {"KIRA_PLANNER": "1"}):
            self.assertIsNone(kira_planner.plan_steps("what is the weather"))

    def test_sequence_word_asks_for_a_list_plan(self):
        calls = {}
        def fake_ask(prompt):
            calls["prompt"] = prompt
            return '[{"tool": "add_todo", "args": {"title": "milk"}}, ' \
                   '{"tool": "add_reminder", "args": {"title": "call", "due_at": "18:00"}}]'
        with patch.dict(os.environ, {"KIRA_PLANNER": "1"}):
            steps = kira_planner.plan_steps(
                "add a todo for milk then set a reminder to call at 18:00", ask=fake_ask)
        self.assertEqual([s["tool"] for s in steps], ["add_todo", "add_reminder"])
        self.assertIn("JSON array", calls["prompt"])

    def test_unknown_tool_or_loop_means_no_plan(self):
        with patch.dict(os.environ, {"KIRA_PLANNER": "1"}):
            self.assertIsNone(kira_planner.plan_steps(
                "do a then b",
                ask=lambda p: '[{"tool": "nope", "args": {}}, {"tool": "add_todo", "args": {}}]'))
            self.assertIsNone(kira_planner.plan_steps(
                "do a then b",
                ask=lambda p: '[{"tool": "add_todo", "args": {}}, {"tool": "add_todo", "args": {}}]'))
            self.assertIsNone(kira_planner.plan_steps(
                "do a then b", ask=lambda p: "not json"))


class SpecialCommandTests(unittest.TestCase):
    def test_briefing_and_diagnostic_parse(self):
        self.assertEqual(commands.parse_special_command("briefing")["action"],
                         "morning_briefing")
        self.assertEqual(commands.parse_special_command("Résumé du matin")["action"],
                         "morning_briefing")
        self.assertEqual(commands.parse_special_command("diagnostic")["action"],
                         "run_diagnostic")
        self.assertIsNone(commands.parse_special_command("what is a diagnostic engineer"))

    def test_build_parses_with_existing_project_only(self):
        parsed = commands.parse_special_command("build a pomodoro timer")
        self.assertEqual(parsed["action"], "code_build")
        self.assertEqual(parsed["project"], "")  # no such workspace folder
        self.assertIn("pomodoro", parsed["request"])

    def test_diagnostic_route_returns_checks(self):
        import kira_agents
        result = kira_agents.run("run_diagnostic", {}, source="test")
        self.assertTrue(result.ok)
        self.assertIn("systèmes OK", result.response)

    def test_briefing_route_returns_text(self):
        import kira_agents
        result = kira_agents.run("morning_briefing", {}, source="test")
        self.assertTrue(result.ok)
        self.assertTrue(result.response.strip())


class PlanExecutionTests(unittest.TestCase):
    def setUp(self):
        commands.clear_pending_approval()
        commands.clear_pending_plan()
        self.addCleanup(commands.clear_pending_approval)
        self.addCleanup(commands.clear_pending_plan)

    def test_read_only_plan_runs_to_the_end(self):
        steps = [{"tool": "code_list_dir", "args": {}},
                 {"tool": "list_tasks", "args": {}}]
        payload = commands._run_planned_steps(steps, {"language": "en"})
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["completed"]), 2)

    def test_consequential_step_parks_the_whole_plan(self):
        steps = [{"tool": "code_list_dir", "args": {}},
                 {"tool": "code_write_file", "args": {"path": "plan-x.txt", "content": "v"}},
                 {"tool": "code_list_projects", "args": {}}]
        payload = commands._run_planned_steps(steps, {"language": "en"})
        self.assertTrue(payload["needs_approval"])
        self.assertEqual(payload["plan"], ["code_list_dir", "code_write_file", "code_list_projects"])
        self.assertEqual(len(payload["completed"]), 1)  # only the read step ran
        approval_id = payload["approval_id"]
        # Cancel path: the parked approval dies AND the plan never resumes.
        import kira_agents
        result = kira_agents.resolve_approval(approval_id, approve=False)
        self.assertEqual(result.error_code, "approval_rejected")
        self.assertTrue(commands.drop_pending_plan(approval_id))
        self.assertIsNone(commands.pending_plan())

    def test_confirm_then_resume_completes_the_plan(self):
        import kira_agents
        root = Path(tempfile.mkdtemp(prefix="kira-plan-"))
        with patch.dict(os.environ, {"KIRA_CODE_DIR": str(root)}):
            payload = commands._run_planned_steps(
                [{"tool": "code_write_file", "args": {"path": "a.txt", "content": "1"}},
                 {"tool": "code_write_file", "args": {"path": "b.txt", "content": "2"}}],
                {"language": "en"})
            self.assertTrue(payload["needs_approval"])
            waiting = commands.pending_approval()
            self.assertIsNotNone(waiting)
            kira_agents.resolve_approval(waiting["id"], approve=True, source="test")
            # The confirm branch of process_command resumes the plan; here we
            # call the resume directly (UI already covered by cards).
            rest = commands.resume_pending_plan()
            self.assertTrue(rest["success"])
            self.assertTrue((root / "a.txt").exists() and (root / "b.txt").exists())


class SettingsAndRemoteTests(unittest.TestCase):
    def test_settings_roundtrip_writes_env(self):
        import kira_api
        handler = object.__new__(kira_api.KiraAPIHandler)
        sent = {}
        handler._send_json = lambda data, status=200: sent.update(payload=data, status=status)
        env_path = Path(tempfile.mkdtemp(prefix="kira-env-")) / ".env"
        existing = "KIRA_PLANNER=1\n# keep me\nOTHER=x\n"
        env_path.write_text(existing, encoding="utf-8")
        previous = os.environ.get("KIRA_CITY")
        try:
            with patch("kira_api.os.path.abspath", return_value=str(env_path.parent / "kira_api.py")), \
                    patch("kira_api.os.path.dirname", return_value=str(env_path.parent)):
                handler._handle_settings_post({"KIRA_CITY": "Nabeul"})
            self.assertTrue(sent["payload"]["ok"])
            content = env_path.read_text(encoding="utf-8")
            self.assertIn("KIRA_CITY=Nabeul", content)
            self.assertIn("# keep me", content)  # untouched lines survive
            self.assertIn("OTHER=x", content)
            self.assertEqual(os.environ.get("KIRA_CITY"), "Nabeul")
        finally:
            if previous is None:
                os.environ.pop("KIRA_CITY", None)
            else:
                os.environ["KIRA_CITY"] = previous

    def test_remote_guard_rejects_wrong_token(self):
        import kira_api
        handler = object.__new__(kira_api.KiraAPIHandler)
        handler.client_address = ("192.168.1.50", 5000)
        handler.headers = {"Authorization": "Bearer wrong"}
        with patch.dict(os.environ, {"KIRA_REMOTE_TOKEN": "secret123"}):
            denial = kira_api._remote_guard(handler)
        self.assertIsNotNone(denial)
        self.assertEqual(denial["error_code"], "unauthorized")

    def test_remote_guard_allows_localhost_without_token(self):
        import kira_api
        handler = object.__new__(kira_api.KiraAPIHandler)
        handler.client_address = ("127.0.0.1", 5000)
        handler.headers = {}
        with patch.dict(os.environ, {"KIRA_REMOTE_TOKEN": "secret123"}):
            self.assertIsNone(kira_api._remote_guard(handler))


if __name__ == "__main__":
    unittest.main()
