"""KIRA local Kokoro TTS server — fully offline neural text-to-speech.

Runs in the dedicated Python 3.13 side-venv (``.kokoro-venv``) because the
Kokoro ONNX runtime cannot install in KIRA's main interpreter. The rest of
KIRA talks to it over ``http://127.0.0.1:7860``:

    GET  /health  -> {"status": "ok", "ready": bool, "device": str, ...}
    GET  /voices  -> {"voices": [...]}
    POST /tts     -> {"audio": <base64 wav>, "sample_rate": 24000, ...}

POST /tts body: {"text", "voice", "speed", "lang", "sentence_pause",
"clause_pause", "timings", "volume"}

Everything is local: the model (``models/kokoro/kokoro-v1.0.onnx``) and voice
binaries are downloaded ONCE from GitHub on first start; after that no
internet is needed. Device selection: cpu, dml (DirectML GPU), cuda, or auto
(best available), with a safe CPU fallback and no crash on failure.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
SAMPLE_RATE = 24000

_lock = threading.Lock()          # one synthesis at a time
_state_lock = threading.Lock()
_state = {"ready": False, "device": "", "error": "", "loading": True}
_kokoro = None


def log(message: str) -> None:
    print("[kokoro-server] {}".format(message), flush=True)


def download_once(path: Path, url: str) -> bool:
    """Fetch a model file once (first start only); never crash on failure."""
    if path.is_file() and path.stat().st_size > 1024 * 1024:
        return True
    log("Downloading {} -> {}".format(url, path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        with urlopen(url, timeout=120) as response, open(temporary, "wb") as sink:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            stamp = time.time()
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                sink.write(chunk)
                done += len(chunk)
                if time.time() - stamp >= 10:
                    stamp = time.time()
                    log("  {:.0f} / {:.0f} MB".format(done / 1e6, total / 1e6) if total
                        else "  {:.0f} MB".format(done / 1e6))
        if total and done != total:
            raise IOError("Incomplete download: {} of {} bytes".format(done, total))
        temporary.replace(path)
        log("Downloaded {} ({:.0f} MB)".format(path.name, path.stat().st_size / 1e6))
        return True
    except Exception as error:  # noqa: BLE001 — a failed download must not crash the server
        log("Download failed: {}".format(error))
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def build_session(model_path: Path, device: str):
    """Create the onnxruntime session for the requested device, CPU as safety net."""
    import onnxruntime as ort  # noqa: PLC0415

    model = str(model_path)
    if device == "cpu":
        return ort.InferenceSession(model, providers=["CPUExecutionProvider"]), "cpu"
    wanted = {
        "dml": ["DmlExecutionProvider", "CPUExecutionProvider"],
        "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    }.get(device)
    if wanted:
        try:
            session = ort.InferenceSession(model, providers=wanted)
            return session, session.get_providers()[0].replace("ExecutionProvider", "").lower()
        except Exception as error:  # noqa: BLE001
            log("Device {!r} unavailable ({}), falling back to CPU".format(device, error))
    # auto: let the installed distribution choose (DirectML/CUDA if present).
    # An accelerated provider that fails to load must never take the voice down:
    # fall back to a plain CPU session instead.
    try:
        from kokoro_onnx.session import create_session  # noqa: PLC0415

        session = create_session(model)
        providers = [p.replace("ExecutionProvider", "").lower() for p in session.get_providers()]
        return session, providers[0] if providers else "cpu"
    except Exception as error:  # noqa: BLE001
        log("Auto device selection failed ({}), using CPU".format(error))
        return ort.InferenceSession(model, providers=["CPUExecutionProvider"]), "cpu"


def initialize(models_dir: Path, device: str) -> None:
    """Load model + voices; runs in a background thread at startup."""
    global _kokoro
    with _state_lock:
        _state.update({"loading": True, "error": "", "ready": False})
    try:
        model_path = models_dir / "kokoro-v1.0.onnx"
        voices_path = models_dir / "voices-v1.0.bin"
        if not download_once(model_path, MODEL_URL) or not download_once(voices_path, VOICES_URL):
            raise RuntimeError(
                "Model files missing in {} — run scripts/setup_kokoro.bat once online".format(models_dir))
        from kokoro_onnx import Kokoro  # noqa: PLC0415

        started = time.time()
        session, resolved = build_session(model_path, device)
        _kokoro = Kokoro.from_session(session, str(voices_path))
        voices = len(_kokoro.get_voices())
        with _state_lock:
            _state.update({"ready": True, "device": resolved, "loading": False,
                           "error": "", "voices": voices})
        log("Ready: device={} voices={} ({:.1f}s load)".format(resolved, voices, time.time() - started))
    except Exception as error:  # noqa: BLE001 — report, stay up, stay diagnosable
        with _state_lock:
            _state.update({"ready": False, "loading": False, "error": str(error)})
        log("Initialization failed: {}".format(error))


def phoneme_timings_to_words(timings, text: str):
    """Group phoneme spans into word spans; [] when counts do not line up.

    The UI uses these for lip sync; a mismatch simply falls back to its own
    estimated timeline, so this is a best-effort bonus, never a failure.
    """
    try:
        groups = []
        current = None
        for item in timings:
            phoneme = str(getattr(item, "phoneme", "") or "")
            start, end = float(item.start), float(item.end)
            if not phoneme.strip():
                if current is not None:
                    groups.append(current)
                    current = None
                continue
            if current is None:
                current = {"start": start, "end": end}
            else:
                current["end"] = max(current["end"], end)
        if current is not None:
            groups.append(current)
        words = str(text or "").split()
        if len(groups) != len(words):
            return []
        result = []
        for word, group in zip(words, groups):
            start = max(0.0, group["start"])
            duration = max(0.0, group["end"] - start)
            if duration > 0:
                result.append({"text": word, "start": round(start, 3),
                               "duration": round(duration, 3)})
        return result
    except Exception:  # noqa: BLE001 — timings are optional
        return []


def force_cpu_rebuild(models_dir: Path) -> bool:
    """Drop an accelerated session that fails at inference and go back to CPU.

    Some GPUs advertise DirectML/CUDA but then fail on specific operators (the
    Kokoro encoder's ConvTranspose is a known one). KIRA must keep speaking, so
    the engine rebuilds once on CPU and every later request follows.
    """
    global _kokoro
    with _state_lock:
        if _state.get("device") == "cpu" or _state.get("rebuilding"):
            return False
        _state["rebuilding"] = True
    try:
        model_path = models_dir / "kokoro-v1.0.onnx"
        voices_path = models_dir / "voices-v1.0.bin"
        from kokoro_onnx import Kokoro  # noqa: PLC0415

        session, resolved = build_session(model_path, "cpu")
        _kokoro = Kokoro.from_session(session, str(voices_path))
        with _state_lock:
            _state.update({"device": resolved, "rebuilding": False,
                           "error": "GPU provider failed on this model — running on CPU"})
        log("Rebuilt the engine on CPU after a GPU inference failure")
        return True
    except Exception as error:  # noqa: BLE001
        with _state_lock:
            _state["rebuilding"] = False
        log("CPU rebuild failed: {}".format(error))
        return False


def prosody_speed(text: str, speed: float) -> float:
    """A tiny, deterministic tempo variation so consecutive sentences breathe.

    Speaking every sentence at exactly the same rate reads as a metronome. The
    offset is derived from the text itself, so the same reply always sounds the
    same (stable for caching and tests) while different sentences vary by up to
    ±3%.
    """
    import zlib  # noqa: PLC0415 — keep the module import light

    value = float(speed)
    if not 0.5 <= value <= 2.0:
        return value
    offset = (zlib.crc32(text.encode("utf-8")) % 5) - 2  # -2 … +2
    return round(max(0.5, min(2.0, value * (1.0 + offset * 0.015))), 3)


# Level matching aims at a comfortable loudness; the ceiling is reached through
# a soft knee so an overdriven word saturates instead of clipping.
TARGET_RMS = 0.10       # ≈ −20 dBFS, a normal speaking level
CEILING_KNEE = 0.70     # linear: below this the audio is untouched
CEILING = 0.95          # never louder than this, so PCM_16 cannot clip


def polish_audio(audio, sample_rate: int = SAMPLE_RATE):
    """Smooth the raw model output: level-matched, never clipped, clean edges.

    Measured on this model: a two-sentence reply peaks at 1.086, so PCM_16
    clipped it (harsh on loud words), and loudness drifts from sentence to
    sentence. Both are corrected gently — matched toward ``TARGET_RMS`` and
    then softly limited — plus micro-fades on the trimmed edges so a clip
    never starts or stops mid-cycle.
    """
    import numpy as np  # noqa: PLC0415 — runs in the side-venv only

    data = np.asarray(audio, dtype=np.float32).ravel()
    if data.size == 0:
        return data
    data = data - float(data.mean())                    # no DC offset

    rms = float(np.sqrt(np.mean(data * data)))
    if rms > 1e-6:
        gain = max(0.6, min(2.0, TARGET_RMS / rms))     # gentle correction only
        data = data * gain

    magnitude = np.abs(data)
    peak = float(magnitude.max())
    if peak > CEILING_KNEE:
        over = magnitude > CEILING_KNEE
        shaped = CEILING_KNEE + (CEILING - CEILING_KNEE) * np.tanh(
            (magnitude[over] - CEILING_KNEE) / (CEILING - CEILING_KNEE))
        data[over] = np.sign(data[over]) * shaped.astype(data.dtype)

    # Fade only into silence: a clip that begins or ends on a non-zero sample
    # clicks on playback, but no consonant may be faded away.
    audible = np.nonzero(np.abs(data) > 0.01 * max(peak, 1e-6))[0]
    if audible.size:
        lead = int(audible[0])
        fade_in = min(int(0.004 * sample_rate), lead)
        if fade_in > 1:
            data[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
        tail = data.size - 1 - int(audible[-1])
        fade_out = min(int(0.025 * sample_rate), tail)
        if fade_out > 1:
            data[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)
    return data


def encode_wav(audio, sample_rate: int) -> bytes:
    import soundfile as sf  # noqa: PLC0415

    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


class KokoroHandler(BaseHTTPRequestHandler):
    models_dir = Path(__file__).resolve().parents[1] / "models" / "kokoro"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:*")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def do_OPTIONS(self):  # local UI pages may probe the server
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.rstrip("/")
        if path == "/health":
            with _state_lock:
                payload = {"status": "ok", "model": "kokoro-v1.0", "sample_rate": SAMPLE_RATE,
                           "engine": "kokoro-onnx"}
                payload.update(_state)
            self._json(payload)
        elif path == "/voices":
            if _kokoro is None:
                self._json({"voices": [], "error": "model not ready"}, 503)
                return
            self._json({"voices": sorted(_kokoro.get_voices())})
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path.rstrip("/") != "/tts":
            self._json({"error": "Not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            request = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (ValueError, UnicodeDecodeError):
            self._json({"error": "Invalid JSON body"}, 400)
            return
        text = str(request.get("text") or "").strip()
        if not text:
            self._json({"error": "Text required"}, 400)
            return
        if _kokoro is None:
            with _state_lock:
                error = _state.get("error") or "Model is loading, retry shortly"
            self._json({"error": error}, 503)
            return

        # KIRA speaks with a female voice: never default to a male one.
        voice = str(request.get("voice") or "bf_emma")
        try:
            speed = float(request.get("speed") or 1.0)
        except (TypeError, ValueError):
            speed = 1.0
        speed = max(0.5, min(2.0, speed))
        requested_speed = speed
        speed = prosody_speed(text, speed)
        volume = request.get("volume")
        try:
            volume = None if volume is None else max(0.0, min(1.0, float(volume)))
        except (TypeError, ValueError):
            volume = None
        lang = str(request.get("lang") or "")
        if not lang:
            lang = "en-gb" if voice.startswith("b") else "en-us"
        try:
            sentence_pause = max(0.0, min(2.0, float(request.get("sentence_pause") or 0.0)))
        except (TypeError, ValueError):
            sentence_pause = 0.0
        try:
            clause_pause = max(0.0, min(1.0, float(request.get("clause_pause") or 0.0)))
        except (TypeError, ValueError):
            clause_pause = 0.0
        want_timings = bool(request.get("timings"))

        started = time.time()
        with _lock:  # serialize synthesis: requests queue instead of overlapping
            for attempt in (1, 2):
                try:
                    if want_timings:
                        audio, sample_rate, timings = _kokoro.create_timed(
                            text, voice=voice, speed=speed, lang=lang,
                            sentence_pause=sentence_pause, clause_pause=clause_pause)
                        word_timings = phoneme_timings_to_words(timings, text)
                    else:
                        audio, sample_rate = _kokoro.create(
                            text, voice=voice, speed=speed, lang=lang,
                            sentence_pause=sentence_pause, clause_pause=clause_pause)
                        word_timings = []
                    break
                except ValueError as error:
                    self._json({"error": str(error)}, 400)
                    return
                except Exception as error:  # noqa: BLE001 — synthesis failure is not a crash
                    # A GPU that loads but cannot run this model must not silence KIRA:
                    # rebuild on CPU once and retry the very same request.
                    if attempt == 1 and force_cpu_rebuild(self.models_dir):
                        log("Retrying on CPU after: {}".format(error))
                        continue
                    self._json({"error": "Synthesis failed: {}".format(error)}, 500)
                    return
        audio = polish_audio(audio, sample_rate)
        if volume is not None and volume < 1.0:
            audio = audio * volume
        wav = encode_wav(audio, sample_rate)
        self._json({
            "audio": base64.b64encode(wav).decode("ascii"),
            "format": "wav",
            "sample_rate": sample_rate,
            "duration": round(len(audio) / sample_rate, 3),
            "word_timings": word_timings,
            "device": _state.get("device", ""),
            "voice": voice,
            "speed": requested_speed,
            "generated_in": round(time.time() - started, 3),
        })


def main() -> int:
    parser = argparse.ArgumentParser(description="KIRA local Kokoro TTS server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "dml", "cuda"])
    parser.add_argument("--models-dir", default=str(Path(__file__).resolve().parents[1] / "models" / "kokoro"))
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    log("Starting on http://{}:{} (device={}, models={})".format(
        args.host, args.port, args.device, models_dir))
    threading.Thread(target=initialize, args=(models_dir, args.device), daemon=True).start()

    server = ThreadingHTTPServer((args.host, args.port), KokoroHandler)
    KokoroHandler.models_dir = models_dir
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
