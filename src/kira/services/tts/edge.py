"""Edge neural voices as the KIRA voice fallback engine.

Wraps the existing :mod:`kira.services.kira_tts` edge-tts engine behind the
abstract ``TTSProvider`` contract. It is used automatically when the local
Kokoro server is unreachable, and for non-English replies (the Kokoro v1.0
voices are English-only while Edge covers 40+ locales).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from kira.services.tts.base import SynthesisResult, TTSProvider, TTSProviderError


class EdgeTTSProvider(TTSProvider):
    """Microsoft Edge neural voices (requires internet at synthesis time)."""

    name = "edge"

    def __init__(self) -> None:
        self._initialized = False

    def initialize(self) -> bool:
        try:
            import kira_tts  # noqa: PLC0415 — lazy: keeps this module light

            self._initialized = bool(getattr(kira_tts, "EDGE_TTS_AVAILABLE", False))
        except Exception:  # ImportError or a broken install — stay offline.
            self._initialized = False
        return self._initialized

    def speak(self, text: str, voice: Optional[str] = None, speed: Optional[float] = None,
              settings: Optional[Dict[str, Any]] = None) -> SynthesisResult:
        import kira_tts  # noqa: PLC0415
        from kira.core import kira_language  # noqa: PLC0415

        settings = settings or {}
        language = settings.get("language") or "auto"
        selected_language = kira_language.speech_language(text, language)
        # Resolve the voice first (legacy behaviour): the caller may pass a
        # short name such as "jenny" that maps to the locale-appropriate voice.
        selected_voice = kira_tts.select_neural_voice(
            text, voice=voice, language=selected_language)
        if not selected_voice:
            raise TTSProviderError("No neural voice available for this language")
        audio_path = kira_tts.generate_speech(
            text, selected_voice, language=selected_language)
        if not audio_path:
            raise TTSProviderError("Edge neural voices returned no audio")
        audio = Path(audio_path).read_bytes()
        return SynthesisResult(
            audio=audio,
            format="mp3",
            sample_rate=24000,
            duration=0.0,
            voice=selected_voice,
            engine=self.name,
            word_timings=kira_tts.get_word_timings(audio_path),
            device="edge-cloud",
            language=str(selected_language),
            locale=kira_language.locale_for(selected_language),
        )

    def stop(self) -> None:
        """Edge synthesis cannot be aborted mid-request; the manager drops the result."""

    def pause(self) -> None:
        """Playback is owned by the UI; nothing to do server-side."""

    def resume(self) -> None:
        """Playback is owned by the UI; nothing to do server-side."""

    def is_available(self) -> bool:
        try:
            import kira_tts  # noqa: PLC0415

            return bool(getattr(kira_tts, "EDGE_TTS_AVAILABLE", False))
        except Exception:
            return False

    def get_voices(self) -> List[str]:
        try:
            import kira_tts  # noqa: PLC0415

            return sorted(kira_tts.FEMALE_VOICES.keys())
        except Exception:
            return []

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info["note"] = "Fallback engine — requires an internet connection"
        return info
