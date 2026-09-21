"""Voice lock + passphrase, privacy blur, and the locked-lab command gate."""
import sys

import kira_security


def _gui_calls():
    return sys.modules["pyautogui"].calls


class TestUnlockExtraction:
    def test_plain_unlock(self):
        assert kira_security.extract_unlock("unlock the lab") == "unlock"
        assert kira_security.extract_unlock("unlock the lab", "arcreactor") == "deny"
        assert (
            kira_security.extract_unlock("unlock the lab arcreactor", "arcreactor")
            == "unlock"
        )

    def test_french_and_arabic_commands(self):
        assert kira_security.extract_unlock("déverrouille le labo") == "unlock"
        assert kira_security.extract_unlock("افتح المختبر") == "unlock"
        assert (
            kira_security.extract_unlock("افتح المختبر سري", "سري") == "unlock"
        )
        assert kira_security.extract_unlock("افتح المختبر غلط", "سري") == "deny"

    def test_unrelated_commands_are_not_unlocks(self):
        for text in ("secure the lab", "open chrome", "what time is it", ""):
            assert kira_security.extract_unlock(text) is None

    def test_passphrase_requires_something_offered(self):
        assert kira_security.extract_unlock("unlock the lab", "root") == "deny"


class TestLockStateAndReplies:
    def setup_method(self):
        kira_security.unlock()

    def teardown_method(self):
        kira_security.unlock()

    def test_lock_cycle(self):
        assert not kira_security.is_locked()
        kira_security.lock()
        assert kira_security.is_locked()
        kira_security.unlock()
        assert not kira_security.is_locked()

    def test_replies_are_localized(self):
        for language in ("en", "fr", "ar"):
            assert kira_security.lock_reply(language)
            assert kira_security.unlock_reply(language)
            assert kira_security.deny_reply(language)
            assert kira_security.blur_reply(language)
            assert kira_security.locked_notice(language)


class TestBackendGate:
    def test_gate_is_open_when_unlocked(self, backend):
        assert backend.lab_gate("open chrome") is None

    def test_gate_blocks_everything_not_unlock(self, backend, speak_silenced):
        backend.kira_security.lock()
        reply = backend.lab_gate("open chrome")
        assert "secured" in reply or "verrouillé" in reply or "مؤمّن" in reply
        assert backend.kira_security.is_locked()

    def test_gate_unlocks_on_phrase(self, backend, speak_silenced):
        backend.kira_security.lock()
        reply = backend.lab_gate("unlock the lab")
        assert not backend.kira_security.is_locked()
        assert "Welcome back" in reply

    def test_gate_denies_wrong_passphrase(self, backend, speak_silenced, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "lab_passphrase", "jarvis")
        backend.kira_security.lock()
        reply = backend.lab_gate("unlock the lab vision")
        assert "does not match" in reply
        assert backend.kira_security.is_locked()

    def test_gate_accepts_right_passphrase(self, backend, speak_silenced, monkeypatch):
        monkeypatch.setitem(backend.CONFIG, "lab_passphrase", "jarvis")
        backend.kira_security.lock()
        backend.lab_gate("unlock the lab jarvis")
        assert not backend.kira_security.is_locked()

    def test_secure_and_unlock_lab_execution(self, backend, speak_silenced):
        reply = backend.execute_action({"action": "secure_lab", "language": "en"})
        assert "secured" in reply
        assert backend.kira_security.is_locked()

        reply = backend.execute_action({"action": "unlock_lab", "language": "en"})
        assert "Welcome back" in reply
        assert not backend.kira_security.is_locked()

    def test_unlock_when_not_locked(self, backend, speak_silenced):
        reply = backend.execute_action({"action": "unlock_lab", "language": "en"})
        assert "isn't locked" in reply

    def test_privacy_blur_triggers_desktop_and_mute(self, backend, speak_silenced):
        reply = backend.execute_action({"action": "privacy_blur", "language": "en"})
        assert "Privacy mode" in reply
        hotkeys = [call for call in _gui_calls() if call[0] == "hotkey"]
        assert any(set(call[1]) == {"win", "d"} for call in hotkeys)  # show desktop
        presses = [call for call in _gui_calls() if call[0] == "press"]
        assert any("volumemute" in str(call) for call in presses)

    def test_denied_verdict_speaks_deny(self, backend, speak_silenced):
        backend.kira_security.lock()
        reply = backend.execute_action(
            {"action": "unlock_lab", "verdict": "deny", "language": "en"}
        )
        assert "does not match" in reply
        assert backend.kira_security.is_locked()
