"""Shared, same-origin UI server for KIRA's native window and browser launcher.

Run a hardware-independent visual preview with:
    python kira_ui.py --preview --host 0.0.0.0

Preview mode starts the real telemetry/task API, but never loads the desktop
agent or pretends to execute commands. Install psutil for live system readings.
The default binding is loopback; exposing this unauthenticated local agent on a
public network is not recommended.
"""

import argparse
import os
from functools import partial
from http.client import HTTPConnection, HTTPException
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

UI_DIRECTORY = Path(__file__).resolve().parent / "ui"
UI_BUILD_ID = "holographic-cockpit-04-open-15"
UI_BUILD_LABEL = "HOLOGRAPHIC COCKPIT 04 / OPEN 15"
UI_REQUIRED_FILES = (
    "index.html", "style.css", "app.js", "speech.mjs", "hologram.mjs", "lips.mjs", "mouth.mjs",
    "assets/kira-mouth-interior.webp", "i18n.mjs", "locale.mjs",
    "assets/fonts/noto-sans-arabic-arabic-400-normal.woff2",
    "assets/fonts/noto-sans-arabic-arabic-600-normal.woff2",
    "assets/kira-hologram.webp", "assets/reticle.svg", "assets/projector.svg",
    "assets/neural-map.svg", "assets/binary-field.svg", "assets/kira-mark.svg",
)


def validate_ui_bundle(directory=UI_DIRECTORY):
    """Catch partial source updates instead of serving an old/incomplete UI."""
    directory = Path(directory).resolve()
    missing = [name for name in UI_REQUIRED_FILES if not (directory / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Incomplete KIRA UI at {directory}. Missing: {', '.join(missing)}. "
            "Update the entire project, including ui/; do not replace main_window.py alone."
        )
    index = (directory / "index.html").read_text(encoding="utf-8")
    if f'name="kira-ui-build" content="{UI_BUILD_ID}"' not in index:
        raise RuntimeError(
            f"The UI at {directory} does not match {UI_BUILD_LABEL}. "
            "Update the entire ui/ folder from the same Git revision as this launcher."
        )
    return directory


def print_ui_info(directory):
    """Make it easy to identify which local copy the user actually launched."""
    import sys
    print(f"[KIRA UI] {UI_BUILD_LABEL}", flush=True)
    print(f"[KIRA UI] Python: {sys.executable}", flush=True)
    print(f"[KIRA UI] Files: {directory}", flush=True)


def webview_profile_directory():
    """Persist UI preferences outside the source tree / frozen program files."""
    if os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "KIRA" / "WebViewProfile"


class KiraUIHandler(SimpleHTTPRequestHandler):
    """Serve local assets and proxy /api/* only to the configured local API."""

    api_host = "127.0.0.1"
    api_port = 8765
    api_timeout = 125
    max_body_size = 1024 * 1024
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mjs": "text/javascript",
        ".webp": "image/webp",
        ".woff2": "font/woff2",
    }

    def end_headers(self):
        # Desktop WebView2 must pick up UI changes after a pull/rebuild.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-KIRA-UI-Build", UI_BUILD_ID)
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, format, *args):
        pass

    def _is_api(self):
        return urlsplit(self.path).path.startswith("/api/")

    def do_GET(self):
        if self._is_api():
            self._proxy_api()
        else:
            super().do_GET()

    def do_POST(self):
        if self._is_api():
            self._proxy_api()
        else:
            self.send_error(405, "POST is only supported for the API")

    def _json_error(self, status, message):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy_api(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_error(400, "Invalid Content-Length")
            return
        if length < 0 or self.headers.get("Transfer-Encoding"):
            self._json_error(400, "Invalid request body")
            return
        if length > self.max_body_size:
            self._json_error(413, "Request body too large")
            return
        body = self.rfile.read(length) if length else None
        parsed = urlsplit(self.path)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        connection = HTTPConnection(self.api_host, self.api_port, timeout=self.api_timeout)
        try:
            connection.request(self.command, path, body=body, headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            })
            response = connection.getresponse()
            payload = response.read()
            status = response.status
            content_type = response.getheader("Content-Type", "application/json")
        except (OSError, HTTPException):
            self._json_error(503, "KIRA backend unavailable. Start the KIRA desktop app or web launcher.")
            return
        finally:
            connection.close()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    parser = argparse.ArgumentParser(description="Serve KIRA's holographic interface")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--api-port", type=int, default=8765)
    parser.add_argument("--preview", action="store_true", help="Start telemetry/task API without desktop control or an AI model")
    args = parser.parse_args()
    ui_dir = validate_ui_bundle()
    print_ui_info(ui_dir)
    api_server = None
    if args.preview:
        import kira_api
        api_server = kira_api.start_server(host="127.0.0.1", port=args.api_port)
        print("[KIRA] Interface preview. Desktop commands and AI chat are not loaded.", flush=True)
    KiraUIHandler.api_port = args.api_port
    server = ThreadingHTTPServer((args.host, args.port), partial(KiraUIHandler, directory=str(ui_dir)))
    print(f"[KIRA] Neural interface listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if api_server:
            api_server.shutdown()
            api_server.server_close()


if __name__ == "__main__":
    main()
