"""Abstract TTS contract — the only interface KIRA's core depends on.

Engines (Kokoro, Edge, Piper, XTTS...) implement this class. Nothing else in
KIRA imports an engine directly, so swapping one is a configuration change,
never a rewrite.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class TTSProviderError(RuntimeError):
    """Raised by providers when synthesis cannot be performed."""


@dataclass
class SynthesisResult:
    """One finished piece of synthesized audio.

    ``audio`` holds the encoded bytes (wav/mp3) ready for playback;
    ``word_timings`` optionally aligns words to the audio for lip sync.
    """

    audio: bytes
    format: str = "wav"
    sample_rate: int = 24000
    duration: float = 0.0
    voice: str = ""
    engine: str = ""
    word_timings: List[Dict[str, Any]] = field(default_factory=list)
    device: str = ""
    language: str = ""
    locale: str = ""


class TTSProvider(ABC):
    """Abstract text-to-speech engine.

    Implementations must never raise out of :meth:`is_available`; they should
    return ``False`` and keep a human-readable reason in :meth:`describe`.
    """

    name: str = "abstract"

    @abstractmethod
    def initialize(self) -> bool:
        """Bring the engine up (idempotent). Return True when usable."""

    @abstractmethod
    def speak(self, text: str, voice: Optional[str] = None, speed: Optional[float] = None,
              settings: Optional[Dict[str, Any]] = None) -> SynthesisResult:
        """Synthesize ``text`` and return the encoded audio."""

    @abstractmethod
    def stop(self) -> None:
        """Abort in-flight work as soon as possible (best effort)."""

    @abstractmethod
    def pause(self) -> None:
        """Pause playback/synthesis when the engine owns the output."""

    @abstractmethod
    def resume(self) -> None:
        """Resume a previously paused engine."""

    @abstractmethod
    def is_available(self) -> bool:
        """True when the engine can synthesize right now."""

    @abstractmethod
    def get_voices(self) -> List[str]:
        """Voice identifiers offered by this engine."""

    def shutdown(self) -> None:
        """Release resources when KIRA exits. Optional no-op by default."""
        return None

    def describe(self) -> Dict[str, Any]:
        """Human-readable engine state for status endpoints and logs."""
        return {"engine": self.name, "available": self.is_available()}
