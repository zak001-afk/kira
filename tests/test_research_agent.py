"""Research agent v2: web learning/search run through the registry, so the
specialist displays show real activity and failures stay structured."""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kira_agents
import kira_commands


class RegistryTests(unittest.TestCase):
    def test_web_tools_belong_to_the_research_agent(self):
        kira_agents.ensure_builtins()
        snapshot = {agent["id"]: agent for agent in kira_agents.agents_snapshot()}
        self.assertIn("web_learn", snapshot["research"]["tools"])
        self.assertIn("web_search", snapshot["research"]["tools"])

    def test_web_tools_are_not_consequential(self):
        # 'learn about X' stays instant; the shared-memory privacy gates
        # already filter what may be published.
        kira_agents.ensure_builtins()
        for name in ("web_learn", "web_search"):
            self.assertFalse(kira_agents._REGISTRY[name].consequential, name)


class WebLearnRouteTests(unittest.TestCase):
    def fake_web(self, learn=None, search=None):
        return types.SimpleNamespace(
            search_and_learn=learn or Mock(return_value="I learned about python."),
            search_web=search or Mock(return_value=[{"title": "t", "url": "u"}]),
        )

    def test_learn_about_runs_through_the_registry_and_records_activity(self):
        learn = Mock(return_value="I learned about python.")
        with patch.dict(sys.modules, kira_web=self.fake_web(learn=learn)):
            reply = kira_commands.try_web_learning("learn about python")
        self.assertEqual(reply, "I learned about python.")
        learn.assert_called_once_with("python")
        activity = kira_agents.recent_activity(limit=5)
        self.assertEqual(activity[-1]["agent"], "research")
        self.assertEqual(activity[-1]["tool"], "web_learn")
        self.assertTrue(activity[-1]["ok"])

    def test_failures_are_structured_never_raised(self):
        learn = Mock(side_effect=RuntimeError("no network"))
        with patch.dict(sys.modules, kira_web=self.fake_web(learn=learn)):
            reply = kira_commands.try_web_learning("learn about python")
        self.assertIn("no network", reply)
        activity = kira_agents.recent_activity(limit=1)
        self.assertFalse(activity[-1]["ok"])
        self.assertEqual(activity[-1]["error_code"], "tool_failed")

    def test_unrelated_and_private_commands_are_untouched(self):
        with patch.dict(sys.modules, kira_web=self.fake_web()):
            self.assertIsNone(kira_commands.try_web_learning("remember my birthday"))
            self.assertIsNone(kira_commands.try_web_learning("tell me a joke"))

    def test_web_search_clamps_the_result_count(self):
        search = Mock(return_value=[])
        with patch.dict(sys.modules, kira_web=self.fake_web(search=search)):
            result = kira_agents.run("web_search", {"query": "python", "num_results": 50})
        self.assertTrue(result.ok)
        search.assert_called_once_with("python", num_results=10)

    def test_web_search_returns_structured_data(self):
        rows = [{"title": "Python", "url": "https://python.org"}]
        with patch.dict(sys.modules, kira_web=self.fake_web(search=Mock(return_value=rows))):
            result = kira_agents.run("web_search", {"query": "python"})
        self.assertTrue(result.ok)
        self.assertEqual(result.data, rows)


if __name__ == "__main__":
    unittest.main()
