"""Kokoro — fully local neural TTS (Kokoro v1.0 via ONNX, Apache-2.0 weights).

Talks to the small local server in ``scripts/kokoro_server.py`` over
``http://127.0.0.1:<port>``. The server owns the model (Python 3.13 side-venv,
``.kokoro-venv``) so the main KIRA interpreter never loads onnxruntime.

Behavior goals:
- fully offline once the model is installed;
- never crash KIRA: every failure becomes "unavailable" plus a reason;
- GPU when available and stable (DirectML/CUDA providers on the server side),
  automatic CPU otherwise.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from kira.services.tts.base import SynthesisResult, TTSProvider, TTSProviderError


def _no_window_flags() -> int:
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return creationflags
    return 0


class KokoroTTSProvider(TTSProvider):
    """Local Kokoro v1.0 voices through the internal HTTP interface."""

    name = "kokoro"

    def __init__(self, config: Any) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._available: Optional[bool] = None
        self._checked_at = 0.0
        self._voices: List[str] = []
        self._voices_count = 0
        self._error = ""
        self._device = ""
        self._process: Optional[subprocess.Popen] = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    def initialize(self) -> bool:
        """Probe the local server; start it when allowed and missing."""
        with self._lock:
            return self._initialize_locked()

    def _initialize_locked(self, force: bool = False) -> bool:
        if self._healthy():
            self._available = True
            return True
        if force or self._available is None:
            self._spawn_server_locked()
            return self._wait_ready()
        return False

    def _spawn_server_locked(self) -> None:
        config = self._config
        if not getattr(config, "autostart", True):
            return
        if self._process is not None and self._process.poll() is None:
            return
        python = Path(config.venv_python)
        script = Path(config.server_script)
        if not python.is_file() or not script.is_file():
            self._error = (
                "Kokoro server not installed (expected {} and {})".format(python, script)
            )
            return
        log_file = Path(config.models_dir).parent / "kokoro_server.log"
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handle = open(log_file, "ab", buffering=0)
            self._process = subprocess.Popen(
                [str(python), str(script),
                 "--host", "127.0.0.1", "--port", str(config.server_port()),
                 "--device", config.device, "--models-dir", config.models_dir],
                stdout=handle, stderr=subprocess.STDOUT,
                creationflags=_no_window_flags(), cwd=str(script.parent.parent),
            )
            print("[KIRA TTS] Starting local Kokoro server on {} (pid {})".format(
                config.url, self._process.pid))
        except OSError as error:
            self._error = "Could not start the Kokoro server: {}".format(error)

    def _wait_ready(self) -> bool:
        deadline = time.time() + float(getattr(self._config, "init_timeout", 300.0))
        while time.time() < deadline:
            if self._healthy():
                self._available = True
                print("[KIRA TTS] Kokoro server ready ({})".format(self._device or "cpu"))
                return True
            if self._process is not None and self._process.poll() is not None:
                self._error = "Kokoro server exited with code {}".format(self._process.returncode)
                return False
            time.sleep(1.0)
        self._error = "Kokoro server did not become ready in time"
        return False

    # ── health ───────────────────────────────────────────────────────────────

    def _health(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            request = Request(self._config.url + "/health", headers={"Accept": "application/json"})
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (URLError, OSError, ValueError):
            return None

    def _healthy(self) -> bool:
        health = self._health()
        if not health or not health.get("ready"):
            if health and health.get("error"):
                self._error = str(health["error"])
            elif health:
                self._error = "Kokoro model is still loading"
            else:
                self._error = "Kokoro server unreachable at " + str(self._config.url)
            return False
        self._error = ""
        self._device = str(health.get("device") or "cpu")
        # /health reports a voice count; the full list comes from /voices.
        count = health.get("voices")
        if isinstance(count, int):
            self._voices_count = count
        return True

    def is_available(self) -> bool:
        """Availability with a short cache so the UI can poll cheaply."""
        now = time.time()
        if self._available and now - self._checked_at < self._config.availability_ttl:
            return True
        if self._available is False and now - self._checked_at < self._config.availability_ttl:
            return False
        with self._lock:
            now = time.time()
            if self._available and now - self._checked_at < self._config.availability_ttl:
                return True
            self._checked_at = now
            self._available = self._healthy()
            return self._available

    def mark_unavailable(self, reason: str) -> None:
        """Force the next availability check after a synthesis failure."""
        with self._lock:
            self._available = False
            self._checked_at = time.time()
            self._error = reason

    # ── synthesis ────────────────────────────────────────────────────────────

    def speak(self, text: str, voice: Optional[str] = None, speed: Optional[float] = None,
              settings: Optional[Dict[str, Any]] = None) -> SynthesisResult:
        if not self.is_available() and not self.initialize():
            raise TTSProviderError(self._error or "Kokoro is unavailable")
        config = self._config
        settings = settings or {}
        payload: Dict[str, Any] = {
            "text": text,
            "voice": voice or config.voice,
            "speed": round(float(speed if speed is not None else config.speed), 3),
            "timings": True,
        }
        for key in ("lang", "sentence_pause", "clause_pause"):
            if settings.get(key) is not None:
                payload[key] = settings[key]
        request = Request(
            config.url + "/tts",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=float(settings.get("timeout") or 120.0)) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (URLError, OSError, ValueError) as error:
            self.mark_unavailable("Kokoro synthesis failed: {}".format(error))
            raise TTSProviderError(str(error)) from error
        if data.get("error"):
            self.mark_unavailable(str(data["error"]))
            raise TTSProviderError(str(data["error"]))
        try:
            audio = base64.b64decode(data.get("audio") or "")
        except (ValueError, TypeError) as error:
            raise TTSProviderError("Kokoro returned malformed audio") from error
        if not audio:
            raise TTSProviderError("Kokoro returned no audio")
        voice_used = str(data.get("voice") or payload["voice"])
        british = voice_used.startswith("b")
        return SynthesisResult(
            audio=audio,
            format="wav",
            sample_rate=int(data.get("sample_rate") or 24000),
            duration=float(data.get("duration") or 0.0),
            voice=voice_used,
            engine=self.name,
            word_timings=list(data.get("word_timings") or []),
            device=str(data.get("device") or self._device),
            language="en",
            locale="en-GB" if british else "en-US",
        )

    def stop(self) -> None:
        """The server synthesizes per request; nothing long-lived to abort."""

    def pause(self) -> None:
        """Playback is owned by the UI; nothing to do server-side."""

    def resume(self) -> None:
        """Playback is owned by the UI; nothing to do server-side."""

    # ── voices ───────────────────────────────────────────────────────────────

    def get_voices(self) -> List[str]:
        if not self._voices:
            try:
                request = Request(self._config.url + "/voices", headers={"Accept": "application/json"})
                with urlopen(request, timeout=2.0) as response:
                    data = json.loads(response.read().decode("utf-8"))
                # KIRA speaks with female voices only: keep male voices (am_/bm_)
                # out of the picker.
                self._voices = [str(v) for v in data.get("voices") or []
                                if str(v)[:3].lower() not in ("am_", "bm_")]
            except (URLError, OSError, ValueError):
                self._voices = []
        return list(self._voices)

    def describe(self) -> Dict[str, Any]:
        return {
            "engine": self.name,
            "available": bool(self._available),
            "url": self._config.url,
            "device": self._device,
            "error": self._error,
            "voices": len(self._voices) or self._voices_count,
        }

    def shutdown(self) -> None:
        """Stop the server only if this process spawned it."""
        process = self._process
        self._process = None
        # Invalidate the availability cache: the engine is being stopped on
        # purpose, the next probe must re-check reality.
        self._available = False
        self._checked_at = 0.0
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
