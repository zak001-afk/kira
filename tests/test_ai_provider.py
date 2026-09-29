"""kira_ai: local by default, cloud strictly opt-in, keys never leak.

All tests are offline: requests.post is mocked; refusal paths must not touch
the network at all.
"""
import os
import unittest
from unittest.mock import Mock, patch

import requests as real_requests

import kira_ai


FAKE_KEY = "AIzaFAKEFAKEFAKEFAKE"


def clean_env(**extra):
    scrubbed = {name: "" for name in
                ("KIRA_CLOUD_AI", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                 "KIRA_GEMINI_MODEL", "KIRA_OLLAMA_URL", "KIRA_OLLAMA_MODEL")}
    scrubbed.update(extra)
    return patch.dict(os.environ, scrubbed)


def gemini_ok(text="Bonjour de Gemini."):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}]}
    return response


def ollama_ok(text="Bonjour d'Ollama."):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {"message": {"content": text}}
    return response


class OllamaThinkTests(unittest.TestCase):
    """Thinking models (qwen3, …) must not silently eat short deadlines:
    reasoning off by default, token cap always applied, think blocks stripped."""

    def test_think_off_and_default_cap_by_default(self):
        with patch.object(kira_ai.requests, "post", return_value=ollama_ok()) as post, \
                clean_env():
            kira_ai.chat("hello", provider="ollama")
        body = post.call_args.kwargs["json"]
        self.assertFalse(body["think"])
        self.assertEqual(body["options"]["num_predict"], 512)

    def test_caller_can_opt_into_reasoning(self):
        with patch.object(kira_ai.requests, "post", return_value=ollama_ok()) as post, \
                clean_env():
            kira_ai.chat("hello", provider="ollama", think=True)
        body = post.call_args.kwargs["json"]
        self.assertTrue(body["think"])

    def test_caller_num_predict_wins_over_default_cap(self):
        with patch.object(kira_ai.requests, "post", return_value=ollama_ok()) as post, \
                clean_env():
            kira_ai.chat("hello", provider="ollama", options={"num_predict": 96})
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["options"]["num_predict"], 96)

    def test_inline_think_blocks_are_stripped(self):
        with patch.object(kira_ai.requests, "post",
                          return_value=ollama_ok("<think>pondering</think>Answer.")), \
                clean_env():
            reply = kira_ai.chat("hello", provider="ollama")
        self.assertTrue(reply.ok)
        self.assertEqual(reply.text, "Answer.")

    def test_planner_asks_for_fast_no_think_json(self):
        import kira_planner
        captured = {}

        def fake_chat(prompt, **kwargs):
            captured.update(kwargs)
            return kira_ai.AIReply(ok=True, text='{"tool": "none"}')

        with patch.dict(os.environ, {"KIRA_PLANNER": "1"}), \
                patch.object(kira_planner, "planner_route", return_value=("ollama", "")), \
                patch("kira_ai.chat", side_effect=fake_chat):
            plan = kira_planner.plan_command("look for python info")
        self.assertIsNone(plan)  # 'none' -> no plan, chat fallback
        self.assertFalse(captured.get("think", True))
        self.assertLessEqual(captured.get("options", {}).get("num_predict", 10**9), 96)





class CloudGateTests(unittest.TestCase):
    def test_cloud_disabled_refuses_before_any_network(self):
        post = Mock()
        with clean_env(GEMINI_API_KEY=FAKE_KEY), patch.object(kira_ai.requests, "post", post):
            reply = kira_ai.chat("hello", provider="gemini")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "cloud_disabled")
        post.assert_not_called()

    def test_missing_key_refuses_before_any_network(self):
        post = Mock()
        with clean_env(KIRA_CLOUD_AI="1"), patch.object(kira_ai.requests, "post", post):
            reply = kira_ai.chat("hello", provider="gemini")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "missing_api_key")
        post.assert_not_called()

    def test_local_provider_is_the_default(self):
        with clean_env(), patch.object(kira_ai.requests, "post", Mock(return_value=ollama_ok())) as post:
            reply = kira_ai.chat("hello")
        self.assertTrue(reply.ok)
        self.assertEqual(reply.provider, "ollama")
        self.assertIn("11434", post.call_args.args[0])

    def test_unknown_provider_is_refused(self):
        with clean_env():
            reply = kira_ai.chat("hello", provider="skynet")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "unknown_provider")


class GeminiTests(unittest.TestCase):
    def run_gemini(self, response=None, messages="hello", **env):
        post = Mock(return_value=response or gemini_ok())
        with clean_env(KIRA_CLOUD_AI="1", GEMINI_API_KEY=FAKE_KEY, **env), \
                patch.object(kira_ai.requests, "post", post):
            reply = kira_ai.chat(messages, provider="gemini")
        return post, reply

    def test_success_returns_text_and_timing(self):
        post, reply = self.run_gemini()
        self.assertTrue(reply.ok)
        self.assertEqual(reply.text, "Bonjour de Gemini.")
        self.assertEqual(reply.provider, "gemini")
        self.assertGreaterEqual(reply.elapsed_ms, 0)

    def test_key_travels_in_header_never_in_url(self):
        post, _ = self.run_gemini()
        url = post.call_args.args[0]
        headers = post.call_args.kwargs["headers"]
        self.assertNotIn(FAKE_KEY, url)
        self.assertEqual(headers["x-goog-api-key"], FAKE_KEY)
        self.assertIn("gemini-2.5-flash", url)

    def test_model_override(self):
        post, _ = self.run_gemini(KIRA_GEMINI_MODEL="gemini-2.5-pro")
        self.assertIn("gemini-2.5-pro", post.call_args.args[0])

    def test_system_messages_become_system_instruction(self):
        post, _ = self.run_gemini(messages=[
            {"role": "system", "content": "You are KIRA."},
            {"role": "user", "content": "Salut"},
            {"role": "assistant", "content": "Bonjour"},
            {"role": "user", "content": "Ça va ?"},
        ])
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "You are KIRA.")
        roles = [c["role"] for c in body["contents"]]
        self.assertEqual(roles, ["user", "model", "user"])

    def test_http_error_is_structured_and_scrubbed(self):
        response = Mock()
        response.status_code = 400
        response.text = f"bad request key={FAKE_KEY}"
        post, reply = self.run_gemini(response=response)
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "provider_error")
        self.assertNotIn(FAKE_KEY, reply.error)  # The key never leaks into errors.

    def test_blocked_or_empty_reply_is_honest(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"candidates": []}
        _, reply = self.run_gemini(response=response)
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "empty_reply")

    def test_timeout_is_structured(self):
        post = Mock(side_effect=real_requests.Timeout())
        with clean_env(KIRA_CLOUD_AI="1", GEMINI_API_KEY=FAKE_KEY), \
                patch.object(kira_ai.requests, "post", post):
            reply = kira_ai.chat("hello", provider="gemini", timeout=5)
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "timeout")


class OllamaTests(unittest.TestCase):
    def test_success_and_payload_shape(self):
        post = Mock(return_value=ollama_ok("Réponse locale."))
        with clean_env(KIRA_OLLAMA_MODEL="qwen3:0.6b"), patch.object(kira_ai.requests, "post", post):
            reply = kira_ai.chat([{"role": "user", "content": "salut"}])
        self.assertTrue(reply.ok)
        self.assertEqual(reply.text, "Réponse locale.")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "qwen3:0.6b")
        self.assertFalse(body["stream"])

    def test_unreachable_ollama_is_structured(self):
        post = Mock(side_effect=real_requests.ConnectionError("refused"))
        with clean_env(), patch.object(kira_ai.requests, "post", post):
            reply = kira_ai.chat("salut")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "provider_unreachable")

    def test_empty_prompt_refused_without_network(self):
        post = Mock()
        with clean_env(), patch.object(kira_ai.requests, "post", post):
            reply = kira_ai.chat("   ")
        self.assertFalse(reply.ok)
        self.assertEqual(reply.error_code, "empty_prompt")
        post.assert_not_called()


class AvailabilityTests(unittest.TestCase):
    def test_reports_booleans_never_the_key(self):
        with clean_env(KIRA_CLOUD_AI="1", GEMINI_API_KEY=FAKE_KEY):
            info = kira_ai.availability()
        self.assertTrue(info["gemini"]["key_present"])
        self.assertTrue(info["gemini"]["cloud_enabled"])
        self.assertEqual(info["default"], "ollama")
        self.assertNotIn(FAKE_KEY, str(info))

    def test_defaults_are_local_and_disabled(self):
        with clean_env():
            info = kira_ai.availability()
        self.assertFalse(info["gemini"]["cloud_enabled"])
        self.assertFalse(info["gemini"]["key_present"])


if __name__ == "__main__":
    unittest.main()
