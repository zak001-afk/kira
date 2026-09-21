"""Teach-a-trick learning: macro recording, corrections, skill promotion."""
import json
import sys

import pytest

import kira_learning


class TestRecording:
    def test_start_and_cancel(self, backend):
        kira_learning.start_recording()
        assert kira_learning.is_recording()
        kira_learning.capture({"action": "open_app", "target": "vscode"})
        kira_learning.capture({"action": "press", "target": "f5"})
        assert len(kira_learning.recorded_steps()) == 2
        assert kira_learning.cancel_recording() == 2
        assert not kira_learning.is_recording()
        assert kira_learning.recorded_steps() == []

    def test_capture_skips_meta_actions(self, backend):
        kira_learning.start_recording()
        kira_learning.capture({"action": "routine_start"})
        kira_learning.capture({"action": "skill_promote"})
        kira_learning.capture({"action": "correct_last"})
        kira_learning.capture(None)
        kira_learning.capture({"action": "open_app", "target": "chrome"})
        steps = kira_learning.recorded_steps()
        assert steps == [{"action": "open_app", "target": "chrome"}]

    def test_capture_does_nothing_when_idle(self, backend):
        kira_learning.capture({"action": "open_app", "target": "chrome"})
        assert kira_learning.recorded_steps() == []

    def test_name_extraction(self):
        assert kira_learning.extract_routine_name("call it deploy mode") == "deploy mode"
        assert kira_learning.extract_routine_name("name this morning setup") == (
            "morning setup"
        )
        assert kira_learning.extract_routine_name("appelle-la démo") == "démo"
        assert kira_learning.extract_routine_name("سمها وضع العمل") == "وضع العمل"
        assert kira_learning.extract_routine_name("open chrome") is None


class TestVoiceFlow:
    def test_routine_start_and_stop_commands(self, backend, speak_silenced):
        reply = backend.execute_action({"action": "routine_start", "language": "en"})
        assert "listening to learn" in reply
        reply = backend.execute_action({"action": "routine_start", "language": "en"})
        assert "already recording" in reply
        reply = backend.execute_action({"action": "routine_stop", "language": "en"})
        assert "discarded" in reply
        reply = backend.execute_action({"action": "routine_stop", "language": "en"})
        assert "not recording" in reply

    def test_full_recording_saves_a_shortcut(
        self, backend, speak_silenced, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(backend, "CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.setitem(backend.CONFIG, "shortcuts", dict(backend.CONFIG["shortcuts"]))
        backend.execute_action({"action": "routine_start", "language": "en"})
        kira_learning.capture({"action": "open_app", "target": "vscode"})
        kira_learning.capture({"action": "type", "text": "npm test"})
        reply = backend.execute_action(
            {"action": "routine_name", "name": "test mode", "language": "en"}
        )
        assert "test mode" in reply and "2 steps" in reply
        assert backend.CONFIG["shortcuts"]["test mode"] == [
            {"action": "open_app", "target": "vscode"},
            {"action": "type", "text": "npm test"},
        ]
        saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert saved["shortcuts"]["test mode"][1]["text"] == "npm test"

    def test_naming_without_steps_cancels(self, backend, speak_silenced):
        backend.execute_action({"action": "routine_start", "language": "en"})
        reply = backend.execute_action(
            {"action": "routine_name", "name": "empty", "language": "en"}
        )
        assert "nothing to save" in reply
        assert not kira_learning.is_recording()

    def test_naming_without_recording(self, backend, speak_silenced):
        reply = backend.execute_action(
            {"action": "routine_name", "name": "x", "language": "en"}
        )
        assert "not recording" in reply


class TestCorrections:
    def test_correction_demotes_the_last_learning(self, backend, memory_db, speak_silenced):
        action = {"action": "open_app", "target": "vscode"}
        backend.kira_memory.learn_from_outcome("launch the editor", action, True)
        backend._LAST_COMMAND = "launch the editor"
        backend._LAST_ACTION = action
        reply = backend.execute_action({"action": "correct_last", "language": "en"})
        assert "marked that as a mistake" in reply
        learning = backend.kira_memory.recall_action("launch the editor")
        # one failure against one success → ineligible (reflexion)
        assert learning is None

    def test_correction_without_history(self, backend, speak_silenced):
        reply = backend.execute_action({"action": "correct_last", "language": "en"})
        assert "nothing recent to correct" in reply

    def test_correction_cannot_be_repeated(self, backend, memory_db, speak_silenced):
        backend._LAST_COMMAND = "do the thing"
        backend._LAST_ACTION = {"action": "mute"}
        backend.execute_action({"action": "correct_last", "language": "en"})
        reply = backend.execute_action({"action": "correct_last", "language": "en"})
        assert "nothing recent to correct" in reply


class TestSkillPromotion:
    def _seed(self, backend, memory_db, command, action, successes):
        for _ in range(successes):
            backend.kira_memory.learn_from_outcome(command, action, True)

    def test_offer_appears_at_threshold(self, backend, memory_db, speak_silenced):
        action = {"action": "mute"}
        self._seed(backend, memory_db, "quiet the room", action, 9)
        assert kira_learning.pending_promotion() is None
        note = backend.learn_from("quiet the room", action, "memory", True)
        assert note and "permanent shortcut" in note
        assert kira_learning.pending_promotion()["command"] == "quiet the room"

    def test_offer_only_offered_once(self, backend, memory_db, speak_silenced):
        action = {"action": "mute"}
        self._seed(backend, memory_db, "hush", action, 10)
        # already at threshold → no new offer (10 != 11)
        assert backend.learn_from("hush", action, "memory", True) is None

    def test_promote_persists_shortcut(
        self, backend, memory_db, speak_silenced, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(backend, "CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.setitem(backend.CONFIG, "shortcuts", dict(backend.CONFIG["shortcuts"]))
        action = {"action": "mute"}
        self._seed(backend, memory_db, "hush the room", action, 9)
        backend.learn_from("hush the room", action, "memory", True)
        reply = backend.execute_action({"action": "skill_promote", "language": "en"})
        assert "permanent shortcut" in reply
        assert backend.CONFIG["shortcuts"]["hush the room"] == [action]
        assert kira_learning.pending_promotion() is None
        saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert "hush the room" in saved["shortcuts"]

    def test_promote_without_offer(self, backend, speak_silenced):
        reply = backend.execute_action({"action": "skill_promote", "language": "en"})
        assert "no shortcut offer" in reply

    def test_skip_clears_the_offer(self, backend, memory_db, speak_silenced):
        action = {"action": "mute"}
        self._seed(backend, memory_db, "hush", action, 10)
        kira_learning.check_promotion("hush", {"action": action, "success_count": 10})
        reply = backend.execute_action({"action": "skill_skip", "language": "en"})
        assert "not permanent" in reply
        assert kira_learning.pending_promotion() is None

    def test_skip_without_offer(self, backend, speak_silenced):
        reply = backend.execute_action({"action": "skill_skip", "language": "en"})
        assert "no shortcut offer" in reply

    def test_promotion_threshold_is_configurable(
        self, backend, memory_db, speak_silenced, monkeypatch
    ):
        monkeypatch.setitem(backend.CONFIG, "skill_promote_after", 2)
        action = {"action": "volume_up"}
        self._seed(backend, memory_db, "louder", action, 1)
        note = backend.learn_from("louder", action, "memory", True, language="fr")
        assert note and "raccourci permanent" in note


class TestParserRouting:
    @pytest.mark.parametrize(
        ("phrase", "action"),
        [
            ("learn this routine", "routine_start"),
            ("watch and learn", "routine_start"),
            ("apprends cette routine", "routine_start"),
            ("stop learning", "routine_stop"),
            ("call it deploy mode", "routine_name"),
            ("no not that one", "correct_last"),
            ("that's wrong", "correct_last"),
            ("make it a shortcut", "skill_promote"),
            ("skip the shortcut", "skill_skip"),
        ],
    )
    def test_phrases_route(self, backend, phrase, action):
        parsed = backend.parse_simple_command(phrase)
        assert parsed and parsed["action"] == action

    def test_routine_name_is_extracted_by_parser(self, backend):
        parsed = backend.parse_simple_command("call it morning setup")
        assert parsed == {
            "action": "routine_name",
            "name": "morning setup",
            "language": "en",
        }
