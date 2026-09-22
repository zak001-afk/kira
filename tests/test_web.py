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


class TestSessionControls:
    """These actions bypass execute_action on the desktop, so the server has
    to answer them itself — otherwise the browser reports a failure."""

    def test_conversation_mode_toggles_the_backend_flag(self):
        service, backend = service_with_backend(
            simple_result={"action": "conversation_on"},
            confirm_actions=set(),
        )
        backend._CONVERSATION_MODE = False
        result = service.handle_command("conversation mode on")
        assert result["ok"] is True
        assert backend._CONVERSATION_MODE is True
        assert "on" in result["reply"].lower()
        assert backend.executed == [], "a session control went to execute_action"

        backend.simple_result = {"action": "conversation_off"}
        service.handle_command("conversation mode off")
        assert backend._CONVERSATION_MODE is False

    def test_chat_reset_starts_a_new_session(self):
        service, backend = service_with_backend(
            simple_result={"action": "chat_reset"},
            confirm_actions=set(),
        )
        backend.reset_chat = lambda: backend.__setattr__("reset_called", True)
        result = service.handle_command("start a new chat")
        assert result["ok"] is True
        assert backend.reset_called is True

    def test_mode_info_answers_plainly(self):
        service, backend = service_with_backend(
            simple_result={"action": "mode_info"},
            confirm_actions=set(),
        )
        assert service.handle_command("what mode are you in")["reply"]
        assert backend.executed == []

    def test_goodbye_does_not_stop_the_server(self):
        """The desktop app quits on 'exit' — a web server must not."""
        service, backend = service_with_backend(
            simple_result={"action": "exit"},
            confirm_actions=set(),
        )
        result = service.handle_command("goodbye")
        assert "goodbye" in result["reply"].lower()
        assert backend.executed == []


class TestReplyBuilding:
    def test_an_empty_string_result_is_a_failure_not_a_silence(self):
        """execute_action() returning "" used to produce no reply at all."""
        service, _ = service_with_backend(
            simple_result={"action": "volume_up"},
            confirm_actions=set(),
            execute_result="",
        )
        result = service.handle_command("volume up")
        assert result["ok"] is False
        assert result["reply"], "the user was left with no answer at all"

    def test_action_targets_reach_the_reply(self):
        service, _ = service_with_backend(
            simple_result={"action": "search", "query": "weather in tunis"},
            confirm_actions=set(),
        )
        result = service.handle_command("search for the weather")
        assert "weather in tunis" in result["reply"]

    def test_folder_and_press_targets_are_passed_through(self):
        service, _ = service_with_backend(
            simple_result={"action": "press", "target": "enter"},
            confirm_actions=set(),
        )
        assert "enter" in service.handle_command("press enter")["reply"]


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
        service.handle_command("open chrome")
        result = service.handle_command("", confirm=True)
        assert result["kind"] == "action"
        assert result["ok"] is True
        assert backend.executed == [{"action": "open_app", "target": "chrome"}]
        assert service.state == "READY"

    def test_a_pending_action_only_fires_once(self):
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
        )
        service.handle_command("open chrome")
        service.handle_command("", confirm=True)
        # a second confirm has nothing pending and must not re-run anything
        service.handle_command("", confirm=True)
        assert len(backend.executed) == 1

    def test_confirm_without_pending_is_harmless(self):
        service, backend = service_with_backend()
        result = service.handle_command("", confirm=True)
        assert result["kind"] == "empty"
        assert backend.executed == []

    def test_cancelling_disarms_the_action_for_good(self):
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
        )
        service.handle_command("open chrome")
        cancelled = service.handle_command("", cancel=True)
        assert cancelled["kind"] == "cancelled"
        assert service._pending is None
        assert backend.executed == []

        # a stray CONFIRM afterwards must do nothing at all
        assert service.handle_command("", confirm=True)["kind"] == "empty"
        assert backend.executed == [], "a cancelled action still ran"

    def test_cancelling_with_nothing_pending_is_harmless(self):
        service, backend = service_with_backend()
        result = service.handle_command("", cancel=True)
        assert result["kind"] == "empty"
        assert backend.executed == []

    def test_ignoring_the_question_cancels_it(self):
        """Moving on must not leave a loaded CONFIRM button behind."""
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
        )
        service.handle_command("open chrome")
        assert service._pending is not None

        # the user typed something else instead of answering
        backend.simple_result = {"action": "volume_up"}
        service.handle_command("volume up")
        assert service._pending is None, "the old question was still armed"

        # a late CONFIRM click must do nothing at all
        result = service.handle_command("", confirm=True)
        assert result["kind"] == "empty"
        assert backend.executed == [{"action": "volume_up"}], (
            "a stale confirmation executed a command the user had abandoned"
        )

    def test_the_new_command_becomes_the_pending_one(self):
        service, backend = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
        )
        service.handle_command("open chrome")
        backend.simple_result = {"action": "open_app", "target": "vscode"}
        service.handle_command("open vscode")
        service.handle_command("", confirm=True)
        assert backend.executed == [{"action": "open_app", "target": "vscode"}]

    def test_llm_plans_are_confirmed_too(self):
        """The whitelist holds sensitive actions; whoever planned it, ask."""
        service, backend = service_with_backend(
            simple_result=None,
            think_result=FakeClock(
                {"action": "open_app", "target": "vscode"},
                source="llm",
                text="The user means the code editor.",
            ),
        )
        result = service.handle_command("open my editor")
        assert result["needs_confirmation"] is True
        assert backend.executed == [], "a model-planned action ran without asking"

        done = service.handle_command("", confirm=True)
        assert done["ok"] is True
        assert backend.executed == [{"action": "open_app", "target": "vscode"}]
        assert done["thought"] == "The user means the code editor.", (
            "the thought was lost across the confirmation"
        )

    def test_llm_plans_without_a_confirmation_rule_still_run(self):
        service, backend = service_with_backend(
            simple_result=None,
            think_result=FakeClock({"action": "volume_up"}, source="llm"),
            confirm_actions=set(),
        )
        result = service.handle_command("louder")
        assert "needs_confirmation" not in result
        assert backend.executed == [{"action": "volume_up"}]


class TestHistory:
    def test_both_sides_are_recorded(self):
        """A reload must restore the user's half of the conversation too."""
        service, _ = service_with_backend(
            simple_result={"action": "volume_up"},
            confirm_actions=set(),
        )
        service.handle_command("volume up")
        messages = service.history(10)
        assert [message["role"] for message in messages] == ["you", "kira"]
        assert messages[0]["text"] == "volume up"
        assert messages[1]["text"] == "Done: volume_up"
        assert messages[1]["kind"] == "action"

    def test_failed_commands_are_recorded(self):
        service, _ = service_with_backend(simple_result={"action": "none"})
        service.handle_command("do something impossible")
        roles = [message["role"] for message in service.history(10)]
        assert roles == ["you", "kira"]

    def test_empty_commands_are_not_recorded(self):
        service, _ = service_with_backend()
        service.handle_command("   ")
        assert service.history(10) == []

    def test_a_confirmation_does_not_duplicate_the_user_line(self):
        service, _ = service_with_backend(
            simple_result={"action": "open_app", "target": "chrome"},
        )
        service.handle_command("open chrome")
        service.handle_command("", confirm=True)
        roles = [message["role"] for message in service.history(10)]
        assert roles == ["you", "kira", "kira"], roles

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


class TestFaultState:
    """The HUD renders FAULT from an ERROR state — something must produce it."""

    def test_a_failure_raises_the_fault_state(self):
        service = kira_server.KiraService(simulate=False)
        service.backend = None
        service.reason = "no backend"
        service.handle_command("open chrome")
        assert service.state == "ERROR"
        assert service.telemetry()["state"] == "ERROR"

    def test_the_fault_state_clears_by_itself(self):
        service = kira_server.KiraService(simulate=False)
        service.backend = None
        service.reason = "no backend"
        service.handle_command("open chrome")
        service._error_until = 0  # as if the linger window had passed
        assert service.telemetry()["state"] == "READY"
        assert service.state == "READY"

    def test_success_leaves_no_fault_behind(self):
        service, _ = service_with_backend(
            simple_result={"action": "volume_up"},
            confirm_actions=set(),
        )
        service.handle_command("volume up")
        assert service.telemetry()["state"] == "READY"

    def test_an_action_failure_is_not_a_fault(self):
        """A command that ran and failed is KIRA's business, not a HUD fault."""
        service, _ = service_with_backend(
            simple_result={"action": "open_app", "target": "ghost"},
            confirm_actions=set(),
            execute_result=False,
        )
        service.handle_command("open ghost")
        assert service.telemetry()["state"] == "READY"


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


# ── the real backend, not a fake ─────────────────────────────────────────────


class TestBackendContract:
    """The fakes above model the backend; these tests hold it to the model.

    `tests/conftest.py` stubs the hardware, so the real `kira_voice_agent`
    imports fine here. If the agent renames or drops anything the server
    calls, this fails instead of the browser quietly breaking.
    """

    def test_every_backend_attribute_the_server_calls_exists(self):
        source = (ROOT / "kira_server.py").read_text(encoding="utf-8")
        wanted = {
            name
            for name in re.findall(r"\bbackend\.([A-Za-z_][A-Za-z0-9_]*)", source)
            if name not in {"py", "exc"}  # locals, not backend attributes
        }
        assert len(wanted) >= 15, f"only found {wanted} — did the server change shape?"

        import kira_voice_agent as backend

        missing = sorted(name for name in wanted if not hasattr(backend, name))
        assert missing == [], f"kira_server.py calls attributes the backend lacks: {missing}"

    def test_every_telemetry_reader_exists(self):
        import kira_voice_agent as backend

        for name in ("VERSION", "MODEL", "CONFIG", "USER_MEMORY"):
            assert hasattr(backend, name), f"the backend lost {name}"

        for name in ("learnings_summary", "episode_counts", "load_memories"):
            assert callable(getattr(backend.kira_memory, name, None)), name

        summarised = backend.kira_memory.learnings_summary()
        counted = backend.kira_memory.episode_counts()
        assert isinstance(summarised.get("count"), int)
        assert isinstance(counted.get("total"), int)


class TestRealBackendPipeline:
    """One command end to end through the actual agent, with only the
    hardware-touching executor replaced."""

    def _service(self, monkeypatch, reply="Done, sir."):
        import kira_voice_agent as backend

        service = kira_server.KiraService(simulate=False)
        service.backend = backend
        service.reason = ""
        executed = []

        def fake_execute(action):
            executed.append(action)
            return reply

        monkeypatch.setattr(backend, "execute_action", fake_execute)
        return service, executed

    def test_a_parsed_command_runs_without_the_model(self, monkeypatch):
        service, executed = self._service(monkeypatch)
        result = service.handle_command("volume up")
        assert executed == [{"action": "volume_up"}]
        assert result["action"] == "volume_up"
        assert result["ok"] is True
        assert result["reply"] == "Done, sir."
        assert result["mode"] == "live"

    def test_a_sensitive_action_is_held_for_the_page(self, monkeypatch):
        service, executed = self._service(monkeypatch)
        pending = service.handle_command("search for a restaurant")
        assert pending["needs_confirmation"] is True
        assert pending["action_name"] == "search"
        assert executed == [], "a sensitive action ran before confirmation"

        done = service.handle_command("", confirm=True)
        assert [action["action"] for action in executed] == ["search"]
        assert done["ok"] is True

    def test_history_round_trips_through_a_real_command(self, monkeypatch):
        service, _ = self._service(monkeypatch)
        service.handle_command("volume up")
        messages = service.history(10)
        assert [message["role"] for message in messages] == ["you", "kira"]
        assert messages[0]["text"] == "volume up"

    def test_telemetry_reports_the_real_agent(self, monkeypatch):
        service, _ = self._service(monkeypatch)
        data = service.telemetry()
        assert data["online"] is True
        assert data["mode"] == "live"
        assert data["model"] == getattr(service.backend, "MODEL")
        assert isinstance(data["skills"], int)
        assert data["version"] == service.backend.VERSION


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


def request(web, method: str, path: str, payload=None) -> tuple:
    """Returns (status, headers, body-bytes)."""
    connection = http.client.HTTPConnection(web.host, web.port, timeout=5)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def request_json(web, method: str, path: str, payload=None) -> tuple:
    status, headers, body = request(web, method, path, payload)
    return status, json.loads(body.decode("utf-8") or "null")


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

        _, done = request_json(
            web, "POST", "/api/command", {"text": "", "confirm": True}
        )
        assert done["ok"] is True
        assert web.backend.executed == [{"action": "open_app", "target": "chrome"}]

    def test_cancel_endpoint_disarms_without_running(self, web):
        web.backend.simple_result = {"action": "open_app", "target": "chrome"}
        web.backend.confirm_actions = {"open_app"}
        request_json(web, "POST", "/api/command", {"text": "open chrome"})

        _, cancelled = request_json(web, "POST", "/api/command", {"cancel": True})
        assert cancelled["kind"] == "cancelled"
        assert web.backend.executed == []

        _, late = request_json(web, "POST", "/api/command", {"confirm": True})
        assert late["kind"] == "empty"
        assert web.backend.executed == []

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
        assert headers.get("X-Content-Type-Options") == "nosniff"


class TestBrowserIsolation:
    """KIRA's API can drive the machine, so a foreign page must not reach it.

    The interface is served from this origin, so it needs no CORS headers —
    and handing out `Access-Control-Allow-Origin: *` would let any website the
    user visits talk to their local agent.
    """

    def test_no_wildcard_cors_is_ever_sent(self, web):
        for method, path in (("GET", "/"), ("GET", "/api/state"), ("GET", "/api/health")):
            _, headers, _ = request(web, method, path)
            assert "Access-Control-Allow-Origin" not in headers, (
                f"{method} {path} handed out CORS access"
            )

    def test_preflight_does_not_grant_cross_origin_access(self, web):
        status, headers, _ = request(web, "OPTIONS", "/api/command")
        assert status == 204
        assert "Access-Control-Allow-Origin" not in headers
        assert "Access-Control-Allow-Methods" not in headers

    def test_a_form_style_post_cannot_run_a_command(self, web):
        """text/plain/form bodies skip preflight in browsers — refuse them."""
        connection = http.client.HTTPConnection(web.host, web.port, timeout=5)
        try:
            body = json.dumps({"text": "open chrome", "confirm": True})
            for content_type in (
                "text/plain",
                "application/x-www-form-urlencoded",
                "multipart/form-data; boundary=x",
                None,
            ):
                headers = {"Content-Type": content_type} if content_type else {}
                connection.request("POST", "/api/command", body=body, headers=headers)
                response = connection.getresponse()
                payload = json.loads(response.read())
                assert response.status == 200
                assert payload["kind"] == "empty", (
                    f"{content_type!r} body was treated as a command"
                )
        finally:
            connection.close()
        assert web.backend.executed == [], "a cross-origin-style POST executed an action"

    def test_json_posts_still_work(self, web):
        status, data = request_json(web, "POST", "/api/command", {"text": "volume up"})
        assert (status, data["ok"]) == (200, True)

    def test_an_oversized_body_is_refused_and_the_socket_closed(self, web):
        connection = http.client.HTTPConnection(web.host, web.port, timeout=5)
        try:
            connection.request(
                "POST",
                "/api/command",
                body=b"x" * (kira_server.MAX_BODY_BYTES + 10),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            assert json.loads(response.read())["kind"] == "empty"
        finally:
            connection.close()
        assert web.backend.executed == []


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
        for selector in (".status-cluster", ".command-box", ".quick-actions", ".confirm-bar"):
            block = css[css.index(f"{selector} {{"): css.index(f"{selector} {{") + 400]
            assert "pointer-events: auto" in block, f"{selector} is unclickable"


class TestVendoredThree:
    """The reactor must not depend on a CDN — KIRA is a local-first agent."""

    def test_no_external_urls_are_referenced(self):
        """Nothing in the page may need the network — KIRA is local-first.

        Data URIs are stripped first: they are inline content, and the SVG
        namespace inside one (`http://www.w3.org/2000/svg`) is an identifier,
        not a fetch.
        """
        # XML namespace identifiers look like URLs but are never fetched
        namespaces = {
            "http://www.w3.org/2000/svg",
            "http://www.w3.org/1999/xhtml",
            "http://www.w3.org/1999/xlink",
        }
        for name in ("index.html", "app.js", "style.css"):
            text = (ROOT / "ui" / name).read_text(encoding="utf-8")
            for url in re.findall(r"https?://[^\s\"'<>)]+", text):
                if url in namespaces:
                    continue
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

    def test_loopback_binding_does_not_advertise_lan_urls(self):
        """Printing a LAN URL for a 127.0.0.1 server sends people nowhere."""
        assert kira_server.local_addresses(9999, "127.0.0.1") == [
            "http://127.0.0.1:9999"
        ]
        assert len(kira_server.local_addresses(9999, "0.0.0.0")) >= 1
