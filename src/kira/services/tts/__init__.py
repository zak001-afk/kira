"""KIRA voice layer — modular, fully local text-to-speech.

The package sits between KIRA's persona layer and the audio output:

    KIRA reply -> SpeechFormatter -> TTSManager -> TTSProvider -> audio

``TTSProvider`` is the only contract the rest of KIRA sees, so engines can be
swapped (Kokoro today, Piper/XTTS tomorrow) without touching call sites.
"""

from kira.services.tts.base import SynthesisResult, TTSProvider
from kira.services.tts.config import TTSConfig, load_config
from kira.services.tts.edge import EdgeTTSProvider
from kira.services.tts.kokoro import KokoroTTSProvider
from kira.services.tts.manager import MODE_PROFILES, TTSManager, get_manager
from kira.services.tts.speech_formatter import format_speech, split_sentences

__all__ = [
    "MODE_PROFILES",
    "EdgeTTSProvider",
    "KokoroTTSProvider",
    "SynthesisResult",
    "TTSConfig",
    "TTSManager",
    "TTSProvider",
    "format_speech",
    "get_manager",
    "load_config",
    "split_sentences",
]
