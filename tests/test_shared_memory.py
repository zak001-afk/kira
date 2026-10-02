"""Tests for the Supabase shared knowledge boundary.

These tests never touch the network: a fake ``supabase`` module is injected
before loading ``kira_shared_memory``.

They cover the two hard requirements:
  * only non-personal web research / project knowledge may be shared;
  * the service_role key is never used.
"""

import base64
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src/kira/data/kira_shared_memory.py"


def make_key(role):
    """Build an unsigned JWT-shaped Supabase key with the given role claim."""
    def encode(data):
        raw = json.dumps(data).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'HS256', 'typ': 'JWT'})}.{encode({'role': role})}.sig"


ANON_KEY = make_key("anon")
SERVICE_KEY = make_key("service_role")


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.calls = []
        self.payload = None
        self.on_conflict = None
        self.filters = []

    def select(self, columns="*"):
        self.calls.append(("select", columns))
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def or_(self, expression):
        self.calls.append(("or", expression))
        self.filters.append(expression)
        return self

    def order(self, column, desc=False):
        self.calls.append(("order", column, desc))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def upsert(self, payload, on_conflict=None):
        self.calls.append(("upsert", payload, on_conflict))
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def execute(self):
        if self.client.raise_on_query:
            raise RuntimeError("network unavailable")
        return FakeResponse(self.client.rows)


class FakeRpcCall:
    def __init__(self, client, name, params):
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        if self.client.rpc_error:
            raise RuntimeError(self.client.rpc_error)
        return FakeResponse(self.client.rpc_rows)


class FakeClient:
    def __init__(self):
        self.upserts = []
        self.tables = []
        self.rpc_calls = []
        self.rows = []
        self.rpc_rows = []
        self.rpc_error = ""
        self.raise_on_query = False

    def table(self, name):
        query = FakeQuery(self, name)
        self.tables.append(query)
        return query

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return FakeRpcCall(self, name, params)


def load_module(env=None, client=None, create_client=None, dotenv=True, supabase=True):
    """
    Load a fresh copy of kira_shared_memory with a controlled environment.

    Returns (module, fake_client).
    """
    env = dict(env or {})
    fake_client = client if client is not None else FakeClient()

    if create_client is None:
        create_client = lambda url, key: fake_client  # noqa: E731

    saved = {
        name: sys.modules.get(name)
        for name in ("supabase", "dotenv")
    }

    if supabase:
        sys.modules["supabase"] = types.SimpleNamespace(
            create_client=create_client
        )
    else:
        # None in sys.modules makes the import fail, even if it is installed.
        sys.modules["supabase"] = None

    if dotenv:
        sys.modules["dotenv"] = types.SimpleNamespace(load_dotenv=lambda *a, **k: None)
    else:
        sys.modules["dotenv"] = None

    name = f"kira_shared_memory_under_test_{id(fake_client)}"

    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)

    try:
        with mock.patch.dict(os.environ, env, clear=False):
            for key in list(os.environ):
                if key.startswith(("SUPABASE", "KIRA_SHARED")) and key not in env:
                    del os.environ[key]
            spec.loader.exec_module(module)
    finally:
        for module_name, previous in saved.items():
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous

    return module, fake_client


@contextlib.contextmanager
def loaded(env=None, client=None, **kwargs):
    module, fake_client = load_module(env=env, client=client, **kwargs)
    yield module, fake_client


class ConfigurationTests(unittest.TestCase):
    def test_disabled_without_configuration(self):
        with loaded() as (shared, client):
            self.assertFalse(shared.is_configured())
            self.assertFalse(shared.is_enabled())
            self.assertFalse(
                shared.save_shared_knowledge("web_research", "python", "Decorators.")
            )
            self.assertEqual(shared.search_shared_knowledge("python"), [])
            self.assertEqual(client.tables, [])

    def test_enabled_with_url_and_anon_key(self):
        with loaded(
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": ANON_KEY}
        ) as (shared, _client):
            self.assertTrue(shared.is_enabled())
            self.assertTrue(shared.status()["enabled"])

    def test_kill_switch_disables_sharing(self):
        with loaded(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_ANON_KEY": ANON_KEY,
                "KIRA_SHARED_KNOWLEDGE": "off",
            }
        ) as (shared, client):
            self.assertFalse(shared.is_enabled())
            self.assertFalse(
                shared.save_shared_knowledge("web_research", "python", "Decorators.")
            )
            self.assertEqual(client.tables, [])

    def test_missing_supabase_package_degrades_gracefully(self):
        with loaded(
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": ANON_KEY},
            supabase=False,
        ) as (shared, _client):
            self.assertFalse(shared.is_enabled())
            self.assertEqual(shared.save_web_research("python", "Decorators."), False)


class ServiceRoleKeyTests(unittest.TestCase):
    def test_service_role_env_var_is_ignored_and_client_uses_anon_key(self):
        created = []
        client = FakeClient()

        def factory(url, key):
            created.append(key)
            return client

        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": ANON_KEY,
            "SUPABASE_SERVICE_ROLE_KEY": SERVICE_KEY,
        }

        with loaded(env, create_client=factory) as (shared, _client):
            self.assertTrue(shared.is_enabled())
            self.assertEqual(
                shared.SERVICE_ROLE_ENV_VARS, ["SUPABASE_SERVICE_ROLE_KEY"]
            )
            self.assertTrue(
                shared.save_shared_knowledge("project_knowledge", "deploy", "Use systemd.")
            )

        # Only the public anon key is ever handed to the client.
        self.assertEqual(created, [ANON_KEY])

    def test_service_role_key_in_anon_slot_is_refused(self):
        calls = []
        client = FakeClient()

        def factory(url, key):
            calls.append((url, key))
            return client

        with loaded(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_ANON_KEY": SERVICE_KEY,
            },
            client=client,
        ) as (shared, _client):
            self.assertFalse(shared.is_enabled())
            self.assertTrue(shared.key_looks_like_service_role(SERVICE_KEY))
            self.assertFalse(
                shared.save_shared_knowledge("web_research", "python", "Decorators.")
            )
            self.assertEqual(shared.search_shared_knowledge("python"), [])
            self.assertEqual(calls, [])

    def test_secret_prefix_key_is_refused(self):
        with loaded(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_ANON_KEY": "sb_secret_abcdefghijklmnop",
            }
        ) as (shared, _client):
            self.assertFalse(shared.is_enabled())
            self.assertIn("service_role", shared.status()["reason"])


class PrivacyBoundaryTests(unittest.TestCase):
    ENV = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": ANON_KEY}

    def test_personal_statements_never_reach_supabase(self):
        payloads = [
            "My name is Zakaria and I live in Paris.",
            "my favorite programming language is Python",
            "I prefer dark mode in every app",
            "Remember that my office is on the second floor",
            "My password is hunter2, do not share it",
            "Contact me at zakaria@example.com",
            "Task: call my manager at 06 12 34 56 78",
        ]

        with loaded(dict(self.ENV)) as (shared, client):
            for payload in payloads:
                self.assertFalse(
                    shared.save_shared_knowledge("web_research", "note", payload),
                    payload,
                )
                self.assertFalse(
                    shared.save_project_knowledge("project", payload),
                    payload,
                )
            self.assertEqual(client.tables, [])

    def test_registered_private_terms_block_publishing(self):
        with loaded(dict(self.ENV)) as (shared, client):
            registered = shared.set_private_terms(["Zakaria", "ab"])
            self.assertEqual(registered, 1)
            self.assertEqual(shared.get_private_terms(), ["zakaria"])

            self.assertFalse(
                shared.save_project_knowledge(
                    "release_process",
                    "Zakaria deploys the web UI on Fridays.",
                )
            )
            self.assertEqual(client.tables, [])

    def test_public_web_research_is_shared(self):
        with loaded(dict(self.ENV)) as (shared, client):
            saved = shared.save_web_research(
                "python decorators",
                "Decorators wrap a callable and return a new callable.",
                source_url="https://docs.python.org/3/",
                tags=["python", "docs"],
            )

            self.assertTrue(saved)
            self.assertEqual(len(client.tables), 1)

            query = client.tables[0]
            self.assertEqual(query.table_name, "shared_knowledge")
            self.assertEqual(query.on_conflict, "kind,topic")
            self.assertEqual(query.payload["kind"], "web_research")
            self.assertEqual(query.payload["topic"], "python_decorators")

    def test_project_knowledge_is_shared_with_expected_kind(self):
        with loaded(dict(self.ENV)) as (shared, client):
            self.assertTrue(
                shared.save_project_knowledge(
                    "ui architecture",
                    "The desktop HUD lives in kira_theme.py and ui/app.js.",
                )
            )
            payload = client.tables[0].payload
            self.assertEqual(payload["kind"], "project_knowledge")
            self.assertEqual(payload["topic"], "ui architecture")

    def test_unknown_kind_is_refused(self):
        with loaded(dict(self.ENV)) as (shared, client):
            self.assertFalse(
                shared.save_shared_knowledge("personal_note", "diary", "Private text.")
            )
            self.assertFalse(
                shared.save_shared_knowledge("conversation", "chat", "Hello there.")
            )
            self.assertFalse(
                shared.save_shared_knowledge("fact", "note", "A general statement.")
            )
            self.assertEqual(client.tables, [])

    def test_web_page_helper_trims_url_topic(self):
        with loaded(dict(self.ENV)) as (shared, client):
            self.assertTrue(
                shared.save_web_page(
                    "https://example.com/docs/page.html?x=1",
                    "Example docs",
                    "Some public documentation.",
                )
            )
            payload = client.tables[0].payload
            self.assertEqual(payload["kind"], "web_page")
            self.assertNotIn("https://", payload["topic"])
            self.assertEqual(payload["source_url"], "https://example.com/docs/page.html?x=1")


class SearchTests(unittest.TestCase):
    ENV = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": ANON_KEY}

    def test_search_uses_rpc_and_normalizes_rows(self):
        client = FakeClient()
        client.rpc_rows = [
            {
                "kind": "web_research",
                "topic": "python_decorators",
                "title": "Python decorators",
                "content": "Decorators wrap a callable.",
                "source_url": "https://docs.python.org/3/",
                "tags": ["python"],
                "updated_at": "2026-09-25T10:00:00+00:00",
            }
        ]

        with loaded(dict(self.ENV), client=client) as (shared, _client):
            results = shared.search_shared_knowledge("python decorators", limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["topic"], "python_decorators")
        self.assertEqual(results[0]["tags"], ["python"])
        self.assertEqual(client.rpc_calls[0][0], "search_shared_knowledge")
        self.assertEqual(client.rpc_calls[0][1]["p_limit"], 3)

    def test_search_falls_back_to_filters_when_rpc_is_missing(self):
        client = FakeClient()
        client.rpc_error = "function does not exist (PGRST202)"
        client.rows = [
            {
                "kind": "project_knowledge",
                "topic": "release_process",
                "title": "Release process",
                "content": "Tag the repo then rebuild the installer.",
                "source_url": "",
                "tags": [],
                "updated_at": "2026-09-24T10:00:00+00:00",
            }
        ]

        with loaded(dict(self.ENV), client=client) as (shared, _client):
            results = shared.search_shared_knowledge("release process", limit=2)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["kind"], "project_knowledge")

        table = client.tables[0]
        filters = [call for call in table.calls if call[0] == "or"]
        self.assertEqual(len(filters), 2)
        self.assertIn("topic.ilike.%release%", filters[0][1])

    def test_search_never_raises_on_errors(self):
        client = FakeClient()
        client.rpc_error = "boom"

        with loaded(dict(self.ENV), client=client) as (shared, client_ref):
            client_ref.raise_on_query = True
            self.assertEqual(shared.search_shared_knowledge("anything"), [])
            self.assertIsNone(shared.get_shared_knowledge("web_research", "missing"))

    def test_build_shared_context_labels_non_personal_knowledge(self):
        client = FakeClient()
        client.rpc_rows = [
            {
                "kind": "web_research",
                "topic": "python_decorators",
                "title": "Python decorators",
                "content": "Decorators wrap a callable.",
                "source_url": "",
                "tags": [],
                "updated_at": "",
            }
        ]

        with loaded(dict(self.ENV), client=client) as (shared, _client):
            context = shared.build_shared_context("python decorators")

        self.assertIn("SHARED KNOWLEDGE", context)
        self.assertIn("NOT the user's personal memories", context)
        self.assertIn("Decorators wrap a callable.", context)

    def test_build_shared_context_is_empty_when_disabled(self):
        with loaded() as (shared, _client):
            self.assertEqual(shared.build_shared_context("python decorators"), "")


class RepositoryFileTests(unittest.TestCase):
    def test_env_example_contains_required_keys_and_warning(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("SUPABASE_URL=", text)
        self.assertIn("SUPABASE_ANON_KEY=", text)
        self.assertIn("SERVICE_ROLE", text)
        self.assertIn("DO NOT add SUPABASE_SERVICE_ROLE_KEY", text)

    def test_schema_enables_rls_and_has_no_service_role_policy(self):
        text = (ROOT / "SUPABASE_SCHEMA.sql").read_text(encoding="utf-8").lower()
        self.assertIn("enable row level security", text)
        self.assertIn("to anon, authenticated", text)
        self.assertIn("privacy_guard", text)
        self.assertIn("shared_knowledge", text)
        # KIRA upserts with the anon key, so insert + update policies must
        # exist for it; deletion stays behind authentication.
        self.assertIn('"shared_knowledge_public_insert"', text)
        self.assertIn('"shared_knowledge_public_update"', text)
        self.assertIn('"shared_knowledge_auth_delete"', text)
        # Policies must never be granted to service_role and the schema must
        # not instruct anyone to use that key.
        self.assertNotIn("to service_role", text)
        self.assertIn("never use the service_role key", text)

    def test_requirements_pin_new_dependencies(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertIn("supabase>=2.0.0", text)
        self.assertIn("python-dotenv>=1.0.0", text)


if __name__ == "__main__":
    unittest.main()
