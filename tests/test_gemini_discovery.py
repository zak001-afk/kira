"""Gemini model names rot; KIRA must recover without a code change.

Regression source: live test 2026-09-27 22:36 — 'gemini-2.5-flash' returned
HTTP 404 'no longer available to new users' and cloud chat silently died."""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import kira_ai


def fake_response(status_code=200, payload=None, text=""):
    return SimpleNamespace(status_code=status_code,
                           json=lambda: payload or {},
                           text=text or str(payload or {}))


MODELS_PAYLOAD = {"models": [
    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/gemini-3.8-flash-lite", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
]}

GOOD_CHAT = {"candidates": [{"content": {"parts": [{"text": "pong"}]}}]}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        kira_ai._GEMINI_RESOLVED["model"] = ""

    def tearDown(self):
        kira_ai._GEMINI_RESOLVED["model"] = ""

    def test_prefers_the_latest_alias_when_available(self):
        payload = {"models": MODELS_PAYLOAD["models"] + [
            {"name": "models/gemini-flash-latest", "supportedGenerationMethods": ["generateContent"]}]}
        with patch.object(kira_ai.requests, "get", return_value=fake_response(200, payload)):
            self.assertEqual(kira_ai._discover_gemini_model("k"), "gemini-flash-latest")

    def test_picks_the_highest_versioned_flash(self):
        with patch.object(kira_ai.requests, "get", return_value=fake_response(200, MODELS_PAYLOAD)):
            self.assertEqual(kira_ai._discover_gemini_model("k"), "gemini-3.8-flash")

    def test_returns_empty_on_api_failure(self):
        with patch.object(kira_ai.requests, "get", return_value=fake_response(500, {})):
            self.assertEqual(kira_ai._discover_gemini_model("k"), "")
        with patch.object(kira_ai.requests, "get", side_effect=OSError("no network")):
            self.assertEqual(kira_ai._discover_gemini_model("k"), "")


class Retry404Tests(unittest.TestCase):
    def setUp(self):
        kira_ai._GEMINI_RESOLVED["model"] = ""

    def tearDown(self):
        kira_ai._GEMINI_RESOLVED["model"] = ""

    def env(self):
        return patch.dict(os.environ, {"KIRA_CLOUD_AI": "1", "GEMINI_API_KEY": "test-key",
                                       "KIRA_GEMINI_MODEL": "gemini-2.5-flash"})

    def test_404_triggers_discovery_and_one_retry(self):
        post = Mock(side_effect=[
            fake_response(404, text='{"error": {"code": 404, "message": "no longer available"}}'),
            fake_response(200, GOOD_CHAT),
        ])
        get = Mock(return_value=fake_response(200, MODELS_PAYLOAD))
        with self.env(), patch.object(kira_ai.requests, "post", post), \
                patch.object(kira_ai.requests, "get", get):
            reply = kira_ai.chat("ping", provider="gemini")
        self.assertTrue(reply.ok)
        self.assertEqual(reply.text, "pong")
        self.assertEqual(reply.model, "gemini-3.8-flash")
        self.assertIn("gemini-3.8-flash", post.call_args_list[1].args[0])
        self.assertEqual(kira_ai.active_gemini_model(), "gemini-3.8-flash")

    def test_the_discovered_model_is_remembered_for_later_calls(self):
        kira_ai._GEMINI_RESOLVED["model"] = "gemini-3.8-flash"
        post = Mock(return_value=fake_response(200, GOOD_CHAT))
        with self.env(), patch.object(kira_ai.requests, "post", post):
            reply = kira_ai.chat("ping", provider="gemini")
        self.assertTrue(reply.ok)
        self.assertIn("gemini-3.8-flash", post.call_args_list[0].args[0])

    def test_failed_discovery_returns_the_original_404(self):
        post = Mock(return_value=fake_response(
            404, text='{"error": {"code": 404, "message": "gone"}}'))
        get = Mock(return_value=fake_response(500, {}))
        with self.env(), patch.object(kira_ai.requests, "post", post), \
                patch.object(kira_ai.requests, "get", get):
            reply = kira_ai.chat("ping", provider="gemini")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "provider_error")
        self.assertIn("404", reply.error)

    def test_non_404_errors_never_trigger_discovery(self):
        post = Mock(return_value=fake_response(429, text='{"error": {"code": 429}}'))
        get = Mock()
        with self.env(), patch.object(kira_ai.requests, "post", post), \
                patch.object(kira_ai.requests, "get", get):
            reply = kira_ai.chat("ping", provider="gemini")
        self.assertFalse(reply.ok)
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
