"""Exercise static serving and the same-origin API without desktop hardware."""
import ast
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from kira_ui import KiraUIHandler, UI_BUILD_ID, UI_REQUIRED_FILES, validate_ui_bundle

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def running_server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


class StaticUiTests(unittest.TestCase):
    def check_handler(self, filename):
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        handler_class = next(node for node in tree.body
                             if isinstance(node, ast.ClassDef) and node.name == "QuietHandler")
        namespace = {"KiraUIHandler": KiraUIHandler, "API_PORT": 8765}
        exec(compile(ast.Module(body=[handler_class], type_ignores=[]), filename, "exec"), namespace)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "speech.mjs").write_text("export const ready = true;", encoding="utf-8")
            with running_server(partial(namespace["QuietHandler"], directory=tmp)) as server:
                with urlopen(f"http://127.0.0.1:{server.server_port}/speech.mjs?v=lip-sync-1", timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(response.headers["X-KIRA-UI-Build"], UI_BUILD_ID)
                    self.assertIn("javascript", response.headers["Content-Type"])
                    self.assertIn(b"export const", response.read())

    def test_native_window_serves_uncached_javascript_modules(self):
        self.check_handler("main_window.py")

    def test_browser_launcher_serves_uncached_javascript_modules(self):
        self.check_handler("launch_web.py")

    def test_local_assets_have_correct_types_and_support_preview_hosts(self):
        with running_server(partial(KiraUIHandler, directory=str(ROOT / "ui"))) as server:
            for path, expected in [("index.html", "text/html"), ("hologram.mjs", "javascript"),
                                   ("assets/kira-hologram.webp", "image/webp"),
                                   ("assets/reticle.svg", "image/svg+xml"),
                                   ("assets/fonts/rajdhani-latin-500-normal.woff2", "font/woff2")]:
                request = Request(f"http://127.0.0.1:{server.server_port}/{path}", headers={"Host": "8766-preview.e2b.app"})
                with urlopen(request, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(expected, response.headers["Content-Type"])
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(response.headers["X-KIRA-UI-Build"], UI_BUILD_ID)
                    self.assertGreater(len(response.read()), 20)


class UIBundleTests(unittest.TestCase):
    def test_repository_bundle_has_the_expected_holographic_version(self):
        self.assertEqual(validate_ui_bundle(ROOT / "ui"), (ROOT / "ui").resolve())

    def test_partial_copy_is_rejected_with_an_actionable_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "index.html").write_text("old UI", encoding="utf-8")
            with self.assertRaisesRegex(FileNotFoundError, "do not replace main_window.py alone"):
                validate_ui_bundle(tmp)

    def test_old_index_is_rejected_even_when_all_assets_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in UI_REQUIRED_FILES:
                path = Path(tmp, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("old UI", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "does not match HOLOGRAPHIC COCKPIT 02"):
                validate_ui_bundle(tmp)


class APIProxyTests(unittest.TestCase):
    def test_proxy_preserves_get_query_post_json_and_error_status(self):
        seen = []

        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                seen.append((self.command, self.path, body))
                payload = json.dumps({"response": "Bonjour, Opérateur."}, ensure_ascii=False).encode("utf-8")
                self.send_response(422 if self.path == "/api/fail" else 200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = respond

        with running_server(Backend) as backend:
            class Handler(KiraUIHandler):
                api_port = backend.server_port

            with running_server(partial(Handler, directory=str(ROOT / "ui"))) as ui:
                base = f"http://127.0.0.1:{ui.server_port}"
                with urlopen(base + "/api/tasks?type=todo&completed=false", timeout=3) as response:
                    self.assertEqual(json.load(response)["response"], "Bonjour, Opérateur.")
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(response.headers["X-KIRA-UI-Build"], UI_BUILD_ID)
                payload = json.dumps({"text": "salut KIRA"}).encode()
                with urlopen(Request(base + "/api/command", data=payload, headers={"Content-Type": "application/json"}), timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(int(response.headers["Content-Length"]), len(response.read()))
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + "/api/fail", timeout=3)
                self.assertEqual(error.exception.code, 422)
                self.assertEqual(seen[0], ("GET", "/api/tasks?type=todo&completed=false", b""))
                self.assertEqual(seen[1], ("POST", "/api/command", payload))

    def test_missing_backend_is_an_explicit_json_503_not_a_static_404(self):
        class Handler(KiraUIHandler):
            api_port = 0  # No service can bind port zero as its resulting port.

        with running_server(Handler) as ui:
            with self.assertRaises(HTTPError) as error:
                urlopen(f"http://127.0.0.1:{ui.server_port}/api/status", timeout=3)
            self.assertEqual(error.exception.code, 503)
            self.assertIn("backend unavailable", json.load(error.exception)["error"])

    def test_proxy_rejects_oversized_body_and_post_to_static_files(self):
        class Handler(KiraUIHandler):
            max_body_size = 8

        with running_server(Handler) as ui:
            base = f"http://127.0.0.1:{ui.server_port}"
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/api/command", data=b"too much data"), timeout=3)
            self.assertEqual(error.exception.code, 413)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/index.html", data=b"{}"), timeout=3)
            self.assertEqual(error.exception.code, 405)


if __name__ == "__main__":
    unittest.main()
