"""Tests for the application window (``kira_app.py``).

The desktop app is a shell around the real interface, so these tests check
the shell and nothing else: that the server is actually serving the HUD on
the URL handed to the window, that a missing pywebview or a missing WebView2
runtime degrades to a browser instead of a blank window, and that the module
stays import-safe on machines with no GUI stack at all.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import types
import urllib.request

import pytest

import kira_app


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def fake_webview(monkeypatch):
    """A stand-in for the pywebview module that records what it was asked."""
    module = types.ModuleType("webview")
    module.calls = []

    def create_window(title, url, **kwargs):
        module.calls.append(("create_window", title, url, kwargs))
        return types.SimpleNamespace(title=title, url=url)

    def start(*args, **kwargs):
        module.calls.append(("start", args, kwargs))

    module.create_window = create_window
    module.start = start
    monkeypatch.setitem(sys.modules, "webview", module)
    return module


@pytest.fixture()
def no_webview(monkeypatch):
    """``import webview`` fails, as it does without pywebview installed."""
    monkeypatch.setitem(sys.modules, "webview", None)


class FakeProcess:
    """Minimal Popen stand-in: records argv, then exits (or hangs) on demand."""

    def __init__(self, argv, hang=False, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.hang = hang
        self.waits = 0
        self.terminated = False

    def wait(self, timeout=None):
        self.waits += 1
        if self.hang:
            raise subprocess.TimeoutExpired(cmd=self.argv, timeout=timeout or 0)
        return 0

    def terminate(self):
        self.terminated = True


# ── the native window ───────────────────────────────────────────────────────


class TestNativeWindow:
    def test_the_window_gets_the_hud_url_and_the_app_size(self, fake_webview):
        assert kira_app.run_native_window("http://127.0.0.1:9999") is True

        kinds = [call[0] for call in fake_webview.calls]
        assert kinds == ["create_window", "start"], "the window never opened"

        _, title, url, kwargs = fake_webview.calls[0]
        assert title == kira_app.WINDOW_TITLE
        assert url == "http://127.0.0.1:9999"
        assert (kwargs["width"], kwargs["height"]) == (
            kira_app.WINDOW_WIDTH,
            kira_app.WINDOW_HEIGHT,
        )
        assert kwargs["min_size"] == (
            kira_app.MIN_WINDOW_WIDTH,
            kira_app.MIN_WINDOW_HEIGHT,
        )

    def test_a_missing_pywebview_falls_back_instead_of_failing(self, no_webview, capsys):
        assert kira_app.run_native_window("http://127.0.0.1:9999") is False
        printed = capsys.readouterr().out
        assert "pywebview" in printed
        assert "browser" in printed

    def test_a_window_that_cannot_open_falls_back(self, monkeypatch, capsys):
        module = types.ModuleType("webview")
        module.create_window = lambda *a, **k: None

        def start(*args, **kwargs):
            raise RuntimeError("no WebView2 runtime")

        module.start = start
        monkeypatch.setitem(sys.modules, "webview", module)

        assert kira_app.run_native_window("http://127.0.0.1:9999") is False
        printed = capsys.readouterr().out
        assert "no WebView2 runtime" in printed, "the real reason was swallowed"

    def test_closing_the_window_is_not_a_failure(self, fake_webview):
        """start() returning is the *normal* end of the app, not a fallback."""
        assert kira_app.run_native_window("http://127.0.0.1:9999") is True

    def test_the_hud_keeps_its_settings_between_runs(self, fake_webview):
        """The voice toggle lives in localStorage — not in a private session."""
        kira_app.run_native_window("http://127.0.0.1:9999")
        _, _, kwargs = fake_webview.calls[1]
        assert kwargs.get("private_mode") is False

    def test_the_window_gets_the_app_icon(self, fake_webview):
        kira_app.run_native_window("http://127.0.0.1:9999")
        _, _, kwargs = fake_webview.calls[1]
        icon = kwargs.get("icon", "")
        assert icon.endswith("kira_app_icon.png"), "the app lost its icon"
        assert Path(icon).is_file(), f"the icon it points at does not exist: {icon}"

    def test_an_older_pywebview_without_those_keywords_still_opens(
        self, monkeypatch
    ):
        module = types.ModuleType("webview")
        module.create_window = lambda *a, **k: None
        calls = []

        def start(**kwargs):
            calls.append(kwargs)
            if kwargs:
                raise TypeError("start() got an unexpected keyword argument")

        module.start = start
        monkeypatch.setitem(sys.modules, "webview", module)

        assert kira_app.run_native_window("http://127.0.0.1:9999") is True
        assert len(calls) == 2, "the retry never happened"
        assert calls[0].get("private_mode") is False
        assert calls[1] == {}, "the retry repeated the rejected keywords"


# ── finding a browser for the fallback ──────────────────────────────────────


class TestBrowserFallback:
    def test_an_installed_browser_is_found(self, monkeypatch):
        monkeypatch.setattr(kira_app.os, "name", "nt")
        monkeypatch.setattr(kira_app.shutil, "which", lambda name: None)
        monkeypatch.setattr(
            kira_app.os.path,
            "isfile",
            lambda path: path.endswith("msedge.exe"),
        )
        found = kira_app.find_app_browser()
        assert found is not None
        name, path = found
        assert name == "Edge"
        assert path.endswith("msedge.exe")

    def test_windows_paths_are_not_probed_off_windows(self, monkeypatch):
        """`%ProgramFiles%` never expands on Linux/macOS, so do not try."""
        probed = []
        monkeypatch.setattr(kira_app.os, "name", "posix")
        monkeypatch.setattr(
            kira_app.os.path, "isfile", lambda path: probed.append(path) or False
        )
        monkeypatch.setattr(kira_app.shutil, "which", lambda name: None)
        assert kira_app.find_app_browser() is None
        assert probed == [], f"Windows install paths were checked: {probed}"

    def test_a_browser_on_path_is_found(self, monkeypatch):
        monkeypatch.setattr(kira_app.os, "name", "posix")
        monkeypatch.setattr(
            kira_app.shutil,
            "which",
            lambda name: "/usr/bin/microsoft-edge" if name == "microsoft-edge" else None,
        )
        assert kira_app.find_app_browser() == (
            "microsoft-edge",
            "/usr/bin/microsoft-edge",
        )

    def test_no_browser_at_all_is_reported_honestly(self, monkeypatch):
        monkeypatch.setattr(kira_app.shutil, "which", lambda name: None)
        monkeypatch.setattr(kira_app.os.path, "isfile", lambda path: False)
        assert kira_app.find_app_browser() is None

    def test_the_window_is_opened_in_app_mode(self, monkeypatch):
        monkeypatch.setattr(
            kira_app, "find_app_browser", lambda: ("Edge", "/fake/msedge")
        )
        created = []

        def fake_popen(argv, **kwargs):
            process = FakeProcess(argv, hang=True, **kwargs)
            created.append(process)
            return process

        monkeypatch.setattr(kira_app.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(kira_app, "_wait_for_exit", lambda process: None)

        server = _FakeServer()
        assert kira_app._fall_back_to_browser(server, "http://127.0.0.1:1234") == 0

        argv = created[0].argv
        assert "--app=http://127.0.0.1:1234" in argv
        assert (
            f"--window-size={kira_app.WINDOW_WIDTH},{kira_app.WINDOW_HEIGHT}" in argv
        )
        assert server.closed is True, "the server was left running"

    def test_a_handed_off_window_keeps_the_api_up(self, monkeypatch):
        """Chrome/Edge may exit at once and leave the window to itself."""
        monkeypatch.setattr(
            kira_app, "find_app_browser", lambda: ("Chrome", "/fake/chrome")
        )
        monkeypatch.setattr(
            kira_app.subprocess,
            "Popen",
            lambda argv, **kwargs: FakeProcess(argv, hang=False, **kwargs),
        )
        served = []
        monkeypatch.setattr(
            kira_app, "_serve_until_interrupted", lambda s, url: served.append(url) or 0
        )

        server = _FakeServer()
        assert kira_app._fall_back_to_browser(server, "http://127.0.0.1:1234") == 0
        assert served == ["http://127.0.0.1:1234"], (
            "the page would have lost its API"
        )

    def test_without_a_browser_the_default_one_is_used(self, monkeypatch):
        monkeypatch.setattr(kira_app, "find_app_browser", lambda: None)
        monkeypatch.setattr(kira_app.webbrowser, "open", lambda url: None)
        served = []
        monkeypatch.setattr(
            kira_app, "_serve_until_interrupted", lambda s, url: served.append(url) or 0
        )

        assert kira_app._fall_back_to_browser(_FakeServer(), "http://127.0.0.1:1") == 0
        assert served == ["http://127.0.0.1:1"]


class _FakeServer:
    """Enough of kira_server.KiraWebServer to test the shell's lifecycle."""

    def __init__(self):
        self.shutdown_called = False
        self.closed = False
        self.service = types.SimpleNamespace(mode="simulation", version="test")

    def shutdown(self):
        self.shutdown_called = True

    def server_close(self):
        self.closed = True


# ── the whole app ───────────────────────────────────────────────────────────


class TestApplication:
    def test_the_window_is_handed_a_live_hud(self, monkeypatch):
        """The URL given to the window must already be serving the interface."""
        seen = {}

        def fake_window(url):
            seen["url"] = url
            with urllib.request.urlopen(f"{url}/api/health", timeout=5) as response:
                seen["health"] = json.loads(response.read().decode())
            with urllib.request.urlopen(f"{url}/", timeout=5) as response:
                seen["page"] = response.read().decode("utf-8", "replace")
            return True

        monkeypatch.setattr(kira_app, "run_native_window", fake_window)

        assert kira_app.main(["--simulate", "--port", "0"]) == 0

        assert seen["url"].startswith("http://127.0.0.1:")
        assert seen["health"]["ok"] is True
        assert seen["health"]["mode"] == "simulation"
        assert "K I R A".replace(" ", "") in seen["page"].replace(" ", ""), (
            "the served page is not the HUD"
        )

    def test_an_ephemeral_port_is_used_by_default(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            kira_app, "run_native_window", lambda url: seen.update(url=url) or True
        )
        assert kira_app.main(["--simulate"]) == 0
        port = int(seen["url"].rsplit(":", 1)[1])
        assert port != kira_server_port(), "the app took the fixed CLI port"

    def test_a_busy_port_is_reported_not_crashed(self, monkeypatch):
        """Binding twice must not raise a traceback at the user."""
        monkeypatch.setattr(kira_app, "run_native_window", lambda url: True)
        blocker = kira_app.start_server("127.0.0.1", 0, simulate=True)
        port = blocker.server_address[1]
        try:
            assert kira_app.main(["--simulate", "--port", str(port)]) == 1
        finally:
            blocker.shutdown()
            blocker.server_close()

    def test_missing_ui_files_stop_the_app_early(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(kira_app, "UI_DIR", tmp_path / "nope")
        called = []
        monkeypatch.setattr(
            kira_app, "run_native_window", lambda url: called.append(url) or True
        )
        assert kira_app.main(["--simulate"]) == 2
        assert called == [], "a window was opened for a UI that does not exist"
        assert "UI files are missing" in capsys.readouterr().err

    def test_browser_mode_skips_the_native_window(self, monkeypatch):
        opened = []
        monkeypatch.setattr(
            kira_app, "run_native_window", lambda url: opened.append(url) or True
        )
        monkeypatch.setattr(kira_app, "find_app_browser", lambda: None)
        monkeypatch.setattr(kira_app.webbrowser, "open", lambda url: None)
        monkeypatch.setattr(kira_app, "_serve_until_interrupted", lambda s, url: 0)

        assert kira_app.main(["--simulate", "--browser"]) == 0
        assert opened == [], "--browser still tried to open a native window"

    def test_the_watchdog_is_off_in_simulation(self, monkeypatch):
        monkeypatch.setattr(kira_app, "run_native_window", lambda url: True)
        assert kira_app.main(["--simulate"]) == 0
        # a simulated agent must never pretend to watch the machine


def kira_server_port() -> int:
    import kira_server

    return kira_server.DEFAULT_PORT


# ── hygiene ─────────────────────────────────────────────────────────────────


def test_importing_the_app_pulls_in_no_desktop_stack():
    """The shell must import on a machine with no GUI, window or WebView2."""
    for module in ("pywebview", "tkinter", "customtkinter", "webview"):
        assert module not in sys.modules, f"kira_app imported {module} eagerly"


def test_the_banner_says_what_is_actually_running():
    service = types.SimpleNamespace(mode="live", version="2.7.0", backend=None,
                                    simulate=False, reason="ImportError: pyautogui")
    text = kira_app.banner(service, "http://127.0.0.1:8788", watching=False)
    assert "mode      : live" in text
    assert "unavailable" in text
    assert "ImportError: pyautogui" in text
    assert "watchdog  : off" in text
