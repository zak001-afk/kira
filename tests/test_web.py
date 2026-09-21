"""Tests for the browser interface: kira_server.py and the ui/ files.

Two layers are covered:

* **KiraService** — the routing half. It is driven with a fake backend module
  so the real command pipeline (parser → confirmation → execute → learn) is
  exercised without any Windows dependency, plus simulation/offline modes.
* **The HTTP layer** — a real server on an ephemeral port, hit with real
  requests: JSON endpoints, static files, traversal defence, CORS/preview
  headers, and a drift check between ui/app.js and ui/index.html.
"""
from __future__ import annotations

import http.client
import json
import re
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

import kira_server

ROOT = Path(__file__).resolve().parent.parent


# ── fake backend ─────────────────────────────────────────────────────────────


class FakeMemory:
    def __init__(self):
        self.learnings = []

    def learnings_summary(self):
        return {"count": len(self.learnings)}

    def episode_counts(self):
        return {"total": 42}

    def load_memories(self):
        return {"language": "en", "name": "sir"}


class FakeLearning:
    def __init__(self):
        self.captured = []

    def capture(self, action):
        self.captured.append(action)


class FakeUndo:
    def __init__(self):
        self.recorded = []

    def record(self, text, action):
        self.recorded.append((text, action))


class FakeClock:
    """Stand-in for a think_about() result."""

    def __init__(self, action, source="llm", text="I will open that for you."):
        self.action = action
        self.source = source
        self.text = text


class FakeBackend(SimpleNamespace):
    """Mimics the slice of kira_voice_agent that KiraService talks to."""

    def __init__(self, **overrides):
        super().__init__()
        self.VERSION = "9.9.9-test"
        self.MODEL = "fake-model"
        self.CONFIG = {"monitor": {"enabled": True}}
        self.USER_MEMORY = {"language": "en"}
        self.kira_memory = FakeMemory()
        self.kira_learning = FakeLearning()
        self.kira_undo = FakeUndo()
        self.executed = []
        self.learned = []
        self.calls = []

        # routing knobs the tests flip per case
        self.lab_locked_reply = None
        self.simple_result = None
        self.chat_question = False
        self.chat_reply = "Some local answer."
        self.think_result = None
        self.confirm_actions = {"open_app", "search"}
        self.execute_result = True
        self.vision_result = None

        for key, value in overrides.items():
            setattr(self, key, value)

    # pipeline
    def normalize_command(self, text):
        return str(text or "").lower().strip()

    def lab_gate(self, text):
        return self.lab_locked_reply

    def parse_simple_command(self, text):
        self.calls.append(("parse", text))
        return self.simple_result

    def is_chat_question(self, text):
        return self.chat_question

    def ask_chat(self, text):
        self.calls.append(("chat", text))
        return self.chat_reply

    def think_about(self, text):
        self.calls.append(("think", text))
        return self.think_result

    def requires_confirmation(self, action):
        return action in self.confirm_actions

    def plan_vision_command(self, text):
        self.calls.append(("vision", text))
        return self.vision_result

    def action_succeeded(self, result):
        """The real backend answers True/False, a string, or a dict."""
        if isinstance(result, dict):
            return bool(result.get("success"))
        return bool(result)

    def outcome_message(self, result):
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return str(result.get("message") or "")
        return ""

    def describe_action(self, result):
        return f"Shall I {result.get('action')} {result.get('target', '')}?".strip()

    def detect_language(self, text):
        return "en"

    def execute_action(self, result):
        self.executed.append(result)
        return self.execute_result

    def learn_from(self, text, result, source, success, language=None):
        self.learned.append((text, source, success))
        return "I'll remember that routine."

    def build_reply(self, language, action, target=""):
        if action == "none":
            return "I could not do that, sir."
        return f"Done: {action} {target}".strip()

    def listen_for_command(self, timeout=6, phrase_timeout=4):
        return "open chrome"


def service_with_backend(**overrides) -> tuple:
    service = kira_server.KiraService(simulate=False)
    backend = FakeBackend(**overrides)
    service.backend = backend
    service.reason = ""
    return service, backend


# ── service: modes ───────────────────────────────────────────────────────────


class TestServiceModes:
    def test_simulation_mode_is_labelled(self):
        service = kira_server.KiraService(simulate=True)
        assert service.online is True
        assert service.mode == "simulation"
        assert service.version == "sim"

    def test_offline_is_not_labelled_as_a_simulation(self):
        """A half-installed agent is not a demo, and must not read like one."""
        service = kira_server.KiraService(simulate=False)
        service.backend = None
        version = service.version
        assert version != "sim", "offline mode called itself a simulation"
        assert re.match(r"^\d+\.\d+", version), (
            f"the offline interface cannot say which build it is: {version!r}"
        )
        # ...and it agrees with the one place the number is written down
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert f'version = "{version}"' in pyproject

    def test_offline_mode_explains_itself(self):
        service = kira_server.KiraService(simulate=False)
        service.backend = None
        service.reason = "ModuleNotFoundError: No module named 'pyautogui'"
        assert service.online is False
        assert service.mode == "offline"

        result = service.handle_command("open chrome")
        assert result["kind"] == "error"
        assert "pyautogui" in result["reply"]
        assert result["mode"] == "offline"

    def test_live_mode_reports_the_backend_version(self):
        service, _ = service_with_backend()
        assert service.online is True
        assert service.mode == "live"
        assert service.version == "9.9.9-test"

    def test_empty_command_is_ignored(self):
        service, backend = service_with_backend()
        result = service.handle_command("   ")
        assert result["kind"] == "empty"
        assert backend.calls == []


class TestSimulatedCommands:
    def test_canned_answers(self):
        service = kira_server.KiraService(simulate=True)
        assert "ready" in service.handle_command("hello")["reply"].lower()
        assert "nominal" in service.handle_command("systems check")["reply"]
        assert "learned" in service.handle_command("what did you learn")["reply"]

    def test_trigger_actions_are_prefixed_as_simulation(self):
        service = kira_server.KiraService(simulate=True)
        result = service.handle_command("open chrome")
        assert result["reply"].startswith("(simulation)")
        assert result["action"] == "open_app"

    def test_unknown_input_stays_honest(self):
        service = kira_server.KiraService(simulate=True)
        result = service.handle_command("book me a flight to mars")
        assert "(simulation)" in result["reply"]
        assert "book me a flight to mars" in result["reply"]

    def test_simulation_listen_returns_text_without_a_microphone(self):
        service = kira_server.KiraService(simulate=True)
        assert service.listen() == {"text": "systems check", "simulated": True}


# ── service: the real routing pipeline ───────────────────────────────────────


class TestRouting:
    def test_locked_lab_gates_everything(self):
        service, backend = service_with_backend(lab_locked_reply="The lab is locked.")
        result = service.handle_command("open chrome")
        assert result["kind"] == "security"
        assert result["reply"] == "The lab is locked."
        assert backend.executed == []

    def test_chat_question_goes_straight_to_the_model(self):
        service, backend = service_with_backend(chat_question=True)
        result = service.handle_command("what do you think about jazz?")
        assert result["kind"] == "chat"
        assert result["reply"] == "Some local answer."
        assert ("chat", "what do you think about jazz?") in backend.calls

    def test_parser_action_executes_and_reports(self):
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
            confirm_actions=set(),
        )
        result = service.handle_command("open chrome")
        assert result["kind"] == "action"
        assert result["ok"] is True
        assert result["action"] == "open_app"
        assert result["reply"] == "Done: open_app chrome"
        assert backend.executed == [{"action": "open_app", "target": "chrome"}]
        assert backend.kira_learning.captured == [{"action": "open_app", "target": "chrome"}]
        assert backend.kira_undo.recorded == [("open chrome", {"action": "open_app", "target": "chrome"})]

    def test_action_none_falls_back_to_chat(self):
        service, backend = service_with_backend(
            simple_result={"action": "none"},
            chat_question=False,
            think_result=None,
        )
        result = service.handle_command("hmm")
        assert result["kind"] == "chat"
        assert result["reply"] == "Some local answer."

    def test_llm_plan_carries_the_thought_and_teaches_the_routine(self):
        service, backend = service_with_backend(
            simple_result=None,
            think_result=FakeClock(
                {"action": "open_app", "target": "vscode"},
                source="llm",
                text="The user means the code editor.",
            ),
            confirm_actions=set(),
        )
        result = service.handle_command("open my editor")
        assert result["thought"] == "The user means the code editor."
        assert result["ok"] is True
        assert result["reply"].endswith("I'll remember that routine.")
        assert backend.learned == [("open my editor", "llm", True)]

    def test_memory_plan_also_learns(self):
        service, backend = service_with_backend(
            simple_result=None,
            think_result=FakeClock({"action": "volume_up"}, source="memory"),
            confirm_actions=set(),
        )
        service.handle_command("louder")
        assert backend.learned == [("louder", "memory", True)]

    def test_parser_plans_are_not_relearned(self):
        service, backend = service_with_backend(
            simple_result={"action": "volume_up"},
            confirm_actions=set(),
        )
        service.handle_command("volume up")
        assert backend.learned == []

    def test_failed_action_asks_the_backend_for_an_apology(self):
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "ghost"},
            confirm_actions=set(),
            execute_result=False,
        )
        result = service.handle_command("open ghost")
        assert result["ok"] is False
        assert result["reply"] == "I could not do that, sir."
        assert backend.kira_learning.captured == []  # nothing learned from a failure

    def test_string_success_is_used_verbatim(self):
        service, _ = service_with_backend(
            simple_result={"action": "screenshot"},
            confirm_actions=set(),
            execute_result="Screenshot saved, sir.",
        )
        result = service.handle_command("screenshot")
        assert result["ok"] is True
        assert result["reply"] == "Screenshot saved, sir."


class TestConfirmation:
    def test_dangerous_action_asks_the_page_first(self):
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
        )
        result = service.handle_command("open chrome")
        assert result["needs_confirmation"] is True
        assert result["kind"] == "confirm"
        assert result["state"] == "CONFIRM"
        assert result["action_name"] == "open_app"
        assert backend.executed == [], "nothing may run before the user confirms"
        assert service.state == "CONFIRM"

    def test_confirming_runs_the_pending_action(self):
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
        )
        pending = service.handle_command("open chrome")
        result = service.handle_command(
            "", confirm=True, confirm_token=pending["confirm_token"]
        )
        assert result["kind"] == "action"
        assert result["ok"] is True
        assert backend.executed == [{"action": "open_app", "target": "chrome"}]
        assert service.state == "READY"

    def test_a_guessed_confirmation_is_refused(self):
        """A page that never saw the prompt cannot answer it."""
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
        )
        service.handle_command("open chrome")
        result = service.handle_command("", confirm=True, confirm_token="not-the-nonce")
        assert result["kind"] == "error"
        assert backend.executed == [], "a forged confirmation ran the action"
        # the action is still pending and can be confirmed properly
        assert service._pending is not None

    def test_a_pending_action_only_fires_once(self):
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
        )
        pending = service.handle_command("open chrome")
        nonce = pending["confirm_token"]
        service.handle_command("", confirm=True, confirm_token=nonce)
        # a second confirm has nothing pending and must not re-run anything
        service.handle_command("", confirm=True, confirm_token=nonce)
        assert len(backend.executed) == 1

    def test_confirm_without_pending_is_harmless(self):
        service, backend = service_with_backend()
        result = service.handle_command("", confirm=True)
        assert result["kind"] == "empty"
        assert backend.executed == []

    def test_llm_plans_are_confirmed_exactly_once(self):
        """The model used to run dangerous plans unasked. It no longer may.

        "Exactly once" is the whole point: the plan is held, the page asks,
        and the confirmation runs *that* plan — it is never re-planned and
        never confirmed twice.
        """
        plan = {"action": "open_app", "target": "vscode"}
        service, backend = service_with_backend(
            simple_result=None,
            think_result=FakeClock(plan, source="llm"),
        )
        result = service.handle_command("open my editor")
        assert result["needs_confirmation"] is True
        assert result["action_name"] == "open_app"
        assert result["confirm_token"]
        assert backend.executed == [], "the model's plan ran before the user said yes"
        assert backend.learned == [], "nothing may be learned from an unapproved plan"

        done = service.handle_command(
            "", confirm=True, confirm_token=result["confirm_token"]
        )
        assert done["ok"] is True
        assert backend.executed == [plan], "the plan did not run exactly once"

    def test_memory_recall_is_confirmed_too(self):
        """A recalled routine is still a click on your machine."""
        service, backend = service_with_backend(
            simple_result=None,
            think_result=FakeClock({"action": "click", "target": "submit"}, source="memory"),
            confirm_actions={"click"},
        )
        result = service.handle_command("do the thing i taught you")
        assert result["needs_confirmation"] is True
        assert backend.executed == []

    def test_a_chat_question_is_never_held_for_confirmation(self):
        service, backend = service_with_backend(simple_result=None, chat_question=True)
        result = service.handle_command("why is the sky blue")
        assert result["kind"] == "chat"
        assert "needs_confirmation" not in result


class TestTelemetryCost:
    """Polling is what a dashboard does most; it must not be what costs most."""

    def test_many_pollers_share_one_sample(self, monkeypatch):
        service, _ = service_with_backend()
        sampled = []
        original = service._sample_metrics

        def counting():
            sampled.append(1)
            return original()

        monkeypatch.setattr(service, "_sample_metrics", counting)
        for _ in range(25):
            service.telemetry()
        assert len(sampled) == 1, f"25 polls cost {len(sampled)} samples"

    def test_the_sample_refreshes_once_it_has_expired(self, monkeypatch):
        service, _ = service_with_backend()
        sampled = []
        original = service._sample_metrics

        def counting():
            sampled.append(1)
            return original()

        monkeypatch.setattr(service, "_sample_metrics", counting)
        clock = [1000.0]
        monkeypatch.setattr(kira_server.time, "monotonic", lambda: clock[0])
        service.telemetry()
        clock[0] += kira_server.TELEMETRY_TTL / 2
        service.telemetry()
        assert len(sampled) == 1, "a fresh sample was thrown away"
        clock[0] += kira_server.TELEMETRY_TTL
        service.telemetry()
        assert len(sampled) == 2, "a stale sample was served"

    def test_every_caller_gets_its_own_dict(self):
        """A caller must not be able to scribble on the cached sample."""
        service, _ = service_with_backend()
        first = service.telemetry()
        first["cpu"] = "vandalised"
        if isinstance(first.get("battery"), dict):
            first["battery"]["percent"] = 0
        second = service.telemetry()
        assert second.get("cpu") != "vandalised"
        if isinstance(second.get("battery"), dict):
            assert second["battery"]["percent"] != 0

    def test_the_hud_quality_knob_is_reported(self, monkeypatch):
        service, backend = service_with_backend()
        monkeypatch.setitem(backend.CONFIG, "orb_quality", "low")
        assert service.telemetry()["quality"] == "low"


class TestVisionRouting:
    """The screen pipeline existed but nothing ever called it."""

    def test_a_screen_question_reaches_the_vision_pipeline(self):
        service, backend = service_with_backend(
            simple_result=None,
            vision_result={"action": "look_at_screen", "question": "what is on my screen"},
            execute_result="You have two browser windows open, sir.",
        )
        result = service.handle_command("what is on my screen")
        assert ("vision", "what is on my screen") in backend.calls
        assert result["reply"] == "You have two browser windows open, sir."
        assert result["action"] == "look_at_screen"

    def test_a_screen_question_never_falls_through_to_chat(self):
        service, backend = service_with_backend(
            simple_result=None,
            vision_result={"action": "look_at_screen", "question": "what is on my screen"},
            chat_question=True,
        )
        service.handle_command("what is on my screen")
        assert not any(call[0] == "chat" for call in backend.calls)

    def test_a_vision_click_asks_before_touching_the_mouse(self):
        service, backend = service_with_backend(
            simple_result=None,
            vision_result={"action": "vision_click", "target": "the save button"},
            confirm_actions={"vision_click"},
            execute_result={"success": True, "message": "Clicked the save button."},
        )
        result = service.handle_command("find the save button and click it")
        assert result["needs_confirmation"] is True
        assert backend.executed == []
        done = service.handle_command(
            "", confirm=True, confirm_token=result["confirm_token"]
        )
        assert done["ok"] is True
        assert done["reply"] == "Clicked the save button."

    def test_a_failed_screen_click_is_reported_as_a_failure(self):
        service, backend = service_with_backend(
            simple_result=None,
            confirm_actions=set(),
            vision_result={"action": "vision_click", "target": "a hidden button"},
            execute_result={"success": False, "message": "I could not find it on screen."},
        )
        result = service.handle_command("find the hidden button and click it")
        assert result["ok"] is False
        assert result["kind"] == "error"
        assert result["reply"] == "I could not find it on screen."
        assert backend.executed == [{"action": "vision_click", "target": "a hidden button"}]

    def test_an_ordinary_command_skips_the_vision_pipeline(self):
        service, backend = service_with_backend(simple_result={"action": "volume_up"})
        service.handle_command("volume up")
        assert not any(call[0] == "vision" for call in backend.calls)


class TestHistory:
    def test_both_sides_are_recorded(self):
        service, _ = service_with_backend(
            simple_result={"action": "volume_up"},
            confirm_actions=set(),
        )
        service.handle_command("volume up")
        messages = service.history(10)
        assert [message["role"] for message in messages] == ["kira"]
        assert messages[0]["text"] == "Done: volume_up"
        assert messages[0]["kind"] == "action"

    def test_limit_takes_the_tail(self):
        service, _ = service_with_backend()
        for index in range(12):
            service._record("kira", f"line {index}")
        tail = service.history(3)
        assert [message["text"] for message in tail] == ["line 9", "line 10", "line 11"]

    def test_history_is_capped(self):
        service, _ = service_with_backend()
        for index in range(250):
            service._record("kira", f"line {index}")
        assert len(service.history(500)) == 200

    def test_clearing_empties_it(self):
        service, _ = service_with_backend()
        service._record("kira", "hello")
        service.clear_history()
        assert service.history(10) == []


class TestProactive:
    def test_alerts_are_recorded_and_queued_once(self):
        service, _ = service_with_backend()
        service.push_proactive("Sir, the battery is low.")
        assert service.drain_proactive() == ["Sir, the battery is low."]
        assert service.drain_proactive() == []
        queued = [message for message in service.history(5) if message["kind"] == "proactive"]
        assert len(queued) == 1

    def test_blank_alerts_are_dropped(self):
        service, _ = service_with_backend()
        service.push_proactive("   ")
        service.push_proactive(None)
        assert service.drain_proactive() == []

    def test_telemetry_delivers_queued_alerts_then_clears_them(self):
        service, _ = service_with_backend()
        service.push_proactive("A reminder, sir.")
        assert service.telemetry()["queue"] == ["A reminder, sir."]
        assert service.telemetry()["queue"] == []

    def test_watchdog_alert_callback_reaches_the_queue(self):
        """start_background wires kira_monitor's alerts into the page queue."""
        started = {}

        class FakeWatch:
            @staticmethod
            def start(sampler=None, on_alert=None, config=None, language="en"):
                started.update(
                    {"sampler": sampler, "on_alert": on_alert, "language": language}
                )
                on_alert("Sir, CPU is at 97%.")
                return object()

        service, backend = service_with_backend(kira_monitor=FakeWatch, _sample_suit_telemetry=lambda: {})
        service.start_background()
        assert service.drain_proactive() == ["Sir, CPU is at 97%."]
        assert started["language"] == "en"

    def test_watchdog_failure_never_breaks_the_server(self):
        class ExplodingWatch:
            @staticmethod
            def start(**kwargs):
                raise RuntimeError("watchdog is unhappy")

        service, _ = service_with_backend(kira_monitor=ExplodingWatch)
        service.start_background()  # must not raise
        assert service._watchdog is None

    def test_simulation_skips_the_real_watchdog(self):
        service = kira_server.KiraService(simulate=True)
        service.backend = FakeBackend()
        service.start_background()
        assert service._watchdog is None


class TestTelemetry:
    def test_shape_is_stable_without_dependencies(self):
        service = kira_server.KiraService(simulate=True)
        data = service.telemetry()
        for key in (
            "online", "mode", "reason", "state", "version", "model", "cpu",
            "memory", "disk", "battery", "skills", "episodes", "memory_db",
            "uptime", "queue",
        ):
            assert key in data, f"telemetry lost the {key!r} field"
        assert data["mode"] == "simulation"
        assert isinstance(data["uptime"], int)
        assert data["queue"] == []

    def test_live_backend_supplies_model_and_memory_stats(self):
        service, _ = service_with_backend()
        service._record("kira", "one")
        data = service.telemetry()
        assert data["model"] == "fake-model"
        assert data["skills"] == 0
        assert data["episodes"] == 42
        assert data["memory_db"] == "2 facts"

    def test_broken_memory_module_does_not_break_telemetry(self):
        class ExplodingMemory:
            def learnings_summary(self):
                raise RuntimeError("database is gone")

            def episode_counts(self):
                raise RuntimeError("database is gone")

            def load_memories(self):
                raise RuntimeError("database is gone")

        service, backend = service_with_backend()
        backend.kira_memory = ExplodingMemory()
        data = service.telemetry()
        assert data["model"] == "fake-model"
        assert data["skills"] is None


# ── HTTP layer ───────────────────────────────────────────────────────────────


@pytest.fixture()
def ui_dir(tmp_path):
    directory = tmp_path / "ui"
    directory.mkdir()
    (directory / "index.html").write_text("<html><body>KIRA</body></html>", encoding="utf-8")
    (directory / "app.js").write_text("console.log('kira');\n", encoding="utf-8")
    (directory / "style.css").write_text("body { color: red; }\n", encoding="utf-8")
    (directory / "secret.py").write_text("print('not served')\n", encoding="utf-8")
    (directory / "notes.json").write_text('{"ok": true}', encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text('{"leak": true}', encoding="utf-8")
    return directory


@pytest.fixture()
def web(ui_dir):
    """A real server on an ephemeral port, with a fake backend attached."""
    service = kira_server.KiraService(simulate=False, ui_dir=ui_dir)
    backend = FakeBackend(
        simple_result={"action": "volume_up"},
        confirm_actions=set(),
    )
    service.backend = backend
    service.reason = ""
    server = kira_server.KiraWebServer(("127.0.0.1", 0), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield SimpleNamespace(
            host=host, port=port, service=service, backend=backend, server=server
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(web, method: str, path: str, payload=None, extra_headers=None) -> tuple:
    """Returns (status, headers, body-bytes)."""
    connection = http.client.HTTPConnection(web.host, web.port, timeout=5)
    body = None
    headers = dict(extra_headers or {})
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def request_json(web, method: str, path: str, payload=None, extra_headers=None) -> tuple:
    status, headers, body = request(web, method, path, payload, extra_headers)
    return status, json.loads(body.decode("utf-8") or "null")


@pytest.fixture()
def guarded(ui_dir):
    """A server with a token required, so the LAN case can be exercised."""
    service = kira_server.KiraService(
        simulate=False, ui_dir=ui_dir, token="s3cret-token",
        allowed_hosts={"kira.local"},
    )
    backend = FakeBackend(simple_result={"action": "volume_up"}, confirm_actions=set())
    service.backend = backend
    service.reason = ""
    server = kira_server.KiraWebServer(("127.0.0.1", 0), service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield SimpleNamespace(
            host=host, port=port, service=service, backend=backend, server=server
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def raw_request(web, target: str) -> int:
    """Sends an unnormalised request line, so traversal attempts are honest."""
    with socket.create_connection((web.host, web.port), timeout=5) as sock:
        sock.sendall(
            f"GET {target} HTTP/1.1\r\nHost: {web.host}\r\nConnection: close\r\n\r\n".encode()
        )
        return int(sock.recv(64).split(b" ")[1])


class TestHttpApi:
    def test_health(self, web):
        status, data = request_json(web, "GET", "/api/health")
        assert status == 200
        assert data["ok"] is True
        assert data["online"] is True
        assert data["mode"] == "live"
        assert data["version"] == "9.9.9-test"

    def test_state_serves_telemetry(self, web):
        status, data = request_json(web, "GET", "/api/state")
        assert status == 200
        assert data["model"] == "fake-model"
        assert data["state"] == "READY"

    def test_command_round_trip(self, web):
        status, data = request_json(web, "POST", "/api/command", {"text": "volume up"})
        assert status == 200
        assert data["kind"] == "action"
        assert data["ok"] is True
        assert web.backend.executed == [{"action": "volume_up"}]

    def test_confirmation_round_trip(self, web):
        web.backend.simple_result = {"action": "open_app", "target": "chrome"}
        web.backend.confirm_actions = {"open_app"}
        _, pending = request_json(web, "POST", "/api/command", {"text": "open chrome"})
        assert pending["needs_confirmation"] is True

        _, refused = request_json(
            web, "POST", "/api/command", {"text": "", "confirm": True}
        )
        assert refused["kind"] == "error", "a bare confirm must be refused"
        assert web.backend.executed == []

        _, done = request_json(
            web,
            "POST",
            "/api/command",
            {"text": "", "confirm": True, "confirm_token": pending["confirm_token"]},
        )
        assert done["ok"] is True
        assert web.backend.executed == [{"action": "open_app", "target": "chrome"}]

    def test_history_reflects_commands(self, web):
        request_json(web, "POST", "/api/command", {"text": "volume up"})
        _, data = request_json(web, "GET", "/api/history?limit=5")
        assert data["messages"][-1]["text"] == "Done: volume_up"

    def test_history_limit_is_parsed(self, web):
        for index in range(8):
            web.service._record("kira", f"line {index}")
        _, data = request_json(web, "GET", "/api/history?limit=3")
        assert len(data["messages"]) == 3

    def test_reset_clears_history(self, web):
        request_json(web, "POST", "/api/command", {"text": "volume up"})
        status, data = request_json(web, "POST", "/api/reset")
        assert (status, data["ok"]) == (200, True)
        _, history = request_json(web, "GET", "/api/history")
        assert history["messages"] == []

    def test_listen_uses_the_backend(self, web):
        status, data = request_json(web, "POST", "/api/listen")
        assert status == 200
        assert data["text"] == "open chrome"

    def test_unknown_endpoint_is_404(self, web):
        status, data = request_json(web, "GET", "/api/nope")
        assert status == 404
        assert "unknown endpoint" in data["error"]

    def test_malformed_body_does_not_crash(self, web):
        connection = http.client.HTTPConnection(web.host, web.port, timeout=5)
        try:
            connection.request(
                "POST",
                "/api/command",
                body=b"{not json",
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            assert response.status == 200
            assert json.loads(response.read())["kind"] == "empty"
        finally:
            connection.close()

    def test_head_and_options_are_supported(self, web):
        status, _, _ = request(web, "HEAD", "/api/health")
        assert status == 200
        status, _, _ = request(web, "OPTIONS", "/api/command")
        assert status == 204


class TestStaticFiles:
    def test_index_is_served_at_the_root(self, web):
        status, headers, body = request(web, "GET", "/")
        assert status == 200
        assert b"KIRA" in body
        assert headers["Content-Type"].startswith("text/html")

    def test_javascript_gets_a_script_content_type(self, web):
        status, headers, body = request(web, "GET", "/app.js")
        assert status == 200
        assert "javascript" in headers["Content-Type"]
        assert b"console.log" in body

    def test_css_is_served(self, web):
        status, headers, _ = request(web, "GET", "/style.css")
        assert status == 200
        assert headers["Content-Type"].startswith("text/css")

    def test_missing_file_is_404(self, web):
        status, _, _ = request(web, "GET", "/nothing-here.js")
        assert status == 404

    def test_unlisted_extensions_are_refused(self, web):
        status, data = request_json(web, "GET", "/secret.py")
        assert status == 403
        assert "not served" in data["error"]

    def test_license_files_are_served(self, web, ui_dir):
        (ui_dir / "vendor").mkdir()
        (ui_dir / "vendor" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        status, headers, body = request(web, "GET", "/vendor/LICENSE")
        assert status == 200
        assert b"MIT License" in body
        assert headers["Content-Type"].startswith("text/plain")

    @pytest.mark.parametrize(
        "target",
        [
            "/../outside.json",
            "/../../etc/passwd",
            "/..%2foutside.json",
            "/%2e%2e/outside.json",
            "/subdir/../../outside.json",
        ],
    )
    def test_traversal_is_blocked(self, web, target):
        assert raw_request(web, target) == 404

    def test_preview_headers(self, web):
        """The UI must be embeddable and never cached by the preview pane."""
        _, headers, _ = request(web, "GET", "/")
        assert headers.get("Cache-Control") == "no-store"
        assert "X-Frame-Options" not in headers

    def test_vendored_runtime_is_cached_for_good(self, web, ui_dir):
        """three.js is ~330 KB and never edited in place: do not re-send it."""
        (ui_dir / "vendor").mkdir(exist_ok=True)
        (ui_dir / "vendor" / "three.module.min.js").write_text(
            "// three\n", encoding="utf-8"
        )
        status, headers, _ = request(web, "GET", "/vendor/three.module.min.js")
        assert status == 200
        assert "immutable" in headers.get("Cache-Control", "")
        assert "immutable" not in request(web, "GET", "/app.js")[1].get("Cache-Control", "")

    def test_the_huds_own_files_are_never_cached(self, web):
        for path in ("/", "/app.js", "/style.css"):
            _, headers, _ = request(web, "GET", path)
            assert headers.get("Cache-Control") == "no-store", path

    def test_no_cors_headers_are_sent(self, web):
        """No Access-Control-Allow-* means no other page can read a response."""
        for path in ("/", "/api/state"):
            _, headers, _ = request(web, "GET", path)
            leaked = [key for key in headers if key.lower().startswith("access-control")]
            assert leaked == [], f"{path} advertises {leaked}"



class TestAccessControl:
    """A local agent is still reachable from every page you visit.

    The API can click, type and lock the machine, so these tests are the
    difference between "a neat local tool" and "a remote control for
    anything you browse past".
    """

    def test_a_site_cannot_drive_the_api(self, web):
        status, body = request_json(
            web, "POST", "/api/command",
            {"text": "open chrome"},
            extra_headers={"Origin": "https://evil.example"},
        )
        assert status == 403
        assert web.backend.executed == [], "a hostile page ran a command"

    def test_a_site_cannot_read_telemetry(self, web):
        status, _ = request_json(
            web, "GET", "/api/state",
            extra_headers={"Origin": "https://evil.example"},
        )
        assert status == 403

    def test_a_site_cannot_listen_through_the_microphone(self, web):
        status, _ = request_json(
            web, "POST", "/api/listen", {},
            extra_headers={"Origin": "https://evil.example"},
        )
        assert status == 403

    def test_a_rebound_hostname_is_refused(self, web):
        """DNS rebinding names this machine with the attacker's domain."""
        status, body = request_json(
            web, "GET", "/api/state",
            extra_headers={"Host": "evil.example", "Origin": "http://evil.example"},
        )
        assert status == 403
        assert b"host" in body["error"].encode() or "host" in body["error"]

    def test_the_hud_talking_to_itself_is_allowed(self, web):
        origin = f"http://127.0.0.1:{web.port}"
        status, data = request_json(
            web, "GET", "/api/state", extra_headers={"Origin": origin}
        )
        assert status == 200 and data["mode"] != ""

    def test_localhost_and_other_loopback_names_work(self, web):
        for name in ("localhost", "127.0.0.1"):
            status, _ = request_json(
                web, "GET", "/api/state",
                extra_headers={"Host": f"{name}:{web.port}"},
            )
            assert status == 200, f"{name} was refused"

    def test_command_line_clients_without_an_origin_work(self, web):
        status, data = request_json(web, "POST", "/api/command", {"text": "volume up"})
        assert status == 200 and data["ok"] is True

    def test_a_null_origin_is_refused(self, web):
        """A sandboxed frame or a file:// page reports Origin: null."""
        status, _ = request_json(
            web, "GET", "/api/state", extra_headers={"Origin": "null"}
        )
        assert status == 403

    def test_preflight_gives_a_foreign_origin_nothing(self, web):
        status, headers, _ = request(
            web, "OPTIONS", "/api/command",
            extra_headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert status == 204
        assert not any(k.lower().startswith("access-control") for k in headers)

    def test_an_extra_host_can_be_allowed_on_purpose(self, guarded):
        """A reverse proxy may be told which name it will use."""
        status, _ = request_json(
            guarded, "GET", "/api/state",
            extra_headers={"Host": "kira.local", "X-KIRA-Token": "s3cret-token"},
        )
        assert status == 200
        status, _ = request_json(
            guarded, "GET", "/api/state",
            extra_headers={"Host": "something.else", "X-KIRA-Token": "s3cret-token"},
        )
        assert status == 403


class TestToken:
    def test_a_lan_bind_generates_a_token(self):
        server = kira_server.create_server("0.0.0.0", 0, simulate=True)
        try:
            assert server.service.token, "a LAN bind left the API open"
            assert is_loopback_or_local(server, "127.0.0.1")
        finally:
            server.server_close()

    def test_a_loopback_bind_needs_no_token(self):
        """No ceremony for the normal case: the app on this machine."""
        server = kira_server.create_server("127.0.0.1", 0, simulate=True)
        try:
            assert server.service.token == ""
        finally:
            server.server_close()

    def test_the_token_is_enforced(self, guarded):
        assert request_json(guarded, "GET", "/api/state")[0] == 401
        assert request_json(
            guarded, "GET", "/api/state",
            extra_headers={"X-KIRA-Token": "wrong"},
        )[0] == 401
        assert request_json(
            guarded, "GET", "/api/state",
            extra_headers={"X-KIRA-Token": "s3cret-token"},
        )[0] == 200
        assert request_json(guarded, "GET", "/api/state?token=s3cret-token")[0] == 200

    def test_the_token_cannot_be_guessed_from_a_foreign_origin(self, guarded):
        status, _ = request_json(
            guarded, "POST", "/api/command", {"text": "open chrome"},
            extra_headers={"Origin": "https://evil.example", "X-KIRA-Token": "s3cret-token"},
        )
        assert status == 403, "the origin check must come first"

    def test_static_files_never_need_the_token(self, guarded):
        """The page has to load before it can present a token."""
        assert request(guarded, "GET", "/")[0] == 200
        assert request(guarded, "GET", "/app.js")[0] == 200

    def test_addresses_include_the_token_so_the_link_just_works(self):
        urls = kira_server.local_addresses(8788, "abc123")
        assert urls and all(url.endswith("?token=abc123") for url in urls)
        assert kira_server.local_addresses(8788) == ["http://127.0.0.1:8788"]

    def test_a_proxy_is_the_boundary_so_no_token_is_invented(self):
        """A generated token could never reach a browser behind a proxy."""
        server = kira_server.create_server("0.0.0.0", 0, simulate=True, trust_proxy=True)
        try:
            assert server.service.token == ""
            assert server.service.trust_proxy is True
        finally:
            server.server_close()

    def test_an_explicit_token_is_still_enforced_behind_a_proxy(self):
        server = kira_server.create_server(
            "0.0.0.0", 0, simulate=True, trust_proxy=True, token="mine"
        )
        try:
            assert server.service.token == "mine"
        finally:
            server.server_close()

    def test_a_chosen_token_is_kept(self):
        server = kira_server.create_server("0.0.0.0", 0, simulate=True, token="mine")
        try:
            assert server.service.token == "mine"
        finally:
            server.server_close()


class TestProxyMode:
    """--trust-proxy is for preview panes; it must be explicit and labelled."""

    def test_it_is_off_by_default(self, web):
        assert web.service.trust_proxy is False

    def test_it_accepts_a_forwarded_host_when_asked(self, ui_dir):
        server = kira_server.create_server(
            "127.0.0.1", 0, simulate=True, ui_dir=ui_dir, trust_proxy=True
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            status, _ = request_json(
                SimpleNamespace(host=host, port=port), "GET", "/api/state",
                extra_headers={"Host": "preview.example", "Origin": "https://preview.example"},
            )
            assert status == 200, "a preview pane would have been locked out"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def is_loopback_or_local(server, name):
    """The bound server answers to the machine's own names, never others."""
    return kira_server.is_loopback(name) or name in server.service.allowed_hosts

class TestClientAborts:
    """Browsers abandon requests all the time (reloads, cancelled polls)."""

    def test_a_vanished_client_is_not_an_error(self):
        class Vanished:
            def write(self, data):
                raise ConnectionResetError(104, "Connection reset by peer")

        handler = SimpleNamespace(
            command="GET",
            wfile=Vanished(),
            send_response=lambda *args: None,
            send_header=lambda *args: None,
            end_headers=lambda: None,
            close_connection=False,
        )
        kira_server.KiraRequestHandler._send(handler, 200, b"payload", "text/plain")
        assert handler.close_connection is True

    def test_the_server_keeps_serving_after_an_abort(self, web):
        with socket.create_connection((web.host, web.port), timeout=5) as sock:
            sock.sendall(b"GET /gone.js HTTP/1.1\r\nHost: x\r\n\r\n")
            # walk away before reading the response
        status, data = request_json(web, "GET", "/api/health")
        assert (status, data["ok"]) == (200, True)


# ── the shipped ui/ files ────────────────────────────────────────────────────


class TestShippedUi:
    def test_the_ui_directory_is_complete(self):
        for name in ("index.html", "app.js", "style.css"):
            path = ROOT / "ui" / name
            assert path.is_file(), f"ui/{name} is missing"
            assert path.stat().st_size > 500, f"ui/{name} looks empty"

    def test_index_loads_the_other_files(self):
        index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        assert 'src="./app.js"' in index
        assert 'href="./style.css"' in index

    def test_every_element_the_script_looks_for_exists(self):
        """Guards against a rename in one file silently breaking the HUD."""
        script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        wanted = set(re.findall(r'\$\("([^"]+)"\)', script))
        wanted.discard("")
        assert wanted, "no element lookups found — did app.js change shape?"
        missing = sorted(name for name in wanted if f'id="{name}"' not in index)
        assert missing == [], f"index.html is missing ids used by app.js: {missing}"

    def test_script_calls_the_expected_endpoints(self):
        script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        for endpoint in ("/api/state", "/api/history", "/api/command", "/api/listen", "/api/reset"):
            assert endpoint in script, f"app.js never calls {endpoint}"

    def test_no_leftover_template_stub(self):
        """The template only console.logged the command; ours must post it."""
        script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        assert "KIRA COMMAND" not in script
        assert "fetch(" in script


class TestUiMarkup:
    """No browser runs in CI, so the markup is checked structurally."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "source", "track", "wbr"}

    def test_tags_are_balanced(self):
        from html.parser import HTMLParser

        class Checker(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.errors = []
                self.ids = []

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if "id" in attributes:
                    self.ids.append(attributes["id"])
                if tag not in TestUiMarkup.VOID:
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if tag in TestUiMarkup.VOID:
                    return
                if not self.stack or self.stack[-1] != tag:
                    self.errors.append(f"unexpected </{tag}>")
                    return
                self.stack.pop()

        checker = Checker()
        checker.feed((ROOT / "ui" / "index.html").read_text(encoding="utf-8"))
        assert checker.errors == []
        assert checker.stack == [], f"unclosed tags: {checker.stack}"
        duplicates = {name for name in checker.ids if checker.ids.count(name) > 1}
        assert duplicates == set(), f"duplicate ids: {duplicates}"

    def test_css_blocks_are_balanced(self):
        css = (ROOT / "ui" / "style.css").read_text(encoding="utf-8")
        assert css.count("{") == css.count("}"), "unbalanced braces in style.css"
        assert css.count("/*") == css.count("*/"), "unbalanced comments in style.css"

    def test_the_hud_has_the_controls_a_user_needs(self):
        index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        for needed in (
            'id="command"', 'id="mic"', 'id="send"', 'id="conversation"',
            'id="confirm-bar"', "data-command=",
        ):
            assert needed in index, f"the interface has no {needed}"

    def test_clickable_areas_stay_clickable(self):
        """The HUD overlay ignores clicks; its controls must opt back in."""
        css = (ROOT / "ui" / "style.css").read_text(encoding="utf-8")
        hud = css[css.index("#hud {"): css.index("#hud {") + 200]
        assert "pointer-events: none" in hud, "the HUD would swallow every click"
        for selector in (".status-cluster", ".command-box", ".quick-actions",
                         ".confirm-bar", ".sidebar-nav", ".media-bar"):
            block = css[css.index(f"{selector} {{"): css.index(f"{selector} {{") + 400]
            assert "pointer-events: auto" in block, f"{selector} is unclickable"

    # ── the desktop app's chrome, ported into the HUD ───────────────────────

    def test_the_rail_has_every_module_the_desktop_app_had(self):
        index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        assert 'id="sidebar-nav"' in index
        for module in ("chat", "voice", "commands", "vision", "files",
                       "tools", "memory", "settings"):
            assert f'data-nav="{module}"' in index, f"the {module} module is gone"

    def test_a_module_that_cannot_work_says_so(self):
        """The rail must not imply a module exists when it does not."""
        index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        assert "inert" in index, "no module is marked as unwired"
        script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        assert "not wired up" in script, "an unwired module fails silently"

    def test_the_state_strip_shows_the_five_states(self):
        index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        assert 'id="state-strip"' in index
        for state in ("READY", "LISTENING", "THINKING", "EXECUTING", "SPEAKING"):
            assert f'data-state="{state}"' in index, f"the {state} state is missing"

    def test_the_media_bar_and_clock_are_present(self):
        index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        for transport in ("previous track", "play pause", "next track"):
            assert f'data-command="{transport}"' in index, f"no {transport} button"
        assert 'id="clock"' in index and 'id="date"' in index
        assert 'id="waveform"' in index, "the voice activity line is gone"

    def test_the_ported_controls_actually_do_something(self):
        """Every ported control is wired: none may be decoration."""
        script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        for hook in ("sidebar-nav", "dataset.nav", "[data-command]", "WAVE_STRENGTH",
                     "tickClock", "stateStrip"):
            assert hook in script, f"app.js never handles {hook}"


class TestUiCommandsReachTheAgent:
    """The HUD's buttons must send phrases KIRA's parser understands.

    A button that posts an unknown phrase is a lie in the interface, so the
    markup is cross-checked against the real parser instead of trusted.
    """

    KNOWN = ["open chrome", "systems check", "what did you learn",
             "previous track", "play pause", "next track"]

    def test_every_known_button_phrase_parses(self, backend):
        for phrase in self.KNOWN:
            assert backend.parse_simple_command(phrase), (
                f"'{phrase}' is in the interface but the parser does not know it"
            )

    def test_the_markup_only_offers_what_is_wired(self):
        """Every data-command in the markup is either known or listed here."""
        index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        offered = set(re.findall(r'data-command="([^"]+)"', index))
        # "what is on my screen" needs the vision pipeline, which no entry
        # point routes yet — it is knowingly unhandled, not accidentally.
        assert offered == set(self.KNOWN) | {"what is on my screen"}, (
            f"the interface offers commands nothing handles: "
            f"{offered - set(self.KNOWN) - {'what is on my screen'}}"
        )


class TestTheHudSpeaksTheSecurityContract:
    """The browser side of the guards, pinned against the server's rules."""

    def test_the_hud_sends_the_token_when_it_has_one(self):
        js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        assert "X-KIRA-Token" in js, "the HUD never sends the token"
        assert "kira.token" in js, "the token is not remembered between reloads"

    def test_the_hud_takes_the_token_out_of_the_address_bar(self):
        """A link with a token in it must not stay in the URL or the screen."""
        js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        assert "replaceState" in js
        assert 'params.delete("token")' in js

    def test_the_hud_echoes_the_confirmation_token(self):
        """The server refuses a bare confirm; the page must carry the nonce."""
        js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        assert "confirm_token" in js
        assert "confirmToken" in js

    def test_the_hud_goes_quiet_when_it_is_not_being_looked_at(self):
        js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        assert 'addEventListener("visibilitychange"' in js
        assert "if (document.hidden) return" in js

    def test_the_hud_honours_the_render_budget(self):
        """orb_quality is the user's answer to "make it lighter"."""
        js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        assert "qualitySettings" in js
        assert "setQuality" in js
        assert "bloomPass.enabled" in js, "the bloom pass is not part of the budget"
        for name in ("low", "balanced", "high"):
            assert f"{name}:" in js, f"no {name} budget"

    def test_the_hud_animates_from_elapsed_time(self):
        """Motion must not depend on the display's refresh rate."""
        js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        assert "HUD_MIN_FRAME_MS" in js, "the render loop is uncapped"
        assert "performance.now" in js or "timestamp" in js
        assert "0.9 ** frames" in js, "the trails fade by frame count"

    def test_the_harness_proves_the_render_loop_behaviour(self):
        """The loop's timing is checked by running it, in scripts/check_ui.mjs."""
        harness = (ROOT / "scripts" / "check_ui.mjs").read_text(encoding="utf-8")
        for name in (
            "the rain falls at the same speed on any display",
            "the rain falls at 60 frames' worth per second, whatever the rate",
            "a fast display does not do more work",
            "a hidden window stops drawing and stops polling",
            "orb_quality lowers the render budget",
        ):
            assert name in harness, f"the harness never checks: {name}"


class TestVendoredThree:
    """The reactor must not depend on a CDN — KIRA is a local-first agent."""

    def test_no_external_urls_are_referenced(self):
        for name in ("index.html", "app.js", "style.css"):
            text = (ROOT / "ui" / name).read_text(encoding="utf-8")
            for url in re.findall(r"https?://[^\s\"'<>)]+", text):
                assert "localhost" in url or "127.0.0.1" in url, (
                    f"ui/{name} reaches out to {url}"
                )

    def test_the_import_map_points_at_files_that_exist(self):
        index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        mapping = json.loads(
            re.search(r'<script type="importmap">\s*(\{.*?\})\s*</script>', index, re.S).group(1)
        )
        assert mapping["imports"]["three"].startswith("./")
        target = ROOT / "ui" / mapping["imports"]["three"].lstrip("./")
        assert target.is_file(), f"import map points at a missing file: {target}"
        addons = ROOT / "ui" / mapping["imports"]["three/addons/"].lstrip("./")
        assert addons.is_dir(), "the addons directory is missing"

    def test_the_license_ships_with_the_vendored_code(self):
        vendor = ROOT / "ui" / "vendor"
        assert "MIT" in (vendor / "LICENSE").read_text(encoding="utf-8")
        banner = (vendor / "three.module.min.js").read_text(
            encoding="utf-8", errors="replace"
        )[:400]
        assert "Three.js Authors" in banner
        assert "MIT" in banner

    def test_every_imported_module_is_present(self):
        """Walks the vendor tree: no import may point at a file we forgot."""
        vendor = ROOT / "ui" / "vendor"
        addons = [path for path in vendor.rglob("*.js") if not path.name.endswith(".min.js")]
        assert len(addons) >= 8, f"only found {len(addons)} vendored addons"

        for module in addons:
            source = module.read_text(encoding="utf-8", errors="replace")
            # ignore JSDoc examples, which advertise the `three/addons/…` path
            code = "\n".join(
                line
                for line in source.splitlines()
                if not line.lstrip().startswith(("*", "//"))
            )
            for specifier in re.findall(r"""from\s*["']([^"']+)["']""", code):
                if specifier == "three":
                    continue  # satisfied by the import map
                assert specifier.startswith("."), (
                    f"{module.name} imports the bare specifier {specifier!r}, "
                    "which would need a CDN"
                )
                target = (module.parent / specifier).resolve()
                assert target.is_file(), f"{module.name} imports missing {specifier}"
                assert vendor in target.parents, f"{module.name} escapes the vendor tree"

    def test_the_core_build_is_split_like_upstream_ships_it(self):
        """three.module.min.js re-exports ./three.core.min.js — both must ship."""
        module = (ROOT / "ui" / "vendor" / "three.module.min.js").read_text(
            encoding="utf-8", errors="replace"
        )
        assert 'from"./three.core.min.js"' in module
        assert (ROOT / "ui" / "vendor" / "three.core.min.js").is_file()

    def test_the_postprocessing_chain_used_by_app_js_is_vendored(self):
        for relative in (
            "jsm/postprocessing/EffectComposer.js",
            "jsm/postprocessing/RenderPass.js",
            "jsm/postprocessing/UnrealBloomPass.js",
            "jsm/postprocessing/ShaderPass.js",
            "jsm/postprocessing/Pass.js",
            "jsm/postprocessing/MaskPass.js",
            "jsm/shaders/CopyShader.js",
            "jsm/shaders/LuminosityHighPassShader.js",
        ):
            assert (ROOT / "ui" / "vendor" / relative).is_file(), relative

    def test_app_js_degrades_instead_of_breaking(self):
        """Building the scene must sit inside a try/catch, not just the import."""
        script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        assert 'await import("three")' in script
        wrapper = re.search(
            r"async function startReactor\(\)\s*\{\s*try\s*\{\s*await buildReactor\(\);",
            script,
        )
        assert wrapper, "startReactor() no longer guards buildReactor()"
        handler = script[wrapper.end() : wrapper.end() + 600]
        assert "catch" in handler, "the guard swallows nothing"
        assert 'classList.add("no-webgl")' in handler, "no CSS fallback"
        assert "console.info" in handler, "the degradation is silent"


class TestCliEntry:
    def test_missing_ui_is_reported(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(kira_server, "UI_DIR", tmp_path / "absent")
        assert kira_server.main([]) == 2
        assert "missing" in capsys.readouterr().err

    def test_help_lists_the_flags(self, capsys):
        with pytest.raises(SystemExit):
            kira_server.main(["--help"])
        out = capsys.readouterr().out
        for flag in ("--host", "--port", "--simulate", "--open", "--no-watchdog"):
            assert flag in out

    def test_default_port_is_not_a_common_service(self):
        assert 1024 < kira_server.DEFAULT_PORT < 65535
        assert kira_server.DEFAULT_HOST == "127.0.0.1"  # local-first by default

    def test_local_addresses_always_include_loopback(self):
        assert kira_server.local_addresses(9999)[0] == "http://127.0.0.1:9999"
