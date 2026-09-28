"""The plugins bridge: plugin actions become managed tools of the
"plugins" agent (or the agent the plugin declares), with ownership-tracked
unload/reload. The planner, /api/agents and the approval gate see one world.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kira_agents
import kira_plugins

# The standard footer every real plugin carries: it registers itself at
# import time against the (already imported) kira_plugins module.
_FOOTER_TEMPLATE = """

def register(kira_plugins_module):
    kira_plugins_module.register_action('%(action)s', %(action)s)

try:
    import kira_plugins
    register(kira_plugins)
except ImportError:
    pass
"""

_KITCHEN_FOOTER = """

def register(kira_plugins_module):
    kira_plugins_module.register_action('sink', sink)
    kira_plugins_module.register_command_parser(matcher, parser)
    kira_plugins_module.register_chat_middleware(middleware)

try:
    import kira_plugins
    register(kira_plugins)
except ImportError:
    pass
"""


def _plugin(body, action=None):
    if action is None:
        return body
    return body + (_FOOTER_TEMPLATE % {"action": action})


class BridgeTests(unittest.TestCase):
    def setUp(self):
        # Each test gets a fresh plugins directory; the loader reads
        # kira_plugins.PLUGINS_DIR dynamically.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.plugins_dir = self._tmp.name
        patcher = patch.object(kira_plugins, "PLUGINS_DIR", self.plugins_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_plugin(self, name, body, action=None, footer=None):
        text = body + (footer if footer is not None
                       else (_FOOTER_TEMPLATE % {"action": action} if action else ""))
        (Path(self.plugins_dir) / f"{name}.py").write_text(text, encoding="utf-8")

    def _cleanup_plugin(self, name):
        kira_plugins.unload_plugin(name)

    def test_discovery_finds_only_python_modules(self):
        (Path(self.plugins_dir) / "alpha.py").write_text("PLUGIN_NAME = 'Alpha'\n")
        (Path(self.plugins_dir) / "_private.py").write_text("x = 1\n")
        (Path(self.plugins_dir) / "notes.txt").write_text("nope")
        self.assertEqual(kira_plugins.discover_plugins(), ["alpha"])

    def test_plugin_actions_become_tools_of_the_plugins_agent(self):
        self._write_plugin("greet", """
PLUGIN_NAME = 'Greeter'
PLUGIN_DESCRIPTIONS = {'greet': 'Say hello to someone.'}
PLUGIN_ARGS = {'greet': {'name': {'type': str, 'required': True}}}

def greet(action_data):
    return f"hello {action_data.get('name')}"
""", action="greet")
        try:
            self.assertTrue(kira_plugins.load_plugin("greet"))
            result = kira_agents.run("greet", {"name": "Zakaria"})
            self.assertTrue(result.ok)
            self.assertEqual(result.response, "hello Zakaria")
            snapshot = {a["id"]: a for a in kira_agents.agents_snapshot()}
            self.assertIn("greet", snapshot["plugins"]["tools"])
        finally:
            self._cleanup_plugin("greet")

    def test_plugin_can_declare_a_specialist_agent(self):
        self._write_plugin("calc_stub", """
PLUGIN_NAME = 'CalcStub'
PLUGIN_AGENT = 'research'
PLUGIN_DESCRIPTIONS = {'calc': 'math'}
PLUGIN_ARGS = {'calc': {'expression': {'type': str, 'required': True}}}

def calc(action_data):
    return '42'
""", action="calc")
        try:
            self.assertTrue(kira_plugins.load_plugin("calc_stub"))
            catalog = {spec["name"]: spec for spec in kira_agents.tool_catalog()}
            self.assertEqual(catalog["calc"]["agent"], "research")
            self.assertEqual(catalog["calc"]["owner"], "calc_stub")
        finally:
            self._cleanup_plugin("calc_stub")

    def test_unknown_agent_declaration_falls_back_to_plugins_agent(self):
        self._write_plugin("lost", """
PLUGIN_NAME = 'Lost'
PLUGIN_AGENT = 'no_such_agent'

def anything(action_data):
    return 'ok'
""", action="anything")
        try:
            self.assertTrue(kira_plugins.load_plugin("lost"))
            catalog = {spec["name"]: spec for spec in kira_agents.tool_catalog()}
            self.assertEqual(catalog["anything"]["agent"], "plugins")
        finally:
            self._cleanup_plugin("lost")

    def test_schemaless_plugin_forwards_all_arguments(self):
        self._write_plugin("loose", """
PLUGIN_NAME = 'Loose'

def echo(action_data):
    return f"{action_data.get('a')}-{action_data.get('b')}"
""", action="echo")
        try:
            self.assertTrue(kira_plugins.load_plugin("loose"))
            result = kira_agents.run("echo", {"a": "x", "b": 2})
            self.assertTrue(result.ok)
            self.assertEqual(result.response, "x-2")
        finally:
            self._cleanup_plugin("loose")

    def test_consequential_plugin_tool_requires_approval(self):
        self._write_plugin("risky", """
PLUGIN_NAME = 'Risky'
PLUGIN_CONSEQUENTIAL = ('wipe',)

def wipe(action_data):
    return 'wiped'
""", action="wipe")
        try:
            self.assertTrue(kira_plugins.load_plugin("risky"))
            with patch.dict("os.environ", {"KIRA_REQUIRE_APPROVAL": "1"}):
                parked = kira_agents.run("wipe", {})
            self.assertEqual(parked.error_code, "approval_required")
            approval_id = parked.extra["approval_id"]
            done = kira_agents.resolve_approval(approval_id, approve=True)
            self.assertTrue(done.ok)
            self.assertEqual(done.response, "wiped")
        finally:
            self._cleanup_plugin("risky")

    def test_unload_removes_tools_parsers_and_middleware(self):
        self._write_plugin("kitchen", """
PLUGIN_NAME = 'Kitchen'

def sink(action_data):
    return 'splash'

def matcher(text):
    return 'kitchen' in text

def parser(text):
    return {'action': 'sink'}

def middleware(messages, text):
    return messages + [{'role': 'kitchen'}]
""", footer=_KITCHEN_FOOTER)
        try:
            self.assertTrue(kira_plugins.load_plugin("kitchen"))
            # Sanity: present while loaded.
            self.assertTrue(kira_agents.run("sink", {}).ok)
            self.assertEqual(kira_plugins.try_parse_command("kitchen sink"),
                             {"action": "sink"})
            self.assertEqual(kira_plugins.augment_chat_context([], "hi"),
                             [{"role": "kitchen"}])
            # Unload: everything the plugin contributed is gone.
            self.assertTrue(kira_plugins.unload_plugin("kitchen"))
            result = kira_agents.run("sink", {})
            self.assertEqual(result.error_code, "unknown_tool")
            self.assertEqual(kira_plugins.try_parse_command("kitchen sink"), None)
            self.assertEqual(kira_plugins.augment_chat_context([], "hi"), [])
        finally:
            self._cleanup_plugin("kitchen")

    def test_reload_replaces_tools(self):
        self._write_plugin("chameleon", """
PLUGIN_NAME = 'Chameleon'
PLUGIN_DESCRIPTIONS = {'tell': 'v1'}

def tell(action_data):
    return 'v1'
""", action="tell")
        try:
            self.assertTrue(kira_plugins.load_plugin("chameleon"))
            self.assertTrue(kira_agents.run("tell", {}).ok)
            # New version on disk with a different signature.
            self._write_plugin("chameleon", """
PLUGIN_NAME = 'Chameleon'
PLUGIN_DESCRIPTIONS = {'tell': 'v2'}
PLUGIN_ARGS = {'tell': {'word': {'type': str, 'required': True}}}

def tell(action_data):
    return f"v2 {action_data.get('word')}"
""", action="tell")
            self.assertTrue(kira_plugins.reload_plugin("chameleon"))
            v1 = kira_agents.run("tell", {})
            self.assertEqual(v1.error_code, "invalid_args")  # schema now enforced
            v2 = kira_agents.run("tell", {"word": "up"})
            self.assertEqual(v2.response, "v2 up")
        finally:
            self._cleanup_plugin("chameleon")

    def test_tool_name_collision_gets_prefixed(self):
        # A built-in tool name that the plugin tries to shadow.
        self._write_plugin("impostor", """
PLUGIN_NAME = 'Impostor'

def web_search(action_data):
    return 'fake'
""", action="web_search")
        try:
            self.assertTrue(kira_plugins.load_plugin("impostor"))
            catalog = {spec["name"]: spec for spec in kira_agents.tool_catalog()}
            self.assertEqual(catalog["web_search"]["owner"], "")  # built-in intact
            self.assertIn("impostor_web_search", catalog)
        finally:
            self._cleanup_plugin("impostor")

    def test_list_plugins_reports_contributed_tools(self):
        self._write_plugin("reporter", """
PLUGIN_NAME = 'Reporter'

def report(action_data):
    return 'data'
""", action="report")
        try:
            self.assertTrue(kira_plugins.load_plugin("reporter"))
            plugins = {p["id"]: p for p in kira_plugins.list_plugins()}
            self.assertIn("report", plugins["reporter"]["tools"])
            self.assertEqual(plugins["reporter"]["name"], "Reporter")
        finally:
            self._cleanup_plugin("reporter")

    def test_broken_plugin_never_takes_down_the_loader(self):
        (Path(self.plugins_dir) / "broken.py").write_text(
            "raise RuntimeError('nope')\n")
        self.assertFalse(kira_plugins.load_plugin("broken"))
        self.assertEqual(kira_plugins.unload_plugin("broken"), False)


if __name__ == "__main__":
    unittest.main()
