"""Central KIRA voice configuration — the single source of truth.

Every tunable lives in one section of ``.env`` (or the process environment):

    KIRA_TTS_ENABLED=true          # voice layer on/off
    KIRA_TTS_ENGINE=kokoro         # primary engine (edge is the automatic fallback)
    KIRA_TTS_URL=http://127.0.0.1:7860
    KIRA_TTS_VOICE=af_heart
    KIRA_TTS_SPEED=0.94
    KIRA_TTS_MODE=normal
    KIRA_TTS_DEVICE=auto           # auto | cpu | dml | cuda
    KIRA_TTS_VOLUME=1.0
    KIRA_TTS_AUDIO_DEVICE=         # empty = system default output device
    KIRA_TTS_INTERRUPT=stop        # what a new user utterance does to speech
    KIRA_TTS_AUTOSTART=1           # let KIRA launch the local Kokoro server
    KIRA_TTS_MAX_SENTENCES=4       # spoken sentences per reply (0 = unlimited)
    KIRA_TTS_KEEP_SIR=0            # keep "Sir" vocatives in speech

No other KIRA module may read these variables directly — they import
:func:`load_config` instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, Optional

from kira import paths

MODES = ("normal", "alert", "serious", "system", "success")
ENGINES = ("kokoro", "edge")

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _as_bool(value: Optional[str], default: bool) -> bool:
    if value is None or str(value).strip() == "":
        return default
    text = str(value).strip().lower()
    if text in _TRUTHY:
        return True
    if text in _FALSY:
        return False
    return default


def _as_float(value: Optional[str], default: float, low: float, high: float) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _as_int(value: Optional[str], default: int, low: int, high: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


@dataclass
class TTSConfig:
    """Resolved voice settings. ``from_env`` fills it from KIRA_TTS_* keys."""

    enabled: bool = True
    engine: str = "kokoro"
    url: str = "http://127.0.0.1:7860"
    voice: str = "af_heart"
    speed: float = 0.94
    mode: str = "normal"
    device: str = "auto"
    volume: float = 1.0
    audio_device: str = ""
    interruption: str = "stop"
    autostart: bool = True
    max_sentences: int = 4
    keep_sir: bool = False
    availability_ttl: float = 10.0
    init_timeout: float = 300.0
    venv_python: str = field(default_factory=lambda: str(
        paths.root_path(".kokoro-venv", "Scripts", "python.exe")))
    server_script: str = field(default_factory=lambda: str(
        paths.root_path("scripts", "kokoro_server.py")))
    models_dir: str = field(default_factory=lambda: str(
        paths.root_path("models", "kokoro")))
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.engine = str(self.engine).lower().strip()
        if self.engine not in ENGINES:
            self.engine = "kokoro"
        self.mode = str(self.mode).lower().strip()
        if self.mode not in MODES:
            self.mode = "normal"
        self.device = str(self.device).lower().strip() or "auto"
        self.interruption = str(self.interruption).lower().strip() or "stop"
        self.url = str(self.url).strip().rstrip("/") or "http://127.0.0.1:7860"

    def with_overrides(self, **overrides: Any) -> "TTSConfig":
        """Return a copy with only the given fields replaced (per-request tweaks)."""
        return replace(self, **overrides)

    def server_port(self) -> int:
        """Port of the local Kokoro server, parsed from ``url``."""
        from urllib.parse import urlparse

        try:
            port = urlparse(self.url).port
        except ValueError:
            port = None
        return port or 7860

    def summary(self) -> Dict[str, Any]:
        """Safe description for the UI (no local paths)."""
        return {
            "enabled": self.enabled,
            "engine": self.engine,
            "url": self.url,
            "voice": self.voice,
            "speed": self.speed,
            "mode": self.mode,
            "device": self.device,
            "volume": self.volume,
            "audio_device": self.audio_device,
            "interruption": self.interruption,
            "max_sentences": self.max_sentences,
            "keep_sir": self.keep_sir,
        }


def load_config(environ: Optional[Mapping[str, str]] = None) -> TTSConfig:
    """Build a TTSConfig from the environment (``.env`` first, then os.environ)."""
    env: Dict[str, str] = dict(os.environ)
    if environ is not None:
        env.update({str(k): str(v) for k, v in environ.items()})
    else:
        # The desktop launcher usually loads .env already; reading it here keeps
        # the voice layer correct even when KIRA starts another way.
        env_file = paths.root_path(".env")
        try:
            if env_file.is_file():
                for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if not line or line.startswith(("#", "[", ";")) or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key.startswith("KIRA_TTS") and key not in env:
                        env[key] = value
        except OSError:
            pass

    def pick(name: str, default: str = "") -> str:
        return env.get(name, default)

    return TTSConfig(
        enabled=_as_bool(pick("KIRA_TTS_ENABLED"), True),
        engine=pick("KIRA_TTS_ENGINE", "kokoro").lower(),
        url=pick("KIRA_TTS_URL", "http://127.0.0.1:7860"),
        voice=pick("KIRA_TTS_VOICE", "af_heart").strip() or "af_heart",
        speed=_as_float(pick("KIRA_TTS_SPEED"), 0.94, 0.5, 2.0),
        mode=pick("KIRA_TTS_MODE", "normal").lower(),
        device=pick("KIRA_TTS_DEVICE", "auto").lower(),
        volume=_as_float(pick("KIRA_TTS_VOLUME"), 1.0, 0.0, 1.0),
        audio_device=pick("KIRA_TTS_AUDIO_DEVICE", "").strip(),
        interruption=pick("KIRA_TTS_INTERRUPT", "stop").lower(),
        autostart=_as_bool(pick("KIRA_TTS_AUTOSTART"), True),
        max_sentences=_as_int(pick("KIRA_TTS_MAX_SENTENCES"), 4, 0, 24),
        keep_sir=_as_bool(pick("KIRA_TTS_KEEP_SIR"), False),
        availability_ttl=_as_float(pick("KIRA_TTS_TTL"), 10.0, 0.5, 120.0),
        init_timeout=_as_float(pick("KIRA_TTS_INIT_TIMEOUT"), 300.0, 5.0, 1800.0),
        venv_python=pick("KIRA_TTS_PYTHON") or str(
            paths.root_path(".kokoro-venv", "Scripts", "python.exe")),
        server_script=pick("KIRA_TTS_SERVER") or str(
            paths.root_path("scripts", "kokoro_server.py")),
        models_dir=pick("KIRA_TTS_MODELS") or str(
            paths.root_path("models", "kokoro")),
    )
