"""Voice layer tests: speech formatter, config, manager and API routes.

No network, no Kokoro server, no Edge service: every engine is a fake provider.
"""
import base64
import io
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# Imported while the suite is still loading: several tests patch sys.modules,
# and on Windows a second import of numpy's extension module raises
# "cannot load module more than once per process".
import numpy as np

import kira_api  # noqa: E402 — the shim puts src/ on sys.path for the imports below
from kira.services.tts import base as tts_base
from kira.services.tts.config import TTSConfig, load_config
from kira.services.tts.manager import MODE_PROFILES, TTSManager
from kira.services.tts.speech_formatter import format_speech, split_sentences, spoken_sentences


class FakeProvider(tts_base.TTSProvider):
    def __init__(self, name, available=True, error=None, audio=b"audio-bytes"):
        self.name = name
        self.available = available
        self.error = error
        self.audio = audio
        self.calls = []
        self.stopped = 0
        self.paused = 0
        self.resumed = 0

    def initialize(self):
        return self.available

    def speak(self, text, voice=None, speed=None, settings=None):
        self.calls.append({"text": text, "voice": voice, "speed": speed, "settings": settings})
        if self.error:
            raise tts_base.TTSProviderError(self.error)
        return tts_base.SynthesisResult(
            audio=self.audio, format="wav", voice=voice or "", engine=self.name,
            word_timings=[{"text": "one", "start": 0.0, "duration": 0.4}],
            device="cpu", language="en", locale="en-GB")

    def stop(self):
        self.stopped += 1

    def pause(self):
        self.paused += 1

    def resume(self):
        self.resumed += 1

    def is_available(self):
        return self.available

    def get_voices(self):
        return ["voice_a", "voice_b"]


def make_manager(config=None):
    manager = TTSManager(config or TTSConfig())
    manager._providers = {"kokoro": FakeProvider("kokoro"), "edge": FakeProvider("edge")}
    return manager


class SpeechFormatterTests(unittest.TestCase):
    def test_spec_example_becomes_short_spoken_sentences(self):
        raw = ("I have analyzed your system and based on the information available I believe that "
               "the reason your computer is slow is because Chrome is consuming 4.2 GB of RAM "
               "while Discord is consuming 900 MB and several background applications are also running.")
        sentences = spoken_sentences(raw)
        self.assertEqual(sentences[0], "I have analyzed your system.")
        self.assertEqual(sentences[-1], "Discord is consuming 900 MB and several background applications are also running.")
        self.assertIn("4.2 GB", " ".join(sentences))  # numbers survive
        self.assertTrue(all(len(sentence.split()) <= 24 for sentence in sentences))

    def test_markdown_code_and_tables_are_never_read_aloud(self):
        raw = ("## Report\n\n| Process | RAM |\n|---------|-----|\n| Chrome | 4 GB |\n\n"
               "```powershell\nGet-Process | Sort-Object CPU\n```\n\n"
               "Run `npm install` then see https://example.com for details.")
        spoken = format_speech(raw)
        self.assertNotIn("|", spoken)
        self.assertNotIn("```", spoken)
        self.assertNotIn("Get-Process", spoken)
        self.assertNotIn("http", spoken)
        self.assertIn("npm install", spoken)
        self.assertIn("link", spoken)

    def test_cliches_and_sir_are_dropped(self):
        spoken = format_speech("Certainly, sir. The update completed successfully. Of course.")
        self.assertEqual(spoken, "The update completed successfully.")

    def test_keep_sir_configuration_is_respected(self):
        spoken = format_speech("Understood, sir. The report is ready.", keep_sir=True)
        self.assertIn("sir", spoken)

    def test_exclamations_become_periods_and_replies_are_capped(self):
        spoken = spoken_sentences("One! Two! Three! Four! Five! Six!", max_sentences=4)
        self.assertEqual(spoken, ["One.", "Two.", "Three.", "Four."])

    def test_split_sentences_keeps_decimals_and_abbreviations(self):
        self.assertEqual(
            split_sentences("Version 4.2 is out. Mr. Smith agrees."),
            ["Version 4.2 is out.", "Mr. Smith agrees."])

    def test_long_sentence_without_punctuation_is_not_mangled(self):
        raw = ("The analysis shows that everything is running within normal parameters and no "
               "further action is required at this time")
        spoken = spoken_sentences(raw)
        self.assertTrue(spoken)
        self.assertTrue(all(sentence.endswith(".") for sentence in spoken))


class TTSConfigTests(unittest.TestCase):
    def test_defaults_match_the_kokoro_spec(self):
        config = load_config(environ={})
        self.assertTrue(config.enabled)
        self.assertEqual(config.engine, "kokoro")
        self.assertEqual(config.url, "http://127.0.0.1:7860")
        self.assertEqual(config.voice, "af_heart")
        self.assertEqual(config.speed, 0.94)
        self.assertEqual(config.mode, "normal")
        self.assertEqual(config.device, "auto")

    def test_environment_values_are_read_and_clamped(self):
        config = load_config(environ={
            "KIRA_TTS_ENABLED": "false", "KIRA_TTS_ENGINE": "edge", "KIRA_TTS_SPEED": "9",
            "KIRA_TTS_MODE": "ALERT", "KIRA_TTS_VOLUME": "0.4", "KIRA_TTS_MAX_SENTENCES": "99",
            "KIRA_TTS_KEEP_SIR": "1", "KIRA_TTS_AUDIO_DEVICE": "speakers-headset",
        })
        self.assertFalse(config.enabled)
        self.assertEqual(config.engine, "edge")
        self.assertEqual(config.speed, 2.0)
        self.assertEqual(config.mode, "alert")
        self.assertEqual(config.volume, 0.4)
        self.assertEqual(config.max_sentences, 24)
        self.assertTrue(config.keep_sir)
        self.assertEqual(config.audio_device, "speakers-headset")
        self.assertEqual(config.summary()["audio_device"], "speakers-headset")

    def test_audio_device_defaults_to_the_system_output(self):
        self.assertEqual(load_config(environ={}).audio_device, "")
        self.assertEqual(TTSConfig().summary()["audio_device"], "")

    def test_unknown_engine_and_mode_fall_back_to_safe_defaults(self):
        config = TTSConfig(engine="nope", mode="dramatic")
        self.assertEqual(config.engine, "kokoro")
        self.assertEqual(config.mode, "normal")

    def test_server_port_parsing(self):
        self.assertEqual(TTSConfig(url="http://127.0.0.1:7860").server_port(), 7860)
        self.assertEqual(TTSConfig(url="http://127.0.0.1").server_port(), 7860)
        self.assertEqual(TTSConfig(url="http://127.0.0.1:9001/").server_port(), 9001)


class TTSManagerTests(unittest.TestCase):
    def test_mode_profile_controls_speed_and_pauses(self):
        manager = make_manager()
        payload = manager.speak("All systems are online.", mode="system", format_text=False)
        self.assertTrue(payload["success"])
        call = manager._providers["kokoro"].calls[0]
        self.assertEqual(call["speed"], MODE_PROFILES["system"]["speed"])
        self.assertEqual(call["settings"]["sentence_pause"], MODE_PROFILES["system"]["sentence_pause"])
        self.assertEqual(payload["mode"], "system")
        self.assertEqual(payload["engine"], "kokoro")

    def test_formatted_text_reaches_the_engine(self):
        manager = make_manager()
        manager.speak("**Bold.** `code` and [link](https://x.y).", format_text=True)
        spoken = manager._providers["kokoro"].calls[0]["text"]
        self.assertNotIn("**", spoken)
        self.assertNotIn("https", spoken)

    def test_unavailable_kokoro_falls_back_to_edge(self):
        manager = make_manager()
        manager._providers["kokoro"].available = False
        payload = manager.speak("Hello there.", format_text=False)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["engine"], "edge")
        self.assertEqual(manager._providers["edge"].calls[0]["text"], "Hello there.")

    def test_kokoro_failure_mid_synthesis_falls_back_to_edge(self):
        manager = make_manager()
        manager._providers["kokoro"].error = "server exploded"
        payload = manager.speak("Hello there.", format_text=False)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["engine"], "edge")
        self.assertEqual(payload["fallback_reason"], "server exploded")

    def test_no_engine_available_reports_unavailable_without_raising(self):
        manager = make_manager()
        manager._providers["kokoro"].available = False
        manager._providers["edge"].available = False
        payload = manager.speak("Hello.", format_text=False)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "tts_unavailable")

    def test_disabled_voice_layer_returns_tts_disabled(self):
        manager = make_manager(TTSConfig(enabled=False))
        payload = manager.speak("Hello.", format_text=False)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "tts_disabled")
        self.assertEqual(manager.status()["state"], "offline")

    def test_non_english_replies_go_to_edge(self):
        manager = make_manager()
        payload = manager.speak("Bonjour, je suis Kira.", language="fr-FR", format_text=False)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["engine"], "edge")
        self.assertFalse(manager._providers["kokoro"].calls)

    def test_detected_language_beats_an_english_voice_request(self):
        # An English Kokoro voice must never read a French reply with English
        # phonemes, even when the caller asks for en-US (voice-derived locale).
        manager = make_manager()
        payload = manager.speak(
            "L'analyse est terminée. La memoire est legerement elevee, principalement a cause de Chrome.",
            voice="bm_george", language="en-US", format_text=False)
        self.assertEqual(payload["engine"], "edge")
        self.assertFalse(manager._providers["kokoro"].calls)

    def test_english_replies_still_use_kokoro_with_an_auto_locale(self):
        manager = make_manager()
        payload = manager.speak("The scan is complete and everything looks normal.", format_text=False)
        self.assertEqual(payload["engine"], "kokoro")

    def test_explicit_edge_voice_name_goes_to_edge(self):
        manager = make_manager()
        payload = manager.speak("Hello.", voice="jenny", format_text=False)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["engine"], "edge")

    def test_plan_returns_sentences_and_profile(self):
        manager = make_manager()
        plan = manager.plan("One. Two. Three. Four. Five.")
        self.assertEqual(plan["sentences"], ["One.", "Two.", "Three.", "Four."])
        self.assertEqual(plan["profile"]["speed"], 0.94)
        self.assertEqual(plan["spoken"], "One.\n\nTwo.\n\nThree.\n\nFour.")

    def test_stop_and_pause_reach_every_provider(self):
        manager = make_manager()
        manager.speak("Hello.", format_text=False)
        manager.stop_speaking()
        manager.pause_speaking()
        manager.resume_speaking()
        for provider in manager._providers.values():
            self.assertEqual(provider.stopped, 1)
            self.assertEqual(provider.paused, 1)
            self.assertEqual(provider.resumed, 1)
        self.assertFalse(manager.is_speaking())
        self.assertFalse(manager.paused)

    def test_status_reports_online_offline_and_speaking(self):
        manager = make_manager()
        self.assertEqual(manager.status()["state"], "online")
        self.assertEqual(manager.status()["engine"], "kokoro")
        manager._providers["kokoro"].available = False
        manager._providers["edge"].available = False
        status = manager.status()
        self.assertEqual(status["state"], "offline")
        self.assertEqual(status["label"], "KIRA VOICE — OFFLINE")

    def test_set_mode_validates_and_stores(self):
        manager = make_manager()
        self.assertTrue(manager.set_mode("alert")["success"])
        self.assertEqual(manager.mode, "alert")
        self.assertFalse(manager.set_mode("dramatic")["success"])


class FakeManager:
    def __init__(self):
        self.stopped = 0
        self.modes = []
        self.voice_provider = FakeProvider("kokoro")

    def speak(self, text, **options):
        return {"success": True, "audio": base64.b64encode(b"wave").decode(), "format": "wav",
                "word_timings": [], "engine": "kokoro", "mode": options.get("mode") or "normal",
                "spoken_text": text, "sentences": [text], "voice": "bm_george", "speed": 0.94,
                "device": "cpu", "duration": 0.5}

    def plan(self, text, mode=None, max_sentences=None):
        sentences = spoken_sentences(text, mode or "normal", max_sentences)
        return {"mode": mode or "normal", "sentences": sentences, "spoken": "\n\n".join(sentences),
                "profile": MODE_PROFILES["normal"]}

    def status(self):
        return {"enabled": True, "state": "online", "label": "KIRA VOICE — ONLINE", "speaking": False,
                "engine": "kokoro", "device": "cpu", "mode": "normal", "voices": ["bm_george"],
                "engines": {}, "config": {}, "error": ""}

    def stop_speaking(self):
        self.stopped += 1

    def pause_speaking(self):
        pass

    def resume_speaking(self):
        pass

    def is_speaking(self):
        return False

    @property
    def paused(self):
        return False

    def set_mode(self, mode):
        self.modes.append(mode)
        return {"success": True, "mode": mode}

    def provider(self, name):
        return self.voice_provider if name == "kokoro" else None

    def warmup_async(self):
        pass


class TTSApiTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), kira_api.KiraAPIHandler)
        worker = Thread(target=self.server.serve_forever, daemon=True)
        worker.start()

        def stop_server():
            self.server.shutdown()
            self.server.server_close()
            worker.join()

        self.addCleanup(stop_server)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.manager = FakeManager()
        patcher = patch("kira.services.tts.get_manager", return_value=self.manager)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, path):
        with urlopen(f"{self.base}{path}", timeout=3) as response:
            return json.load(response)

    def post(self, path, body):
        request = Request(f"{self.base}{path}", data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_status_route_reports_the_voice_layer(self):
        payload = self.get("/api/tts/status")
        self.assertEqual(payload["state"], "online")
        self.assertEqual(payload["engine"], "kokoro")

    def test_voices_route_lists_engines(self):
        payload = self.get("/api/tts/voices")
        self.assertIn("kokoro", payload["voices"])
        self.assertEqual(payload["voices"]["kokoro"], ["voice_a", "voice_b"])

    def test_plan_route_returns_spoken_sentences(self):
        payload = self.post("/api/tts/plan", {"text": "One. Two. Three. Four. Five."})
        self.assertEqual(payload["sentences"], ["One.", "Two.", "Three.", "Four."])

    def test_stop_and_mode_routes_reach_the_manager(self):
        self.assertTrue(self.post("/api/tts/stop", {})["success"])
        self.assertEqual(self.manager.stopped, 1)
        payload = self.post("/api/tts/mode", {"mode": "serious"})
        self.assertTrue(payload["success"])
        self.assertEqual(self.manager.modes, ["serious"])

    def test_tts_route_keeps_the_audio_payload_shape(self):
        payload = self.post("/api/tts", {"text": "Hello Kira.", "engine": "kokoro"})
        self.assertTrue(payload["success"])
        self.assertEqual(base64.b64decode(payload["audio"]), b"wave")
        self.assertEqual(payload["format"], "wav")

    def test_tts_route_requires_text_and_valid_language(self):
        with self.assertRaises(HTTPError) as error:
            self.post("/api/tts", {"text": "   "})
        self.assertEqual(error.exception.code, 400)
        with self.assertRaises(HTTPError) as error:
            self.post("/api/tts", {"text": "Hello", "language": "en; rm -rf"})
        self.assertEqual(error.exception.code, 400)

    def test_tts_route_uses_the_real_manager_for_edge(self):
        patcher = patch("kira.services.tts.get_manager", side_effect=lambda: TTSManager(TTSConfig(engine="edge")))
        patcher.start()
        self.addCleanup(patcher.stop)
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "edge.mp3"
            audio.write_bytes(b"fixture audio")
            with patch("kira_tts.generate_speech", return_value=str(audio)) as generate:
                payload = self.post("/api/tts", {"text": "Bonjour, je suis Kira.", "language": "fr-FR", "voice": "jenny"})
        self.assertTrue(payload["success"])
        self.assertEqual(payload["engine"], "edge")
        self.assertEqual(payload["format"], "mp3")
        self.assertEqual(payload["language"], "fr")
        self.assertEqual(payload["locale"], "fr-FR")
        self.assertEqual(generate.call_args.args[1], "fr-FR-DeniseNeural")


class VoiceSmoothnessTests(unittest.TestCase):
    """The local engine must sound smooth: no clipping, steady level, human pacing."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "kokoro_server", Path(__file__).resolve().parents[1] / "scripts" / "kokoro_server.py")
        cls.server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.server)

    def test_overdriven_audio_is_soft_limited_and_never_clipped(self):
        audio = np.full(4800, 1e-4, dtype=np.float32)        # quiet head and tail
        speech = (0.4 * np.sin(2 * np.pi * 450 * np.arange(1920) / 24000)).astype(np.float32)
        audio[240:2160] = speech
        audio[1500] = 1.086                                   # measured model overshoot
        polished = self.server.polish_audio(audio, 24000)
        self.assertEqual(len(polished), len(audio))
        # PCM_16 clipped this before: the raw model peaks above full scale.
        self.assertLessEqual(float(np.abs(polished).max()), self.server.CEILING + 1e-6)
        self.assertLess(float(np.abs(polished).max()), 1.0)
        self.assertAlmostEqual(float(polished.mean()), 0.0, delta=0.01)

    def test_a_quiet_clip_is_brought_up_without_being_blown_up(self):
        quiet = (0.05 * np.sin(2 * np.pi * 220 * np.arange(4800) / 24000)).astype(np.float32)
        polished = self.server.polish_audio(quiet, 24000)
        self.assertGreater(float(np.abs(polished).max()), float(np.abs(quiet).max()))
        self.assertLessEqual(float(np.abs(polished).max()), self.server.CEILING + 1e-6)

    def test_tempo_varies_between_sentences_and_stays_reproducible(self):
        sentences = ["First sentence.", "Second sentence.", "Third sentence.",
                     "Fourth sentence.", "Fifth sentence.", "Sixth sentence."]
        speeds = [self.server.prosody_speed(text, 0.94) for text in sentences]
        for value in speeds:
            self.assertGreaterEqual(value, 0.94 * 0.96)
            self.assertLessEqual(value, 0.94 * 1.04)
        self.assertGreater(len(set(speeds)), 1)  # consecutive sentences do not march in step
        # Same text, same tempo: a reply always sounds the same.
        self.assertEqual(self.server.prosody_speed(sentences[0], 0.94), speeds[0])
        # A caller asking for a tempo outside the supported range is not altered.
        self.assertEqual(self.server.prosody_speed("Whatever", 9.0), 9.0)


class FemaleVoiceOnlyTests(unittest.TestCase):
    """KIRA speaks with a female voice: male voices are never selected or listed."""

    def test_male_kokoro_voice_falls_back_to_the_configured_female_voice(self):
        manager = make_manager()
        payload = manager.speak("The scan is complete.", voice="am_michael", format_text=False)
        self.assertTrue(payload["success"])
        self.assertEqual(manager._providers["kokoro"].calls[0]["voice"], TTSConfig().voice)

    def test_female_kokoro_voice_reaches_the_engine_unchanged(self):
        manager = make_manager()
        manager.speak("The scan is complete.", voice="af_heart", format_text=False)
        self.assertEqual(manager._providers["kokoro"].calls[0]["voice"], "af_heart")

    def test_male_edge_voice_name_still_routes_to_edge(self):
        manager = make_manager()
        payload = manager.speak("Hello there.", voice="henri", format_text=False)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["engine"], "edge")
        self.assertFalse(manager._providers["kokoro"].calls)

    def test_male_edge_voices_are_hidden_from_the_voice_catalog(self):
        from kira.services import kira_tts

        self.assertTrue(kira_tts.MALE_VOICES)
        self.assertFalse(set(kira_tts.MALE_VOICES) & set(kira_tts.FEMALE_VOICES))
        self.assertNotIn("henri", kira_tts.FEMALE_VOICES)
        self.assertEqual(kira_tts.select_neural_voice("Bonjour, je vais bien.", "henri", "fr"),
                         "fr-FR-DeniseNeural")
        self.assertNotIn("Guy", kira_tts.select_neural_voice("Hello there.", "guy", "en"))

    def test_male_voices_are_never_offered_by_the_kokoro_picker(self):
        from kira.services.tts.kokoro import KokoroTTSProvider

        body = io.BytesIO(json.dumps({"voices": ["af_heart", "am_michael", "bf_emma", "bm_george"]}).encode())
        with patch("kira.services.tts.kokoro.urlopen", return_value=body):
            voices = KokoroTTSProvider(TTSConfig()).get_voices()
        self.assertEqual(voices, ["af_heart", "bf_emma"])

    def test_installed_windows_voice_prefers_a_female_one(self):
        from kira.core import kira_language

        david = SimpleNamespace(id="TTS_MS_EN-US_DAVID", name="Microsoft David Desktop", languages=[])
        zira = SimpleNamespace(id="TTS_MS_EN-US_ZIRA", name="Microsoft Zira Desktop", languages=[])
        self.assertIs(kira_language.select_installed_voice([david, zira], "en-US"), zira)
        # A lone male voice is still usable: silence would be worse.
        self.assertIs(kira_language.select_installed_voice([david], "en-US"), david)


if __name__ == "__main__":
    unittest.main()
