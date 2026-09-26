"""MED interface smoke test with fake API replies; never executes desktop actions.

Install playwright and its Chromium, then run python tests/cockpit_browser.py.
KIRA_TEST_BROWSER can select an existing Chromium. If node_modules/three exists,
CDN requests are served from that exact local package for an offline test.
"""
from functools import partial
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from threading import Thread
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kira_ui import KiraUIHandler, validate_ui_bundle
from playwright.sync_api import sync_playwright, expect


class MEDBrowserTests(unittest.TestCase):
    def test_med_ui_boot_chat_and_voice_preferences(self):
        validate_ui_bundle()
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(KiraUIHandler, directory=str(ROOT / "ui")))
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=os.environ.get("KIRA_TEST_BROWSER"),
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
                )
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors, commands = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))

                three = ROOT / "node_modules" / "three"
                if three.exists():
                    def local_three(route):
                        path = urlsplit(route.request.url).path.split("three@0.180.0/", 1)[1]
                        route.fulfill(path=str(three / path), content_type="text/javascript")
                    page.route("https://cdn.jsdelivr.net/npm/three@0.180.0/**", local_three)

                def api(route):
                    path = urlsplit(route.request.url).path
                    data = {}
                    if path == "/api/command":
                        commands.append(route.request.post_data_json)
                        data = {"response": "Bonjour depuis le test MED.", "action": "chat"}
                    elif path == "/api/tasks":
                        data = {"tasks": []}
                    elif path == "/api/history":
                        data = {"messages": []}
                    elif path == "/api/plugins":
                        data = {"plugins": []}
                    elif path == "/api/status":
                        data = {"backend_available": True}
                    elif path == "/api/tts":
                        data = {"error": "Audio disabled for smoke test"}
                    route.fulfill(content_type="application/json", body=json.dumps(data))

                page.route("**/api/**", api)
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.wait_for_function("typeof window.sendCommand === 'function' || document.querySelector('#scene-container canvas') !== null")
                expect(page.locator("html")).to_have_attribute("lang", "fr")
                page.locator("#command").fill("bonjour")
                page.locator("#send").click()
                expect(page.locator("body")).to_contain_text("Bonjour depuis le test MED.")
                self.assertEqual(commands, [{"text": "bonjour"}])
                page.locator("#settings-btn").click()
                page.locator("#voice-select").select_option("denise")
                self.assertEqual(page.evaluate("localStorage.getItem('kira.voice')"), "denise")
                self.assertEqual(errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
