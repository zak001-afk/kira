"""Tests for the vision pipeline: locate → click → verify.

Screenshots come from the pyautogui stub (which writes a real temp file),
the model is replaced by queued canned responses, and sleeps are disabled.
"""

import pytest


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)


class QueuedChat:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def __call__(self, model=None, messages=None, options=None, **kwargs):
        self.calls.append({"model": model, "messages": messages})
        payload = self.payloads.pop(0) if self.payloads else "no-more-responses"
        if isinstance(payload, Exception):
            raise payload
        return {"message": {"content": payload}}


def stubbed_calls(backend):
    return backend.__dict__["pyautogui"].calls


LOCATED = '{"found": true, "x": 100, "y": 200, "label": "Save", "confidence": 0.9, "reason": "visible"}'


class TestLocate:
    def test_happy_path(self, backend, monkeypatch):
        chat = QueuedChat(LOCATED)
        monkeypatch.setattr(backend, "chat", chat)
        result = backend.locate_on_screen("the save button")
        assert result["found"] is True
        assert (result["x"], result["y"]) == (100, 200)
        assert result["confidence"] == 0.9
        # the model received a screenshot path
        assert chat.calls[0]["messages"][0]["images"]

    def test_not_found(self, backend, monkeypatch):
        monkeypatch.setattr(
            backend,
            "chat",
            QueuedChat('{"found": false, "x": null, "y": null, "confidence": 0, "reason": "not visible"}'),
        )
        assert backend.locate_on_screen("a unicorn")["found"] is False

    def test_out_of_bounds_coordinates_rejected(self, backend, monkeypatch):
        monkeypatch.setattr(
            backend,
            "chat",
            QueuedChat('{"found": true, "x": 99999, "y": 200, "confidence": 0.9}'),
        )
        result = backend.locate_on_screen("anything")
        assert result["found"] is False
        assert "outside" in result["reason"]

    def test_invalid_json_handled(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "chat", QueuedChat("no idea"))
        result = backend.locate_on_screen("anything")
        assert result["found"] is False
        assert "invalid" in result["reason"]


class TestVisionClick:
    def test_clicks_and_verifies(self, backend, monkeypatch):
        chat = QueuedChat(LOCATED, '{"verified": true, "reason": "dialog opened"}')
        monkeypatch.setattr(backend, "chat", chat)
        result = backend.vision_click("the save button")
        assert result["success"] is True
        assert (result["x"], result["y"]) == (100, 200)
        calls = stubbed_calls(backend)
        assert ("moveTo", (100, 200), {"duration": 0.18}) in calls
        assert ("click", (), {}) in calls

    def test_low_confidence_never_clicks(self, backend, monkeypatch):
        low = '{"found": true, "x": 100, "y": 200, "label": "Save", "confidence": 0.4}'
        monkeypatch.setattr(backend, "chat", QueuedChat(low))
        result = backend.vision_click("the save button", confidence_threshold=0.7)
        assert result["success"] is False
        assert "confidence" in result["message"]
        assert ("click", (), {}) not in stubbed_calls(backend)

    def test_unverified_click_reports_failure(self, backend, monkeypatch):
        chat = QueuedChat(LOCATED, '{"verified": false, "reason": "nothing changed"}')
        monkeypatch.setattr(backend, "chat", chat)
        result = backend.vision_click("the save button")
        assert result["success"] is False
        assert "could not visually verify" in result["message"]

    def test_target_not_found(self, backend, monkeypatch):
        monkeypatch.setattr(
            backend,
            "chat",
            QueuedChat('{"found": false, "reason": "not visible"}'),
        )
        result = backend.vision_click("a hidden button")
        assert result["success"] is False
        assert "could not find" in result["message"]

    def test_empty_target(self, backend):
        result = backend.vision_click("   ")
        assert result["success"] is False
        assert "need to know" in result["message"]


class TestAnalyzeScreen:
    def test_returns_cleaned_answer(self, backend, monkeypatch):
        monkeypatch.setattr(
            backend,
            "chat",
            QueuedChat("<think>looking</think>You have Chrome open with two tabs, sir."),
        )
        answer = backend.analyze_screen("what is open?")
        # personalize_address() strips the comma before the title
        assert answer == "You have Chrome open with two tabs sir."

    def test_model_failure_is_explained(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "chat", QueuedChat(ConnectionError("down")))
        answer = backend.analyze_screen("what is open?")
        assert "Vision analysis is unavailable" in answer


class TestVerifyClick:
    def test_parses_verdict(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "chat", QueuedChat('{"verified": true, "reason": "ok"}'))
        assert backend.verify_click("b.png", "a.png", "target") == {
            "verified": True,
            "reason": "ok",
        }

    def test_invalid_response(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "chat", QueuedChat("huh"))
        result = backend.verify_click("b.png", "a.png", "target")
        assert result["verified"] is False
        assert "Invalid verification" in result["reason"]
