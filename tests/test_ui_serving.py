"""Exercise the real static handler classes without importing desktop hardware."""
import ast
from functools import partial
import http.server
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


class StaticUiTests(unittest.TestCase):
    def check_handler(self, filename):
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        handler_class = next(node for node in tree.body
                             if isinstance(node, ast.ClassDef) and node.name == "QuietHandler")
        namespace = {"http": http, "SimpleHTTPRequestHandler": http.server.SimpleHTTPRequestHandler}
        exec(compile(ast.Module(body=[handler_class], type_ignores=[]), filename, "exec"), namespace)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "speech.mjs").write_text("export const ready = true;", encoding="utf-8")
            server = http.server.HTTPServer(("127.0.0.1", 0), partial(namespace["QuietHandler"], directory=tmp))
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/speech.mjs?v=speech-sync-2", timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertIn("javascript", response.headers["Content-Type"])
                    self.assertIn(b"export const", response.read())
            finally:
                server.shutdown()
                server.server_close()
                worker.join()

    def test_native_window_serves_uncached_javascript_modules(self):
        self.check_handler("main_window.py")

    def test_browser_launcher_serves_uncached_javascript_modules(self):
        self.check_handler("launch_web.py")


if __name__ == "__main__":
    unittest.main()
