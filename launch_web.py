"""
KIRA Web Launcher — Starts the API server and opens the web UI in a browser.

This is the recommended way to launch KIRA with the holographic cockpit interface.

Usage:
    python launch_web.py

The API server starts on port 8765 and the browser opens automatically.
"""

import http.server
import os
import sys
import threading
import time
import webbrowser
from functools import partial
from pathlib import Path

# Add project root to path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kira_ui import KiraUIHandler, validate_ui_bundle, print_ui_info

import kira_api
import kira_voice_agent as backend

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

API_PORT = 8765
UI_PORT = 8766  # Static file server for the UI
HOST = "0.0.0.0"


class QuietHandler(KiraUIHandler):
    """Serve the cockpit and its same-origin API in browser mode."""

    api_port = API_PORT


def start_ui_server():
    """Serve the ui/ directory on a separate port."""
    ui_dir = validate_ui_bundle(HERE / "ui")
    print_ui_info(ui_dir)
    handler = partial(QuietHandler, directory=str(ui_dir))
    server = http.server.ThreadingHTTPServer((HOST, UI_PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main():
    print()
    print("=" * 60)
    print("              KIRA — NEURAL INTERFACE")
    print("=" * 60)
    print()

    # 1. Set up the API backend
    print("[1/4] Initializing KIRA backend...")
    kira_api.set_backend(backend)

    # 2. Start the API server
    print(f"[2/4] Starting API server on http://127.0.0.1:{API_PORT}")
    api_server = kira_api.start_server(host="127.0.0.1", port=API_PORT, daemon=True)

    # 3. Start the UI file server
    print(f"[3/4] Starting UI server on http://localhost:{UI_PORT}")
    ui_server = start_ui_server()

    # 4. Open the browser
    print(f"[4/4] Opening KIRA interface...")
    time.sleep(0.5)
    webbrowser.open(f"http://localhost:{UI_PORT}")

    print()
    print("=" * 60)
    print(f"  KIRA is running!")
    print(f"  UI:  http://localhost:{UI_PORT}")
    print(f"  API: http://localhost:{API_PORT}")
    print()
    print("  Press Ctrl+C to stop.")
    print("=" * 60)
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[KIRA] Shutting down...")
        kira_api.stop_server(api_server)
        ui_server.shutdown()
        print("[KIRA] Goodbye.")


if __name__ == "__main__":
    main()
