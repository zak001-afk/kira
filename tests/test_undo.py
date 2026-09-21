"""'Take that back': inverse mapping, stack behavior, executor integration."""
import sys

import kira_undo


class TestInverseMap:
    def test_type_maps_to_ctrl_z(self):
        assert kira_undo.inverse_for({"action": "type", "text": "hello"}) == {
            "action": "press_combo",
            "keys": ["ctrl", "z"],
        }

    def test_toggles_are_symmetric(self):
        for name in ("mute", "show_desktop", "media_play_pause"):
            assert kira_undo.inverse_for({"action": name}) == {"action": name}

    def test_mirrored_actions(self):
        assert kira_undo.inverse_for({"action": "volume_up"}) == {
            "action": "volume_down"
        }
        assert kira_undo.inverse_for({"action": "media_next"}) == {
            "action": "media_previous"
        }

    def test_irreversible_actions_map_to_none(self):
        for name in ("open_app", "click", "lock_pc", "screenshot", "none"):
            assert kira_undo.inverse_for({"action": name}) is None
        assert kira_undo.inverse_for(None) is None
        assert kira_undo.inverse_for({}) is None


class TestStack:
    def setup_method(self):
        kira_undo.clear()

    def teardown_method(self):
        kira_undo.clear()

    def test_record_only_stores_reversible(self):
        kira_undo.record("open chrome", {"action": "open_app"})
        assert kira_undo.last() is None
        kira_undo.record("mute", {"action": "mute"})
        assert kira_undo.last() == {
            "command": "mute",
            "inverse": {"action": "mute"},
        }

    def test_take_last_pops(self):
        kira_undo.record("mute", {"action": "mute"})
        entry = kira_undo.take_last()
        assert entry["command"] == "mute"
        assert kira_undo.take_last() is None

    def test_stack_is_capped(self):
        for i in range(15):
            kira_undo.record(f"volume {i}", {"action": "volume_up"})
        entries = kira_undo._stack.entries
        assert len(entries) == 10
        assert entries[-1]["command"] == "volume 14"


class TestExecutor:
    def test_undo_type_sends_ctrl_z(self, backend, speak_silenced):
        assert backend.execute_action({"action": "type", "text": "hello"})
        backend.kira_undo.record("type hello", {"action": "type", "text": "hello"})
        reply = backend.execute_action({"action": "undo_last", "language": "en"})
        assert "undone" in reply
        hotkeys = [
            call for call in sys.modules["pyautogui"].calls if call[0] == "hotkey"
        ]
        assert any(tuple(call[1]) == ("ctrl", "z") for call in hotkeys)

    def test_undo_nothing_replies_empty(self, backend, speak_silenced):
        reply = backend.execute_action({"action": "undo_last", "language": "en"})
        assert "nothing" in reply.lower()

    def test_undo_toggle_is_re_recorded_for_symmetry(self, backend, speak_silenced):
        backend.kira_undo.record("mute the mic", {"action": "mute"})
        backend.execute_action({"action": "undo_last", "language": "en"})
        # a symmetric undo re-enters the stack so a second undo restores it
        assert backend.kira_undo.last() is not None

    def test_press_combo_executes(self, backend, speak_silenced):
        reply = backend.execute_action(
            {"action": "press_combo", "keys": ["ctrl", "z"]}
        )
        assert "ctrl+z" in reply
        hotkeys = [
            call for call in sys.modules["pyautogui"].calls if call[0] == "hotkey"
        ]
        assert any(tuple(call[1]) == ("ctrl", "z") for call in hotkeys)

    def test_press_combo_without_keys_fails(self, backend, speak_silenced):
        assert backend.execute_action({"action": "press_combo", "keys": []}) is False
