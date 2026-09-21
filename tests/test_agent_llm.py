"""Tests for the LLM agent path: JSON extraction, fences, garbage, failures."""

import json

import pytest


@pytest.fixture
def fast_sleep(monkeypatch):
    """The retry loop in call_ollama sleeps between attempts — skip that."""
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)


def fake_chat(payload):
    def _fake(model=None, messages=None, options=None, **kwargs):
        return {"message": {"content": payload}}

    return _fake


class TestAskAgent:
    def test_parses_plain_json(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "chat", fake_chat('{"action": "type", "text": "hi"}'))
        assert backend.ask_agent("type hi") == {"action": "type", "text": "hi"}

    def test_parses_fenced_json(self, backend, monkeypatch):
        payload = '```json\n{"action": "open_app", "target": "notepad"}\n```'
        monkeypatch.setattr(backend, "chat", fake_chat(payload))
        assert backend.ask_agent("open notepad")["action"] == "open_app"

    def test_parses_json_embedded_in_prose(self, backend, monkeypatch):
        payload = 'Sure, sir! {"action": "volume_up"} There you go.'
        monkeypatch.setattr(backend, "chat", fake_chat(payload))
        assert backend.ask_agent("louder") == {"action": "volume_up"}

    def test_invalid_json_returns_none_action(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "chat", fake_chat("I cannot help with that"))
        assert backend.ask_agent("something") == {"action": "none"}

    def test_ollama_failure_returns_none_action(self, backend, monkeypatch, fast_sleep):
        def boom(**kwargs):
            raise ConnectionError("ollama is down")

        monkeypatch.setattr(backend, "chat", boom)
        assert backend.ask_agent("open chrome") == {"action": "none"}

    def test_sequence_from_model(self, backend, monkeypatch):
        payload = json.dumps(
            {
                "action": "sequence",
                "steps": [
                    {"action": "open_app", "target": "chrome"},
                    {"action": "search", "query": "docs"},
                ],
            }
        )
        monkeypatch.setattr(backend, "chat", fake_chat(payload))
        result = backend.ask_agent("open chrome and search docs")
        assert result["action"] == "sequence"
        assert len(result["steps"]) == 2
