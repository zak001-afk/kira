"""Optional real-browser regressions, with API fixtures (never desktop actions).

    pip install playwright
    playwright install chromium
    python tests/cockpit_browser.py

KIRA_TEST_BROWSER may point to an existing Chromium executable.
"""
from functools import partial
from http.server import ThreadingHTTPServer
import json
import base64
import io
import math
import struct
import wave
import os
from pathlib import Path
import sys
from threading import Thread
import unittest
from urllib.parse import urlsplit
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kira_ui import KiraUIHandler
import kira_language
import kira_commands
from playwright.sync_api import sync_playwright, expect


def voiced_fixture():
    """Decoded PCM with two voiced intervals and a real silence, not spoken text."""
    rate = 16000
    output = io.BytesIO()
    samples = []
    for i in range(int(rate * 3.2)):
        t = i / rate
        voiced = 0.1 <= t < 0.9 or 1.55 <= t < 2.8
        envelope = 0.5 + 0.5 * math.sin(t * 18) ** 2
        value = (math.sin(2 * math.pi * 190 * t) + 0.3 * math.sin(2 * math.pi * 600 * t)) * 0.15 * envelope if voiced else 0
        samples.append(struct.pack("<h", int(value * 32767)))
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(samples))
    return {"audio": base64.b64encode(output.getvalue()).decode("ascii"), "format": "wav", "word_timings": [
        {"text": "Hello", "start": 0.1, "duration": 0.8},
        {"text": "Bonjour", "start": 1.55, "duration": 1.25},
    ]}


class CockpitBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(KiraUIHandler, directory=str(ROOT / "ui")))
        cls.worker = Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get("KIRA_TEST_BROWSER"),
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        self.page = self.context.new_page()
        self.errors = []
        self.requests = []
        self.tasks = []
        self.offline = False
        self.speech_payload = None
        self.real_language_policy = False
        self.language_backend = SimpleNamespace(normalize_command=lambda text: text, parse_simple_command=lambda text: None, ask_chat=lambda text, language=None: kira_commands.message("greeting", language))
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("request", lambda request: self.requests.append(request))
        self.page.route("**/api/**", self.api)

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.context.close()

    def api(self, route):
        path = urlsplit(route.request.url).path
        if self.offline:
            route.fulfill(status=503, content_type="application/json", body=json.dumps({"error": "Backend not available"}))
            return
        if path == "/api/languages":
            data = kira_language.available_languages()
        elif path == "/api/status":
            data = {"online": True, "backend_available": True, "model": "qwen3:0.6b"}
        elif path == "/api/system":
            data = {"cpu_percent": 21.2, "memory_percent": 42.4, "disk_percent": 61.7, "gpu": "Test graphics device"}
        elif path == "/api/history":
            data = {"messages": []}
        elif path == "/api/tasks":
            data = {"tasks": self.tasks}
        elif path == "/api/task":
            task = {"id": str(len(self.tasks) + 1), "title": route.request.post_data_json["title"]}
            self.tasks.append(task)
            data = {"success": True, "id": task["id"]}
        elif path == "/api/task/complete":
            task_id = route.request.post_data_json["id"]
            self.tasks = [task for task in self.tasks if task["id"] != task_id]
            data = {"success": True}
        elif path == "/api/command":
            data = {"response": 'Here is literal text: <img id="injected" src=x onerror="window.injected=true">'}
            if self.real_language_policy:
                data = kira_commands.process_command(self.language_backend, **route.request.post_data_json)
        elif path == "/api/tts":
            data = self.speech_payload or {"error": "No synthesized voice in the browser test fixture"}
        else:
            self.fail(f"Unexpected API request: {path}")
        route.fulfill(content_type="application/json", body=json.dumps(data))

    def load(self):
        self.page.goto(self.base, wait_until="networkidle")
        self.page.evaluate("document.fonts.ready")

    def test_local_assets_and_responsive_command_controls(self):
        self.load()
        self.assertTrue(self.page.locator("img").evaluate_all("els => els.every(el => el.complete && el.naturalWidth > 0)"))
        expect(self.page.locator("#cpu")).to_have_text("21.2%")
        expect(self.page.locator("#status-text")).to_have_text("NEURAL LINK ACTIVE")
        for width, height in [(1920, 1080), (1440, 900), (1366, 768), (1000, 700), (852, 480), (768, 1024), (600, 900), (390, 844), (320, 568)]:
            with self.subTest(width=width, height=height):
                self.page.set_viewport_size({"width": width, "height": height})
                self.assertFalse(self.page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                self.page.locator("#command").scroll_into_view_if_needed()
                expect(self.page.locator("#command")).to_be_in_viewport()
                expect(self.page.locator("#send")).to_be_in_viewport()
                rect = self.page.locator("#send").bounding_box()
                self.assertGreater(rect["width"], 25)
                self.assertGreater(rect["height"], 25)
        self.assertTrue(all(request.url.startswith(self.base) for request in self.requests), "UI must not request CDN assets or a browser-local backend")

    def test_commands_safe_text_and_quick_prompt(self):
        self.load()
        self.page.locator("#mute").click()
        self.page.locator('[data-prompt="search for "]').click()
        expect(self.page.locator("#command")).to_have_value("search for ")
        self.assertFalse(any("/api/command" in request.url for request in self.requests), "Incomplete search must not execute")
        self.page.locator("#command").fill("Bonjour KIRA")
        self.page.locator("#command").press("Enter")
        expect(self.page.locator(".message").last).to_contain_text("<img")
        expect(self.page.locator("#injected")).to_have_count(0)
        expect(self.page.locator("#command-count")).to_have_text("001")
        command = next(request for request in self.requests if request.url.endswith("/api/command"))
        self.assertEqual(command.post_data_json, {"text": "Bonjour KIRA", "reply_language": "auto", "previous_language": "en", "interface_language": "en"})
        self.page.locator("#clear-chat").click()
        expect(self.page.locator(".message-block")).to_have_count(1)
        expect(self.page.locator(".message")).to_contain_text("Channel cleared")

    def test_tasks_are_saved_and_completed_through_the_api(self):
        self.load()
        self.page.locator('.system-toolbar [data-dialog="tasks"]').click()
        expect(self.page.locator("#system-dialog")).to_be_visible()
        self.page.locator("#task-title").fill("Préparer la prochaine version de KIRA")
        self.page.locator("#task-form button").click()
        expect(self.page.locator(".task-item")).to_have_count(1)
        expect(self.page.locator("#task-count")).to_have_text("1")
        expect(self.page.locator("#task-title")).to_have_value("")
        self.page.locator(".task-item button").click()
        expect(self.page.locator(".task-item")).to_have_count(0)
        expect(self.page.locator("#task-count")).to_have_text("0")
        self.page.keyboard.press("Escape")
        expect(self.page.locator("#system-dialog")).not_to_be_visible()

    def test_settings_persist_and_reduced_motion_can_be_overridden(self):
        self.page.emulate_media(reduced_motion="reduce")
        self.load()
        expect(self.page.locator("#motion-status")).to_contain_text("SYSTEM SETTING")
        self.assertEqual(self.page.locator(".reticle").evaluate("el => getComputedStyle(el).animationName"), "none")
        self.page.locator('[data-dialog="settings"]').click()
        expect(self.page.locator("#voice-language")).to_have_value("auto")
        self.page.locator("#voice-language").select_option("ar-SA")
        self.page.locator("#motion-toggle").click()
        expect(self.page.locator("html")).to_have_attribute("data-motion", "on")
        self.page.locator("#settings-voice").click()
        self.page.locator("#close-dialog").click()
        self.page.reload(wait_until="networkidle")
        expect(self.page.locator("#deck-motion-state")).to_have_text("MOTION: ON")
        expect(self.page.locator("#deck-voice-state")).to_have_text("MUTED")
        expect(self.page.locator("#voice-language")).to_have_value("ar-SA")
        self.assertNotEqual(self.page.locator(".reticle").evaluate("el => getComputedStyle(el).animationName"), "none")
        self.page.locator('[data-dialog="diagnostics"]').click()
        self.page.locator("#motion-test").click()
        expect(self.page.locator("#system-dialog")).not_to_be_visible()
        expect(self.page.locator("#motion-status")).to_have_text("TEST MOTION · NO AUDIO")
        self.page.wait_for_function("document.getElementById('halo').style.transform !== 'scale(1, 1)'")
        self.assertFalse(any("/api/command" in request.url or "/api/tts" in request.url for request in self.requests))
        self.page.locator("#deck-motion").click()  # on -> off
        expect(self.page.locator("html")).to_have_attribute("data-motion", "off")
        self.page.wait_for_function("getComputedStyle(document.getElementById('halo')).transform === 'matrix(1, 0, 0, 1, 0, 0)'")

    def test_lip_demo_changes_real_pixels_then_returns_to_idle_without_audio(self):
        self.load()
        expect(self.page.locator("#mouth-canvas")).to_have_attribute("hidden", "")
        self.page.locator('[data-dialog="diagnostics"]').click()
        self.page.locator("#lip-test").click()
        self.page.wait_for_function("Number(document.getElementById('mouth-canvas').dataset.open) > .3")
        expect(self.page.locator("#mouth-canvas")).to_be_visible()
        self.assertEqual(self.page.locator("#mouth-canvas").get_attribute("data-renderer"), "ready")
        pixels = self.page.locator("#mouth-canvas").evaluate("el => el.getContext('2d').getImageData(0, 0, el.width, el.height).data.some((n, i) => i % 4 === 3 && n > 0)")
        self.assertTrue(pixels, "lip attributes changed but the mouth was never painted")
        self.page.wait_for_function("document.getElementById('mouth-canvas').hidden", timeout=7000)
        self.assertFalse(any("/api/tts" in request.url or "/api/command" in request.url for request in self.requests))

    def start_test_voice(self):
        self.speech_payload = voiced_fixture()
        self.page.add_init_script("""(() => {
          const NativeAudio = window.Audio;
          window.Audio = function(...args) {
            const audio = new NativeAudio(...args);
            window.testAudio = audio;
            return audio;
          };
        })();""")
        self.load()
        self.page.locator('[data-dialog="diagnostics"]').click()
        self.page.locator("#voice-test").click()
        self.page.wait_for_function("window.testAudio && Number(document.getElementById('mouth-canvas').dataset.open) > .15")

    def test_decoded_audio_drives_lips_and_real_silence_closes_them(self):
        self.start_test_voice()
        expect(self.page.locator("#lip-status")).to_contain_text("TTS WORD TIMING")
        expect(self.page.locator("#mouth-canvas")).to_be_visible()
        self.page.wait_for_function("window.testAudio.currentTime > 1.25 && window.testAudio.currentTime < 1.52 && Number(document.getElementById('mouth-canvas').dataset.open) < .004", timeout=5000)
        self.page.wait_for_function("window.testAudio.currentTime > 1.7 && Number(document.getElementById('mouth-canvas').dataset.open) > .15", timeout=5000)
        expect(self.page.locator("#mouth-canvas")).to_be_visible()
        self.page.wait_for_function("document.getElementById('activity').textContent === 'READY' && document.getElementById('mouth-canvas').hidden", timeout=5000)
        expect(self.page.locator("#lip-status")).to_have_text("LIP SYNC · IDLE")

    def test_mute_stops_actual_audio_and_immediately_restores_the_mouth(self):
        self.start_test_voice()
        self.page.locator("#mute").click()
        expect(self.page.locator("#mouth-canvas")).to_be_hidden()
        self.assertTrue(self.page.evaluate("window.testAudio.paused"))
        self.assertEqual(float(self.page.locator("#mouth-canvas").get_attribute("data-open")), 0)

    def test_lip_preference_is_persisted_and_global_motion_off_takes_priority(self):
        self.load()
        self.page.locator('[data-dialog="settings"]').click()
        self.page.locator("#lips-toggle").click()
        expect(self.page.locator("#lips-toggle")).to_have_text("LIPS: OFF")
        self.page.reload(wait_until="networkidle")
        expect(self.page.locator("#lip-status")).to_have_text("LIP SYNC · OFF")
        self.page.locator('[data-dialog="settings"]').click()
        self.page.locator("#lips-toggle").click()
        self.page.locator("#motion-toggle").click()  # auto -> on
        self.page.locator("#motion-toggle").click()  # on -> off
        self.page.locator("#close-dialog").click()
        self.page.locator('[data-dialog="diagnostics"]').click()
        self.page.locator("#lip-test").click()
        expect(self.page.locator("#mouth-canvas")).to_be_hidden()
        expect(self.page.locator("#toast")).to_contain_text("Enable Motion: On")

    def test_interface_language_switches_labels_without_translating_history(self):
        self.load()
        self.page.locator("#mute").click()
        self.page.locator("#command").fill("An original message")
        self.page.locator("#send").click()
        expect(self.page.locator(".message").last).to_contain_text("Here is literal text")
        self.page.locator('[data-dialog="settings"]').click()
        self.page.locator("#interface-language").select_option("fr")
        expect(self.page.locator("html")).to_have_attribute("lang", "fr")
        expect(self.page.locator("#dialog-title")).to_have_text("PARAMÈTRES DE L’INTERFACE")
        expect(self.page.locator("#command")).to_have_attribute("placeholder", "Écrivez votre demande…")
        expect(self.page.locator(".message").last).to_contain_text("Here is literal text")
        self.page.reload(wait_until="networkidle")
        expect(self.page.locator("html")).to_have_attribute("lang", "fr")
        expect(self.page.locator("#status-text")).to_have_text("LIAISON NEURONALE ACTIVE")
        self.page.locator('[data-dialog="settings"]').click()
        self.page.locator("#interface-language").select_option("ar")
        self.page.evaluate("document.fonts.ready")
        expect(self.page.locator("html")).to_have_attribute("dir", "rtl")
        expect(self.page.locator("#dialog-title")).to_have_text("إعدادات الواجهة")
        expect(self.page.locator("#command")).to_have_attribute("placeholder", "اكتب طلبك…")
        for width, height in [(1440, 900), (390, 844), (320, 568)]:
            self.page.set_viewport_size({"width": width, "height": height})
            self.assertFalse(self.page.evaluate("document.documentElement.scrollWidth > innerWidth"))
            self.page.locator("#reply-language").scroll_into_view_if_needed()
            expect(self.page.locator("#reply-language")).to_be_in_viewport()

    def test_detected_reply_language_reaches_actual_tts_request_and_lip_player(self):
        self.real_language_policy = True
        self.speech_payload = voiced_fixture()
        self.load()
        for text, language, locale, fragment in [("bonjour", "fr", "fr-FR", "Bonjour"), ("مرحبا", "ar", "ar-SA", "مرحباً")]:
            before = len([request for request in self.requests if request.url.endswith("/api/tts")])
            self.page.locator("#command").fill(text)
            self.page.locator("#send").click()
            expect(self.page.locator(".message").last).to_contain_text(fragment)
            self.page.wait_for_function("Number(document.getElementById('mouth-canvas').dataset.open) > .15")
            spoken = [request for request in self.requests if request.url.endswith("/api/tts")]
            self.assertGreater(len(spoken), before)
            self.assertEqual(spoken[-1].post_data_json["language"], locale)
            self.assertNotIn("voice", spoken[-1].post_data_json, "UI must not force Jenny for every language")
            self.assertEqual(self.page.evaluate("localStorage.getItem('kira.lastReplyLanguage')"), language)
            expect(self.page.locator(".message").last).to_have_attribute("dir", "auto")

    def test_explicit_french_request_persists_and_english_question_still_gets_french(self):
        self.real_language_policy = True
        self.load()
        self.page.locator("#mute").click()
        self.page.locator("#command").fill("Réponds-moi en français")
        self.page.locator("#send").click()
        expect(self.page.locator(".message").last).to_contain_text("répondrai en français")
        expect(self.page.locator("#reply-language")).to_have_value("fr")
        self.page.reload(wait_until="networkidle")
        expect(self.page.locator("#reply-language")).to_have_value("fr")
        self.page.locator("#command").fill("Hello")
        self.page.locator("#send").click()
        expect(self.page.locator(".message").last).to_contain_text("Bonjour")
        posted = [request for request in self.requests if request.url.endswith("/api/command")][-1]
        self.assertEqual(posted.post_data_json["reply_language"], "fr")

    def test_offline_state_is_explicit_and_does_not_show_fake_telemetry(self):
        self.offline = True
        self.load()
        expect(self.page.locator("#cpu")).to_have_text("—")
        expect(self.page.locator("#telemetry-live")).to_have_text("OFFLINE")
        expect(self.page.locator("#status-text")).to_have_text("BACKEND OFFLINE")
        self.page.locator("#command").fill("hello")
        self.page.locator("#send").click()
        expect(self.page.locator(".message").last).to_contain_text("backend is unavailable")
        expect(self.page.locator("#send")).to_be_enabled()
        self.assertEqual(len([request for request in self.requests if request.url.endswith("/api/command")]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
