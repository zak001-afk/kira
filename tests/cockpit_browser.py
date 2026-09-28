"""MED interface smoke/visual tests with fake API replies; no desktop actions.

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


# Test-only instrumentation: production app.js does not expose renderer internals.
AVATAR_PROBE = r"""
window.__avatarTest = {
  get mouth() { return holoMouth; },
  holdPose(pose) {
    if (!this.originalSample) this.originalSample = holoMouth.motion.sample;
    holoMouth.motion.sample = () => pose;
  },
  releasePose() {
    holoMouth.motion.sample = this.originalSample;
    holoMouth.reset();
  },
  sample(points) {
    // Read in the same frame, after the app's real render loop. No preserveDrawingBuffer,
    // alternate renderer or shader replacement: this is the displayed WebGL output.
    return new Promise(resolve => requestAnimationFrame(() => {
      const plane = avatarGroup.children[0];
      const gl = renderer.getContext();
      const photo = document.createElement('canvas');
      photo.width = 1024; photo.height = 1024;
      const ctx = photo.getContext('2d');
      ctx.drawImage(plane.material.uniforms.map.value.image, 0, 0);
      resolve(points.map(([x, y]) => {
        const point = new THREE.Vector3(
          (x / 1024 - 0.5) * plane.geometry.parameters.width,
          (0.5 - y / 1024) * plane.geometry.parameters.height, 0);
        plane.localToWorld(point).project(camera);
        const pixel = new Uint8Array(4);
        gl.readPixels(Math.floor((point.x * 0.5 + 0.5) * gl.drawingBufferWidth),
          Math.floor((point.y * 0.5 + 0.5) * gl.drawingBufferHeight),
          1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
        return {
          rendered: Array.from(pixel),
          source: Array.from(ctx.getImageData(x, y, 1, 1).data),
        };
      }));
    }));
  },
};
"""


class MEDBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        validate_ui_bundle()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(KiraUIHandler, directory=str(ROOT / "ui")))
        cls.worker = Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get("KIRA_TEST_BROWSER"),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        self.errors, self.commands = [], []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("console", lambda message: self.errors.append(message.text) if message.type == "error" else None)
        # The UI has bundled fonts; don't let a third-party font request affect a render test.
        self.page.route("https://fonts.googleapis.com/**", lambda route: route.fulfill(content_type="text/css", body=""))
        three = ROOT / "node_modules" / "three"
        if three.exists():
            def local_three(route):
                path = urlsplit(route.request.url).path.split("three@0.180.0/", 1)[1]
                route.fulfill(path=str(three / path), content_type="text/javascript")
            self.page.route("https://cdn.jsdelivr.net/npm/three@0.180.0/**", local_three)

        def api(route):
            path = urlsplit(route.request.url).path
            data = {}
            if path == "/api/command":
                self.commands.append(route.request.post_data_json)
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

        self.page.route("**/api/**", api)

    def tearDown(self):
        self.page.close()

    def open_ui(self):
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}")
        self.page.wait_for_function("document.querySelector('#scene-container canvas') !== null")

    def test_med_ui_boot_chat_and_voice_preferences(self):
        self.open_ui()
        expect(self.page.locator("html")).to_have_attribute("lang", "fr")
        self.page.locator("#command").fill("bonjour")
        self.page.locator("#send").click()
        expect(self.page.locator("body")).to_contain_text("Bonjour depuis le test MED.")
        self.assertEqual(self.commands, [{"text": "bonjour"}])
        self.page.locator("#settings-btn").click()
        self.page.locator("#voice-select").select_option("denise")
        self.assertEqual(self.page.evaluate("localStorage.getItem('kira.voice')"), "denise")
        self.assertEqual(self.errors, [])

    def test_natural_face_and_speaking_lips_in_the_real_webgl_output(self):
        app = (ROOT / "ui" / "app.js").read_text(encoding="utf-8") + AVATAR_PROBE
        self.page.route("**/app.js*", lambda route: route.fulfill(content_type="text/javascript", body=app))
        self.open_ui()
        self.page.wait_for_function("window.__avatarTest?.mouth?.ready")
        expect(self.page.locator("#avatar-brightness")).to_have_value("90")
        points = [[512, 265], [418, 480], [505, 630]]  # forehead, cheek, pink lower lip

        def sample(coords=points):
            return self.page.evaluate("points => window.__avatarTest.sample(points)", coords)

        def assert_photo_colours(brightness):
            for pixel in sample():
                self.assertEqual(pixel["source"][3], 255, "facial pixels must stay opaque")
                self.assertEqual(pixel["rendered"][3], 255)
                for actual, original in zip(pixel["rendered"][:3], pixel["source"][:3]):
                    # Allow bilinear/mipmap sampling of the textured skin, not a green
                    # monochrome conversion, double gamma correction or blooming.
                    self.assertAlmostEqual(actual, original * brightness, delta=16)
                self.assertGreater(pixel["rendered"][0], pixel["rendered"][1] + 8)

        assert_photo_colours(0.9)
        self.assertTrue(self.page.evaluate("""() => {
            const mouth = window.__avatarTest.mouth;
            return mouth.overlay.material.uniforms.brightness === mouth.parent.material.uniforms.brightness;
        }"""))
        for value in (45, 100, 90):
            self.page.locator("#avatar-brightness").evaluate("""(slider, value) => {
                slider.value = value;
                slider.dispatchEvent(new Event('input', {bubbles: true}));
            }""", str(value))
            assert_photo_colours(value / 100)

        # Hold a speaking pose through the real render loop and inspect the cavity/lip.
        closed = sample([[512, 621]])[0]["rendered"]
        self.page.evaluate("""() => window.__avatarTest.holdPose({
            open: 0.85, round: 0, wide: 0.06, press: 0, bite: 0,
        })""")
        self.page.wait_for_function("window.__avatarTest.mouth.pose.open > 0.8")
        opened = sample([[512, 621], [512, 654]])
        self.assertEqual(self.page.evaluate(
            "window.__avatarTest.mouth.context.getImageData(136, 69, 1, 1).data[3]"), 255,
            "the cavity must stay opaque instead of revealing closed lips through triangle seams")
        self.assertLess(sum(opened[0]["rendered"][:3]), sum(closed[:3]) * 0.6,
                        "the mouth cavity must replace the closed lips, not leave a double mouth")
        self.assertGreater(opened[1]["rendered"][0], opened[1]["rendered"][1] + 15,
                           "animated lips must stay pink, not green")
        self.page.evaluate("window.__avatarTest.releasePose()")
        assert_photo_colours(0.9)
        self.assertEqual(self.page.evaluate(
            "window.__avatarTest.mouth.context.getImageData(136, 69, 1, 1).data[3]"), 0,
            "idle must restore the unmodified photograph")

        # Resize the same canvas: the portrait/patch must keep the same RGB and alignment.
        for width, height in ((900, 900), (390, 844)):
            self.page.set_viewport_size({"width": width, "height": height})
            assert_photo_colours(0.9)
        self.page.reload()
        self.page.wait_for_function("window.__avatarTest?.mouth?.ready")
        expect(self.page.locator("#avatar-brightness")).to_have_value("90")
        assert_photo_colours(0.9)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
