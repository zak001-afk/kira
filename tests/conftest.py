"""Pytest fixtures and dependency stubs for the KIRA test suite.

KIRA targets a Windows desktop: microphones, speakers, a GUI, Ollama and
pyautogui are real machines/services. None of that exists in CI, so conftest
installs lightweight stubs into ``sys.modules`` *before* importing the backend.
The stubs are deterministic and record calls so tests can assert on them.

Importing this module never touches the developer's real files:
``kira_memory.DB_PATH`` is redirected to a temporary directory before
``kira_voice_agent`` is imported.
"""
from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _StubUnknownValueError(Exception):
    pass


class _StubRequestError(Exception):
    pass


class _FakePyautogui(types.ModuleType):
    def __init__(self):
        super().__init__("pyautogui")
        self.calls: list = []
        self.FAILSAFE = True

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def press(self, key, **kw):
        self._record("press", key, **kw)

    def hotkey(self, *keys, **kw):
        self._record("hotkey", *keys, **kw)

    def write(self, text, **kw):
        self._record("write", text, **kw)

    typewrite = write

    def click(self, *args, **kw):
        self._record("click", *args, **kw)

    def moveTo(self, x, y, **kw):
        self._record("moveTo", x, y, **kw)

    def size(self):
        return (1920, 1080)

    def screenshot(self, path=None, **kw):
        self._record("screenshot", path, **kw)
        if path:
            Path(path).write_bytes(b"png-stub")


class _FakePyperclip(types.ModuleType):
    def __init__(self):
        super().__init__("pyperclip")
        self.value = ""

    def paste(self):
        return self.value

    def copy(self, text):
        self.value = text


class _FakeSpeechEngine:
    def __init__(self):
        self.spoken: list = []
        self.props: dict = {}

    def say(self, text):
        self.spoken.append(text)

    def runAndWait(self):
        pass

    def setProperty(self, name, value):
        self.props[name] = value

    def getProperty(self, name):
        return self.props.get(name, [])


class _FakePyttsx3(types.ModuleType):
    def __init__(self):
        super().__init__("pyttsx3")
        self.engine = _FakeSpeechEngine()

    def init(self):
        return self.engine


class _FakePsutil(types.ModuleType):
    def __init__(self):
        super().__init__("psutil")
        self._vm = types.SimpleNamespace(percent=37.0)
        self._battery = types.SimpleNamespace(percent=91)

    def virtual_memory(self):
        return self._vm

    def sensors_battery(self):
        return self._battery

    def cpu_percent(self, interval=None):
        return 4.0


class _FakeSpeechRecognition(types.ModuleType):
    def __init__(self):
        super().__init__("speech_recognition")
        self.UnknownValueError = _StubUnknownValueError
        self.RequestError = _StubRequestError

        class Microphone:
            @staticmethod
            def list_microphone_names():
                return []

        class AudioData:
            def __init__(self, frame_data, sample_rate, sample_width):
                self.frame_data = frame_data
                self.sample_rate = sample_rate
                self.sample_width = sample_width

        class Recognizer:
            pause_threshold = 0.0
            energy_threshold = 0

            def recognize_google(self, audio, language=None):
                raise _StubUnknownValueError()

        self.Microphone = Microphone
        self.AudioData = AudioData
        self.Recognizer = Recognizer


class _FakeOllama(types.ModuleType):
    def __init__(self):
        super().__init__("ollama")
        self.requests: list = []

    def chat(self, model=None, messages=None, options=None, **kw):
        self.requests.append({"model": model, "messages": messages, "options": options})
        raise RuntimeError("ollama is stubbed in tests")


STUBS = {
    "pyautogui": _FakePyautogui(),
    "pyperclip": _FakePyperclip(),
    "pyttsx3": _FakePyttsx3(),
    "psutil": _FakePsutil(),
    "speech_recognition": _FakeSpeechRecognition(),
    "sounddevice": types.ModuleType("sounddevice"),
    "numpy": types.ModuleType("numpy"),
    "ollama": _FakeOllama(),
    "vosk": types.ModuleType("vosk"),
}
sys.modules.update(STUBS)

import kira_memory  # noqa: E402

# Redirect the memory DB to a throwaway file BEFORE importing the backend,
# which reads memories while it is imported.
_TEST_DB = Path(tempfile.mkdtemp(prefix="kira_test_")) / "test_memory.db"
kira_memory.DB_PATH = str(_TEST_DB)
kira_memory.initialize()

import kira_voice_agent  # noqa: E402


@pytest.fixture()
def backend():
    """The voice-agent module with fresh stub state for each test."""
    STUBS["pyautogui"].calls = []
    STUBS["pyttsx3"].engine.spoken = []
    STUBS["ollama"].requests = []
    kira_voice_agent._CHAT_HISTORY.clear()
    return kira_voice_agent


@pytest.fixture()
def memory_db():
    """kira_memory with all tables emptied for the duration of a test."""
    import sqlite3

    with sqlite3.connect(kira_memory.DB_PATH) as connection:
        connection.execute("DELETE FROM memories")
        connection.execute("DELETE FROM conversations")
    return kira_memory


@pytest.fixture()
def speak_silenced(monkeypatch):
    """Mute speak() so action tests never touch PowerShell/pyttsx3."""
    monkeypatch.setattr(kira_voice_agent, "speak", lambda *a, **k: None)
