"""KIRA's application window: the neural interface, in its own native frame.

There is one interface. ``ui/`` is it — the same HUD the browser gets from
``kira_server.py`` — and this module is what turns it into a desktop app:

1. **Serve** — a ``kira_server`` instance is started in-process on
   ``127.0.0.1`` with an ephemeral port (nothing else on the machine can
   reach it, and two launches never fight over a port).
2. **Show** — ``pywebview`` renders that URL in a native window. On Windows
   that is the Edge Chromium/WebView2 engine, so the Three.js reactor, the
   fonts and the layout are exactly what the browser shows.
3. **Fall back, never fail** — if pywebview or the WebView2 runtime is
   missing, KIRA opens the same URL in an app-mode Edge/Chrome window
   instead, and failing that in the default browser. The command pipeline,
   the microphone and the confirmation flow are identical in every case
   because they were never duplicated: they live in ``kira_server``.

Why the desktop UI is no longer a second implementation: ``main_window.py``
was a parallel customtkinter copy of this HUD. Keeping the two in step meant
writing every panel, every state and every fix twice, and the copies had
already drifted. The app is now a shell around the real interface.

Usage
-----
    python kira_app.py                  # native window (or a browser fallback)
    python kira_app.py --simulate       # labelled demo, no desktop stack
    python kira_app.py --browser        # skip the native window on purpose
    python kira_app.py --port 8788      # a fixed port instead of an ephemeral one
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import kira_server

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"

WINDOW_TITLE = "KIRA — Neural Interface"
WINDOW_WIDTH = 1540
WINDOW_HEIGHT = 930
MIN_WINDOW_WIDTH = 1180
MIN_WINDOW_HEIGHT = 760
WINDOW_BACKGROUND = "#010101"

# Where an app-mode window can be launched from when pywebview is absent.
# The first entry that exists on disk wins.
WINDOWS_BROWSERS = (
    ("Edge", r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    ("Edge", r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ("Chrome", r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    ("Chrome", r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    ("Chrome", r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
)

POSIX_BROWSERS = ("microsoft-edge", "google-chrome", "chromium", "chromium-browser")


def find_app_browser() -> "tuple[str, str] | None":
    """Locate a Chromium-family browser that can run in ``--app`` mode.

    The install paths are platform-specific: ``%ProgramFiles%`` only expands
    on Windows, so those candidates are only tried there.
    """
    if os.name == "nt":
        for name, raw in WINDOWS_BROWSERS:
            candidate = os.path.expandvars(raw)
            if os.path.isfile(candidate):
                return name, candidate
    for name in POSIX_BROWSERS:
        found = shutil.which(name)
        if found:
            return name, found
    return None


def _import_webview():
    """The pywebview module, or None when it is not installed."""
    try:
        import webview
    except Exception:  # not installed, or no GUI toolkit behind it
        return None
    return webview


def open_native_window(webview, url: str) -> None:
    """Create the window and block until the user closes it."""
    webview.create_window(
        WINDOW_TITLE,
        url,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT),
        background_color=WINDOW_BACKGROUND,
        resizable=True,
    )
    # private_mode would throw the HUD's localStorage away between runs —
    # the voice toggle is kept there.
    options = {"private_mode": False}
    icon = ROOT / "assets" / "kira_app_icon.png"
    if icon.is_file():
        options["icon"] = str(icon)
    try:
        webview.start(**options)
    except TypeError:
        # an older pywebview without these keywords: a plain start still works
        webview.start()


def run_native_window(url: str) -> bool:
    """Show the HUD in a native window.

    Returns True once the window has been shown (and later closed). False
    means no window could be created, so the caller should fall back.
    """
    webview = _import_webview()
    if webview is None:
        print("KIRA: pywebview is not installed — using a browser window instead.")
        print("      pip install pywebview   (Windows uses Edge WebView2)")
        return False
    try:
        open_native_window(webview, url)
    except Exception as exc:  # no WebView2 runtime, no display, a broken build…
        print(
            f"KIRA: the native window could not open "
            f"({type(exc).__name__}: {exc}) — using a browser window instead."
        )
        return False
    return True


def launch_app_window(browser: "tuple[str, str]", url: str) -> subprocess.Popen:
    """Open the HUD in an app-mode window (no tabs, no URL bar)."""
    name, path = browser
    print(f"KIRA: opening the interface with {name}.")
    return subprocess.Popen(
        [
            path,
            f"--app={url}",
            f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


def reachable_url(host: str, port: int, token: str = "") -> str:
    """The address the window should open.

    ``0.0.0.0`` means "every interface", not a place you can browse to, and an
    IPv6 wildcard needs brackets — so the address shown is the loopback one.
    When the server demanded a token it rides in the link: the HUD reads it
    once, remembers it, and strips it from the address bar.
    """
    name = str(host or "").strip()
    if name in {"", "0.0.0.0", "::", "[::]"}:
        name = "127.0.0.1"
    elif ":" in name and not name.startswith("["):
        name = f"[{name}]"
    suffix = f"?token={token}" if token else ""
    return f"http://{name}:{int(port)}{suffix}"


def start_server(host: str, port: int, simulate: bool, token: str = "",
                 allowed_hosts=(), trust_proxy: bool = False):
    """Start KIRA's web service on a background thread and return it."""
    server = kira_server.create_server(
        host,
        port,
        simulate=simulate,
        token=token,
        allowed_hosts=allowed_hosts,
        trust_proxy=trust_proxy,
    )
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.4}, daemon=True
    )
    thread.start()
    return server


def banner(service, url: str, watching: bool) -> str:
    lines = [
        "=" * 62,
        "KIRA // NEURAL INTERFACE",
        "=" * 62,
        f"mode      : {service.mode}",
        f"version   : {service.version}",
    ]
    if service.backend is None and not service.simulate:
        lines += [
            f"backend   : unavailable ({service.reason})",
            "            the interface will load, commands will explain why",
        ]
    if service.token:
        lines += [
            "access    : a token is required on API calls",
            "            it is in the link below — the window keeps it",
        ]
    if service.trust_proxy:
        lines += [
            "proxy     : --trust-proxy is ON — Host/Origin checks are disabled",
        ]
    lines += [
        f"open      : {url}",
        f"watchdog  : {'on' if watching else 'off'}",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="KIRA's application window (the neural interface, natively)."
    )
    parser.add_argument("--host", default=kira_server.DEFAULT_HOST,
                        help="bind address (127.0.0.1 keeps it to this machine)")
    parser.add_argument("--port", type=int, default=0,
                        help="port to serve on (0 picks a free one)")
    parser.add_argument("--simulate", action="store_true",
                        help="run a labelled demo responder instead of the agent")
    parser.add_argument("--browser", action="store_true",
                        help="skip the native window and open the browser")
    parser.add_argument("--no-watchdog", action="store_true",
                        help="do not start the proactive system watchdog")
    parser.add_argument("--token", default="",
                        help="require this token on /api calls (auto-generated "
                             "when binding beyond loopback)")
    parser.add_argument("--allow-host", action="append", default=[], metavar="NAME",
                        help="extra Host name to answer to (reverse proxy)")
    parser.add_argument("--trust-proxy", action="store_true",
                        help="accept any Host/Origin: only for a preview pane or "
                             "a reverse proxy you control")
    args = parser.parse_args(argv)

    if not (UI_DIR / "index.html").is_file():
        print(f"UI files are missing from {UI_DIR}", file=sys.stderr)
        return 2

    try:
        server = start_server(
            args.host,
            args.port,
            args.simulate,
            token=args.token,
            allowed_hosts=args.allow_host,
            trust_proxy=args.trust_proxy,
        )
    except OSError as exc:
        print(
            f"Could not bind {args.host}:{args.port} — {exc}",
            file=sys.stderr,
        )
        return 1

    service = server.service
    if not args.no_watchdog:
        service.start_background()
    url = reachable_url(args.host, server.server_address[1], service.token)
    print(banner(service, url, service.watchdog_running), flush=True)

    shown = False
    if not args.browser:
        shown = run_native_window(url)

    if not shown:
        return _fall_back_to_browser(server, url)

    server.shutdown()
    server.server_close()
    return 0


def _fall_back_to_browser(server, url: str) -> int:
    """Show the interface in a browser when there is no native window.

    Either the browser owns the window (and this process must stay up so the
    page keeps talking to the API), or the browser hands it off to an
    already-running instance and exits. The two cases are reported honestly
    instead of pretending the process dies with the window.
    """
    browser = find_app_browser()
    if browser is None:
        print("KIRA: opening your default browser.")
        webbrowser.open(url)
        return _serve_until_interrupted(server, url)

    process = launch_app_window(browser, url)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        print("\nKIRA: close the window to stop.", flush=True)
        _wait_for_exit(process)
        server.shutdown()
        server.server_close()
        return 0

    print(
        "KIRA: your browser already had a window open, so it took this one over.",
        flush=True,
    )
    return _serve_until_interrupted(server, url)


def _wait_for_exit(process: subprocess.Popen) -> None:
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()


def _serve_until_interrupted(server, url: str = "") -> int:
    """Keep the API up until the user stops the process.

    Closing a browser window cannot be observed from here, so this says what
    it actually does rather than claiming to stop with the window.
    """
    print(
        f"\nKIRA is serving at {url} — press CTRL+C to stop (or close this window).",
        flush=True,
    )
    try:
        while True:
            threading.Event().wait(0.5)
    except KeyboardInterrupt:
        print("\nKIRA: shutting down the interface.")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
