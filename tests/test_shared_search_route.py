"""Shared-knowledge search must answer fast, as data, and survive disconnects.

Regression coverage for the fix that was verified on Windows but had not been
committed: /api/command with "search shared knowledge for X" used to run
backend.execute_action, which spoke every result synchronously and could call
Ollama for translation before the HTTP response returned.

Also covers the WinError 10053 family: closing the window mid-request must not
produce tracebacks when the server writes the response.
"""
import io
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import kira_commands as commands
import kira_tools


RESEARCH = "Shared knowledge about 'python':\n\n1. **Decorators**\n   Functions wrapping functions."


def fake_web(reply=RESEARCH, error=None):
    def search_shared_knowledge(query, limit=5):
        if error is not None:
            raise error
        return f"{reply} [q={query} limit={limit}]"
    return types.SimpleNamespace(search_shared_knowledge=search_shared_knowledge)


class SharedSearchRouteTests(unittest.TestCase):
    """The fast path: data out, no speech, no execute_action, no Ollama."""

    def backend(self):
        return SimpleNamespace(
            normalize_command=lambda text: text,
            parse_simple_command=Mock(return_value={"action": "search_shared_knowledge", "query": "python"}),
            ask_chat=Mock(return_value="chat"),
            execute_action=Mock(return_value=True),
            build_reply=Mock(return_value="Done."),
            call_ollama=Mock(return_value={"message": {"content": "irrelevant"}}),
        )

    def run_command(self, backend, web=None):
        with patch.dict("sys.modules", kira_web=web or fake_web()):
            asked = commands.process_command(backend, "search shared knowledge for python")
            # La secrétaire annonce OÙ elle cherche avant d'exécuter.
            self.assertEqual(asked["action"], "intent")
            self.assertTrue(asked["needs_confirmation"])
            return commands.process_command(backend, "yes")

    def test_returns_research_text_immediately(self):
        result = self.run_command(self.backend())
        self.assertEqual(result["action"], "search_shared_knowledge")
        self.assertTrue(result["success"])
        self.assertIn("Shared knowledge about 'python'", result["response"])
        self.assertIn("limit=3", result["response"])  # limit=3 exactly as verified on Windows.

    def test_backend_never_executes_or_speaks_on_this_route(self):
        backend = self.backend()
        self.run_command(backend)
        backend.execute_action.assert_not_called()  # The voice handler would speak synchronously.
        backend.build_reply.assert_not_called()

    def test_no_model_translation_on_this_route(self):
        backend = self.backend()
        with patch.dict("sys.modules", kira_web=fake_web()):
            commands.process_command(backend, "search shared knowledge for python",
                                     reply_language="fr", interface_language="fr")
            result = commands.process_command(backend, "yes",
                                              reply_language="fr", interface_language="fr")
        backend.call_ollama.assert_not_called()
        self.assertTrue(result["success"])

    def test_timing_is_reported(self):
        result = self.run_command(self.backend())
        self.assertIsInstance(result["elapsed_ms"], int)
        self.assertGreaterEqual(result["elapsed_ms"], 0)

    def test_tool_failure_is_structured_not_a_500(self):
        backend = self.backend()
        result = self.run_command(backend, web=fake_web(error=RuntimeError("supabase down")))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "tool_failed")
        self.assertIn("supabase down", result["error"])
        self.assertIn("supabase down", result["response"])  # Text-only clients still see the reason.
        backend.execute_action.assert_not_called()

    def test_language_metadata_still_present(self):
        result = self.run_command(self.backend())
        self.assertIn("language", result)

    def test_other_actions_keep_the_existing_path(self):
        backend = self.backend()
        backend.parse_simple_command.return_value = {"action": "open_app", "target": "chrome"}
        asked = commands.process_command(backend, "open chrome")
        self.assertEqual(asked["action"], "intent")       # annonce avant l'action
        result = commands.process_command(backend, "yes")
        backend.execute_action.assert_called_once()
        self.assertTrue(result["success"])


class ToolResultTests(unittest.TestCase):
    def test_success_payload_shape(self):
        result = kira_tools.run_tool("demo", lambda: "hello")
        payload = result.to_payload(language="en")
        self.assertEqual(payload["action"], "demo")
        self.assertTrue(payload["success"])
        self.assertEqual(payload["response"], "hello")
        self.assertEqual(payload["language"], "en")
        self.assertIn("elapsed_ms", payload)

    def test_failure_payload_shape(self):
        result = kira_tools.run_tool("demo", Mock(side_effect=ValueError("bad")))
        payload = result.to_payload()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "tool_failed")
        self.assertEqual(payload["error"], "bad")

    def test_timing_measures_the_call(self):
        import time
        result = kira_tools.run_tool("demo", lambda: time.sleep(0.02) or "ok")
        self.assertGreaterEqual(result.elapsed_ms, 15)


class _AbortingWriter(io.RawIOBase):
    """A wfile whose client has vanished (WinError 10053 family)."""

    def __init__(self, error):
        self.error = error

    def write(self, _data):
        raise self.error

    def flush(self):
        pass


def make_handler(handler_class, error):
    """Handler instance with a dead socket and no real network setup."""
    handler = object.__new__(handler_class)
    handler.wfile = _AbortingWriter(error)
    handler.send_response = Mock(side_effect=error)
    handler.send_header = Mock()
    handler.end_headers = Mock()
    return handler


class DisconnectTests(unittest.TestCase):
    """Closing the window mid-request must not raise in either server."""

    ERRORS = (ConnectionAbortedError("WinError 10053"),
              ConnectionResetError("WinError 10054"),
              BrokenPipeError("EPIPE"))

    def test_api_send_json_survives_client_disconnect(self):
        import kira_api
        for error in self.ERRORS:
            handler = make_handler(kira_api.KiraAPIHandler, error)
            handler._send_json({"response": "late answer"})  # Must not raise.

    def test_ui_proxy_write_survives_client_disconnect(self):
        import kira_ui
        for error in self.ERRORS:
            handler = make_handler(kira_ui.KiraUIHandler, error)
            handler._send_payload(200, "application/json", b"{}")  # Must not raise.
            handler._json_error(503, "backend unavailable")  # Must not raise.

    def test_connected_clients_still_get_their_payload(self):
        import kira_api
        handler = object.__new__(kira_api.KiraAPIHandler)
        written = []
        handler.wfile = SimpleNamespace(write=written.append, flush=lambda: None)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler._send_json({"response": "hello"})
        self.assertEqual(len(written), 1)
        self.assertIn(b"hello", written[0])


if __name__ == "__main__":
    unittest.main()
