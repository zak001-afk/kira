"""TTS timing/cache tests: no network, Edge service, audio device or desktop agent."""
import base64
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

import kira_api
import kira_tts


class TTSTimingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.events = [
            {"type": "WordBoundary", "offset": 2_000_000, "duration": 4_000_000, "text": "Hello"},
            {"type": "audio", "data": b"first-audio-chunk"},
            {"type": "WordBoundary", "offset": 9_000_000, "duration": 5_000_000, "text": "Kira"},
            {"type": "audio", "data": b"second-audio-chunk"},
        ]
        self.calls = []
        outer = self

        class Communicate:
            def __init__(self, text, voice, **kwargs):
                outer.calls.append((text, voice, kwargs))

            async def stream(self):
                for event in outer.events:
                    if isinstance(event, Exception):
                        raise event
                    yield event

        for name, value in [("CACHE_DIR", self.path), ("EDGE_TTS_AVAILABLE", True),
                            ("edge_tts", SimpleNamespace(Communicate=Communicate))]:
            replacement = patch.object(kira_tts, name, value, create=True)
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_stream_keeps_audio_and_converts_ticks_to_seconds(self):
        audio_path = kira_tts.generate_speech("Hello Kira", "jenny")
        self.assertIsNotNone(audio_path)
        self.assertEqual(Path(audio_path).read_bytes(), b"first-audio-chunksecond-audio-chunk")
        self.assertEqual(kira_tts.get_word_timings(audio_path), [
            {"text": "Hello", "start": 0.2, "duration": 0.4},
            {"text": "Kira", "start": 0.9, "duration": 0.5},
        ])
        self.assertEqual(self.calls[0][2], {"boundary": "WordBoundary"})
        self.assertFalse(list(self.path.glob("*.part")))

    def test_cached_audio_reuses_the_matching_word_times(self):
        one = kira_tts.generate_speech("Hello Kira")
        two = kira_tts.generate_speech("Hello Kira")
        self.assertEqual(one, two)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(kira_tts.get_word_timings(two)), 2)

    def test_older_edge_tts_without_boundary_argument_is_supported(self):
        events = self.events

        class OldCommunicate:
            def __init__(self, text, voice):
                pass

            async def stream(self):
                for event in events:
                    yield event

        with patch.object(kira_tts.edge_tts, "Communicate", OldCommunicate):
            audio = kira_tts.generate_speech("Hello")
        self.assertIsNotNone(audio)
        self.assertEqual(len(kira_tts.get_word_timings(audio)), 2)

    def test_no_word_events_still_produces_playable_audio(self):
        self.events = [{"type": "audio", "data": b"complete-audio"}]
        audio = kira_tts.generate_speech("Hello")
        self.assertEqual(Path(audio).read_bytes(), b"complete-audio")
        self.assertEqual(kira_tts.get_word_timings(audio), [])

    def test_failed_stream_never_leaves_a_partial_cached_mp3(self):
        self.events = [{"type": "audio", "data": b"truncated"}, RuntimeError("connection lost")]
        self.assertIsNone(kira_tts.generate_speech("Hello"))
        self.assertEqual(list(self.path.iterdir()), [])
        self.events = [{"type": "audio", "data": b"complete"}]
        audio = kira_tts.generate_speech("Hello")
        self.assertEqual(Path(audio).read_bytes(), b"complete")
        self.assertEqual(len(self.calls), 2)

    def test_empty_audio_is_not_cached(self):
        self.events = [{"type": "WordBoundary", "offset": 0, "duration": 3_000_000, "text": "Hello"}]
        self.assertIsNone(kira_tts.generate_speech("Hello"))
        self.assertEqual(list(self.path.iterdir()), [])

    def test_malformed_and_older_metadata_safely_fall_back(self):
        audio = self.path / "older.mp3"
        audio.write_bytes(b"audio")
        metadata = audio.with_suffix(".timings.json")
        self.assertEqual(kira_tts.get_word_timings(audio), [])
        for payload in ["invalid JSON", "[]", '{"version":2}', '{"version":1,"units":"ticks","words":[]}']:
            metadata.write_text(payload)
            self.assertEqual(kira_tts.get_word_timings(audio), [])
        metadata.write_text(json.dumps({"version": 1, "units": "seconds", "words": [
            {"text": "valid", "start": 0.2, "duration": 0.3},
            {"text": "nan", "start": float("nan"), "duration": 0.2},
            {"text": "negative", "start": 0.6, "duration": -2},
            {"text": "backwards", "start": 0.1, "duration": 0.3},
        ]}))
        self.assertEqual(kira_tts.get_word_timings(audio), [{"text": "valid", "start": 0.2, "duration": 0.3}])

    def test_api_includes_audio_and_optional_word_timing_without_schema_break(self):
        audio = kira_tts.generate_speech("Hello Kira")
        server = ThreadingHTTPServer(("127.0.0.1", 0), kira_api.KiraAPIHandler)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.object(kira_tts, "generate_speech", return_value=audio):
                request = Request(f"http://127.0.0.1:{server.server_port}/api/tts", data=b'{"text":"Hello Kira"}', headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=3) as response:
                    payload = json.load(response)
            self.assertTrue(payload["success"])
            self.assertEqual(payload["format"], "mp3")
            self.assertEqual(base64.b64decode(payload["audio"]), Path(audio).read_bytes())
            self.assertEqual(payload["word_timings"], kira_tts.get_word_timings(audio))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_cache_cleanup_removes_corresponding_timing_sidecar(self):
        audio = Path(kira_tts.generate_speech("Hello"))
        metadata = audio.with_suffix(".timings.json")
        expired = time.time() - 49 * 3600
        os.utime(audio, (expired, expired))
        kira_tts.cleanup_cache()
        self.assertFalse(audio.exists())
        self.assertFalse(metadata.exists())


if __name__ == "__main__":
    unittest.main()
