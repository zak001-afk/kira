"""TTSManager — the KIRA voice layer's brain.

Owns the engines, resolves which provider speaks a given reply (Kokoro first,
Edge as fallback), applies the speaking-mode profiles, and exposes the
control surface KIRA uses: ``speak / stop_speaking / pause_speaking /
resume_speaking / is_speaking``.

Specialized agents never call an engine directly; their text returns to KIRA
and KIRA speaks it through here.
"""

from __future__ import annotations

import base64
import threading
from typing import Any, Dict, List, Optional

from kira.services.tts.base import TTSProvider, TTSProviderError
from kira.services.tts.config import MODES, TTSConfig, load_config
from kira.services.tts.kokoro import KokoroTTSProvider
from kira.services.tts.speech_formatter import spoken_sentences

# Speaking-mode profiles. Voice stays constant on purpose: KIRA has one voice,
# modes only change pace and breathing room.
MODE_PROFILES: Dict[str, Dict[str, Any]] = {
    "normal":  {"speed": 0.94, "sentence_pause": 0.45, "clause_pause": 0.18, "max_sentences": 4},
    "alert":   {"speed": 1.00, "sentence_pause": 0.14, "clause_pause": 0.06, "max_sentences": 6},
    "serious": {"speed": 0.90, "sentence_pause": 0.60, "clause_pause": 0.25, "max_sentences": 4},
    "system":  {"speed": 0.88, "sentence_pause": 0.60, "clause_pause": 0.25, "max_sentences": 5},
    "success": {"speed": 0.96, "sentence_pause": 0.35, "clause_pause": 0.15, "max_sentences": 4},
}


def mode_profile(mode: str) -> Dict[str, Any]:
    return dict(MODE_PROFILES.get(str(mode or "normal").lower(), MODE_PROFILES["normal"]))


class TTSManager:
    """Facade over the engine providers with KIRA's modes and state."""

    def __init__(self, config: Optional[TTSConfig] = None) -> None:
        self.config = config or load_config()
        self.mode = self.config.mode
        self._lock = threading.RLock()
        self._generation = 0
        self._speaking = False
        self._paused = False
        self._last_error = ""
        self._providers: Dict[str, TTSProvider] = {}
        self._warmed = False
        self._warmup_lock = threading.Lock()

    # ── providers ────────────────────────────────────────────────────────────

    def providers(self) -> Dict[str, TTSProvider]:
        with self._lock:
            if not self._providers:
                self._providers = {
                    "kokoro": KokoroTTSProvider(self.config),
                    "edge": self._make_edge_provider(),
                }
            return self._providers

    def _make_edge_provider(self) -> TTSProvider:
        from kira.services.tts.edge import EdgeTTSProvider  # noqa: PLC0415

        return EdgeTTSProvider()

    def provider(self, name: str) -> Optional[TTSProvider]:
        return self.providers().get(name)

    def _preferred_order(self, requested_engine: str) -> List[str]:
        engine = str(requested_engine or self.config.engine or "kokoro").lower()
        if engine not in ("kokoro", "edge"):
            engine = "kokoro"
        order = [engine]
        for candidate in ("kokoro", "edge"):
            if candidate not in order:
                order.append(candidate)
        return order

    # ── resolution ───────────────────────────────────────────────────────────

    def _resolve_language(self, text: str, language: Optional[str] = None):
        """Return ``(language code, kokoro_eligible)`` for a reply.

        A confident detection wins over the requested locale: an English voice
        must never read a French or Arabic reply with English phonemes, and the
        detected code lets the Edge fallback pick a matching national voice.
        Uncertain (very short) text keeps the requested locale.
        """
        try:
            from kira.core import kira_language  # noqa: PLC0415

            detection = kira_language.detect_language(text)
            detected = getattr(detection, "language", None)
            confidence = float(getattr(detection, "confidence", 0) or 0)
            if detected and confidence >= 0.5:
                return str(detected), str(detected).startswith("en")
            requested = kira_language.normalize_language(language or "auto")
            if not requested or requested == "auto":
                return None, True
            return str(requested), str(requested).startswith("en")
        except Exception:
            return None, True

    def _is_english(self, text: str, language: Optional[str] = None) -> bool:
        """True when the local Kokoro voices may speak this reply."""
        return self._resolve_language(text, language)[1]

    def _female_voice(self, voice: Optional[str]) -> str:
        """KIRA speaks with a female voice only.

        Male Kokoro names (``am_``/``bm_``) fall back to the configured voice;
        male Edge names are rewritten to the female voice of the language by
        :func:`kira_tts.select_neural_voice`.
        """
        name = str(voice or "").strip()
        if not name or name[:3].lower() in ("am_", "bm_"):
            return self.config.voice
        return name

    def _edge_voice_names(self) -> set:
        """Short names that address the Edge engine instead of Kokoro."""
        try:
            from kira.services import kira_tts  # noqa: PLC0415

            return set(getattr(kira_tts, "FEMALE_VOICES", {})) | set(
                getattr(kira_tts, "MALE_VOICES", {}))
        except Exception:
            return set()

    def resolve(self, text: str, language: Optional[str] = None,
                engine: Optional[str] = None,
                voice: Optional[str] = None) -> Optional[TTSProvider]:
        """Pick the provider that should speak this reply, or None."""
        requested_voice = str(voice or self.config.voice or "").lower()
        for name in self._preferred_order(engine or ""):
            provider = self.providers().get(name)
            if provider is None:
                continue
            if name == "kokoro":
                if not self._is_english(text, language):
                    continue
                if not provider.is_available():
                    continue
                # An explicit Edge voice name (female or legacy male) means the
                # caller asked for Edge, not for the local Kokoro voices.
                edge_names = self._edge_voice_names()
                if requested_voice in edge_names:
                    continue
            if provider.is_available() or provider.initialize():
                return provider
        return None

    # ── speaking state ───────────────────────────────────────────────────────

    def is_speaking(self) -> bool:
        with self._lock:
            return self._speaking

    def stop_speaking(self) -> None:
        """Interrupt immediately: drop in-flight work, clear the queue."""
        with self._lock:
            self._generation += 1
            self._speaking = False
            self._paused = False
        for provider in self.providers().values():
            try:
                provider.stop()
            except Exception:
                pass

    def pause_speaking(self) -> None:
        with self._lock:
            self._paused = True
        for provider in self.providers().values():
            try:
                provider.pause()
            except Exception:
                pass

    def resume_speaking(self) -> None:
        with self._lock:
            self._paused = False
        for provider in self.providers().values():
            try:
                provider.resume()
            except Exception:
                pass

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._paused

    # ── the pipeline ─────────────────────────────────────────────────────────

    def plan(self, text: str, mode: Optional[str] = None,
             max_sentences: Optional[int] = None) -> Dict[str, Any]:
        """Speech-formatted sentences for a reply (no synthesis)."""
        profile = mode_profile(mode or self.mode)
        limit = profile.get("max_sentences")
        if max_sentences is not None:
            limit = max_sentences
        sentences = spoken_sentences(
            text, mode or self.mode, limit, keep_sir=self.config.keep_sir)
        return {
            "mode": mode or self.mode,
            "sentences": sentences,
            "spoken": "\n\n".join(sentences),
            "profile": profile,
        }

    def speak(
        self,
        text: str,
        mode: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        engine: Optional[str] = None,
        language: Optional[str] = None,
        format_text: bool = True,
        max_sentences: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Format, synthesize and return an audio payload for the UI.

        The returned dict is the same shape the UI already consumed from
        ``/api/tts`` (``audio`` base64, ``format``, ``word_timings``) plus
        additive voice-layer metadata, so older clients keep working.
        """
        if not self.config.enabled:
            return {"success": False, "error": "KIRA voice is disabled", "error_code": "tts_disabled"}

        resolved_mode = str(mode or self.mode or "normal").lower()
        if resolved_mode not in MODES:
            resolved_mode = "normal"
        profile = mode_profile(resolved_mode)

        spoken = text
        sentences: List[str] = []
        if format_text:
            limit = profile.get("max_sentences")
            if max_sentences is not None:
                limit = max_sentences
            plan = self.plan(text, resolved_mode, limit)
            sentences = plan["sentences"]
            spoken = plan["spoken"]
        if not spoken or not spoken.strip():
            return {"success": False, "error": "Nothing to speak", "error_code": "empty_text"}

        provider = self.resolve(spoken, language, engine, voice)
        fallback_reason = ""
        if provider is None:
            self._last_error = "No TTS engine is currently available"
            return {
                "success": False,
                "error": self._last_error,
                "error_code": "tts_unavailable",
                "mode": resolved_mode,
            }

        generation = self._current_generation()
        detected_language, _ = self._resolve_language(spoken, language)
        settings: Dict[str, Any] = {
            "sentence_pause": profile["sentence_pause"],
            "clause_pause": profile["clause_pause"],
            "language": detected_language or language or "auto",
            "timeout": 120.0,
        }
        effective_speed = float(speed if speed is not None else profile["speed"])
        try:
            with self._lock:
                self._speaking = True
                self._paused = False
            result = provider.speak(spoken, self._female_voice(voice),
                                    effective_speed, settings)
        except TTSProviderError as error:
            with self._lock:
                self._speaking = False
            self._last_error = str(error)
            if provider.name != "edge":
                alternate = self.providers().get("edge")
                if alternate is not None and alternate.is_available():
                    try:
                        result = alternate.speak(spoken, None, None, settings)
                        fallback_reason = str(error)
                    except TTSProviderError as edge_error:
                        self._last_error = str(edge_error)
                        return self._unavailable_payload(resolved_mode)
                else:
                    return self._unavailable_payload(resolved_mode)
            else:
                return self._unavailable_payload(resolved_mode)
        finally:
            if self._current_generation() == generation:
                with self._lock:
                    self._speaking = False

        if self._current_generation() != generation:
            return {"success": False, "error": "Interrupted", "error_code": "interrupted"}

        volume = max(0.0, min(1.0, float(self.config.volume)))
        payload: Dict[str, Any] = {
            "success": True,
            "audio": base64.b64encode(result.audio).decode("ascii"),
            "format": result.format,
            "word_timings": result.word_timings,
            "spoken_text": spoken,
            "sentences": sentences,
            "engine": result.engine,
            "voice": result.voice,
            "speed": effective_speed,
            "mode": resolved_mode,
            "device": result.device,
            "duration": result.duration,
        }
        if result.language:
            payload["language"] = result.language
            payload["locale"] = result.locale
        if volume < 1.0:
            payload["volume"] = volume
        if fallback_reason:
            payload["fallback_reason"] = fallback_reason
        return payload

    def _current_generation(self) -> int:
        with self._lock:
            return self._generation

    def _unavailable_payload(self, resolved_mode: str) -> Dict[str, Any]:
        return {
            "success": False,
            "error": self._last_error or "TTS is unavailable",
            "error_code": "tts_unavailable",
            "mode": resolved_mode,
        }

    # ── status for the UI ────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        if not self.config.enabled:
            return {
                "enabled": False,
                "state": "offline",
                "label": "KIRA VOICE — OFFLINE",
                "speaking": False,
                "mode": self.mode,
                "engines": {},
                "config": self.config.summary(),
                "error": "KIRA voice is disabled (KIRA_TTS_ENABLED)",
            }
        # Probe first (cached by TTL) so the reported state matches reality;
        # describe() then reflects the fresh availability/device.
        kokoro = self.providers().get("kokoro")
        edge = self.providers().get("edge")
        kokoro_ok = bool(kokoro.is_available()) if kokoro is not None else False
        edge_ok = bool(edge.is_available()) if edge is not None else False
        engines = {name: provider.describe() for name, provider in self.providers().items()}
        state = "online" if (kokoro_ok or edge_ok) else "offline"
        if kokoro_ok:
            primary = "kokoro"
        elif edge_ok:
            primary = "edge"
        else:
            primary = self.config.engine
        if self.is_speaking():
            state = "speaking"
        return {
            "enabled": True,
            "state": state,
            "label": "KIRA — SPEAKING" if state == "speaking" else "KIRA VOICE — ONLINE"
            if state == "online" else "KIRA VOICE — OFFLINE",
            "engine": primary,
            "device": engines.get("kokoro", {}).get("device", ""),
            "speaking": self.is_speaking(),
            "paused": self.paused,
            "mode": self.mode,
            "voices": self.providers().get("kokoro").get_voices() if kokoro_ok else [],
            "engines": engines,
            "config": self.config.summary(),
            "error": "" if state != "offline" else (self._last_error or
                                                    engines.get("kokoro", {}).get("error", "")),
        }

    def set_mode(self, mode: str) -> Dict[str, Any]:
        resolved = str(mode or "").lower().strip()
        if resolved not in MODES:
            return {"success": False, "error": "Unknown mode: {}".format(mode),
                    "modes": list(MODES)}
        self.mode = resolved
        return {"success": True, "mode": resolved, "profile": mode_profile(resolved)}

    def warmup(self) -> bool:
        """Bring the primary engine up without synthesizing anything."""
        provider = self.providers().get(self.config.engine)
        if provider is None:
            return False
        try:
            return bool(provider.initialize())
        except Exception as error:
            self._last_error = str(error)
            return False

    def warmup_async(self) -> None:
        """Kick off engine initialization once, in the background.

        The first UI status poll calls this, so Kokoro is warming up while
        the user reads the cockpit instead of when the first reply arrives.
        """
        if self._warmed or not self.config.enabled:
            return
        with self._warmup_lock:
            if self._warmed:
                return
            self._warmed = True
            threading.Thread(target=self.warmup, daemon=True,
                             name="kira-tts-warmup").start()


_manager: Optional[TTSManager] = None
_manager_lock = threading.Lock()


def get_manager() -> TTSManager:
    """Process-wide manager singleton (created on first use)."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = TTSManager(load_config())
    return _manager


def reset_manager() -> None:
    """Test helper: drop the singleton."""
    global _manager
    with _manager_lock:
        _manager = None
