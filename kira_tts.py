"""
KIRA Text-to-Speech using Microsoft Edge neural voices.

These voices sound very natural and human-like, much better than
browser-based TTS. Uses edge-tts library.
"""

from kira_speech import clean_for_speech

import asyncio
import os
import tempfile
import hashlib
import html
import json
import math
import kira_language
from pathlib import Path

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    print("[WARNING] edge-tts not installed. Install with: pip install edge-tts")

# Cache directory for generated audio files
CACHE_DIR = Path(tempfile.gettempdir()) / "kira_tts_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Default voice - Jenny is one of the best female neural voices
DEFAULT_VOICE = "en-US-JennyNeural"

# Available high-quality female voices
FEMALE_VOICES = {
    "jenny": "en-US-JennyNeural",      # Friendly, natural (EN)
    "aria": "en-US-AriaNeural",         # Professional, clear (EN)
    "sara": "en-US-SaraNeural",         # Warm, conversational (EN)
    "nancy": "en-US-NancyNeural",       # Calm, soothing (EN)
    "jane": "en-US-JaneNeural",         # Expressive (EN)
    "aria_uk": "en-GB-SoniaNeural",     # British accent
    # Voix françaises
    "denise": "fr-FR-DeniseNeural",     # Chaleureuse, naturelle (FR)
    "eloise": "fr-FR-EloiseNeural",     # Jeune, expressive (FR)
    "vivienne": "fr-FR-VivienneNeural", # Posée, élégante (FR)
    "henri": "fr-FR-HenriNeural",       # Masculine, grave (FR)
}


def _timing_path(audio_path):
    return Path(audio_path).with_suffix(".timings.json")


def _word_boundary(chunk):
    """Edge offsets are 100-nanosecond ticks, not milliseconds."""
    try:
        start = float(chunk["offset"]) / 10_000_000
        duration = float(chunk["duration"]) / 10_000_000
        if not isinstance(chunk.get("text"), str):
            return None
        text = html.unescape(chunk["text"])
        if not text.strip() or not math.isfinite(start) or not math.isfinite(duration):
            return None
        if start < 0 or duration <= 0 or duration > 60:
            return None
        return {"text": text, "start": start, "duration": duration}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


async def _generate_speech(text: str, voice: str, output_path: str) -> bool:
    """Capture audio and optional word boundaries in one TTS stream.

    Audio writes are atomic: an interrupted request cannot leave a truncated MP3
    that the next request mistakes for a valid cached response. Missing timing
    metadata never prevents speech; the UI has an estimated-timing fallback.
    """
    output = Path(output_path)
    audio_temp = metadata_temp = None
    try:
        try:
            communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
        except TypeError:
            # edge-tts 6.x reports word boundaries by default and does not accept
            # the boundary option; newer releases otherwise default to sentences.
            communicate = edge_tts.Communicate(text, voice)
        words = []
        total = 0
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".part", delete=False) as audio:
            audio_temp = Path(audio.name)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    total += audio.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    word = _word_boundary(chunk)
                    if word and (not words or word["start"] >= words[-1]["start"]):
                        words.append(word)
        if not total:
            raise ValueError("The speech service returned no audio")
        audio_temp.replace(output)
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                             suffix=".part", delete=False) as metadata:
                metadata_temp = Path(metadata.name)
                json.dump({"version": 1, "units": "seconds", "words": words}, metadata, ensure_ascii=False)
            metadata_temp.replace(_timing_path(output))
        except (OSError, ValueError, TypeError) as error:
            # Never pair freshly generated audio with a stale timing sidecar.
            try:
                _timing_path(output).unlink(missing_ok=True)
            except OSError:
                pass
            print(f"[KIRA TTS] Word timing unavailable; using estimated lip sync: {error}")
        return True
    except Exception as error:
        print(f"[KIRA TTS] Error generating speech: {error}")
        return False
    finally:
        for temporary in (audio_temp, metadata_temp):
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def get_word_timings(audio_path):
    """Return validated, cached word times. Older/bad caches fall back safely."""
    try:
        path = _timing_path(audio_path)
        if path.stat().st_size > 2 * 1024 * 1024:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or data.get("units") != "seconds":
            return []
        words = data.get("words")
        if not isinstance(words, list):
            return []
        valid = []
        for word in words[:10000]:
            if not isinstance(word, dict) or not isinstance(word.get("text"), str):
                continue
            start, duration = word.get("start"), word.get("duration")
            if (type(start) not in (int, float) or type(duration) not in (int, float)
                    or not math.isfinite(start) or not math.isfinite(duration)
                    or start < 0 or not 0 < duration <= 60 or not word["text"].strip()
                    or (valid and start < valid[-1]["start"])):
                continue
            valid.append({"text": word["text"], "start": start, "duration": duration})
        return valid
    except (OSError, ValueError, TypeError):
        return []


def select_neural_voice(text, voice=None, language=None):
    """A requested language wins over an incompatible legacy 'jenny' default."""
    named = FEMALE_VOICES.get(str(voice or "").lower(), voice)
    if language is None and named:
        return named  # Preserve the explicit-voice Python API.
    code = kira_language.speech_language(text, language or "auto")
    if named and kira_language.normalize_language("-".join(str(named).split("-")[:2])) == code:
        return named
    known = kira_language.LANGUAGES.get(code, {}).get("voice")
    if known:
        return known
    # Rare languages can be provided by a newer Edge catalog. Never substitute
    # English when no matching voice exists; the browser can try an installed one.
    candidates = [item for item in list_voices()
                  if kira_language.normalize_language(item.get("Locale")) == code]
    candidates.sort(key=lambda item: item.get("Gender") != "Female")
    return candidates[0].get("ShortName") if candidates else None


def generate_speech(text: str, voice: str = None, language: str = None) -> str | None:
    """
    Generate speech audio from text.
    
    Args:
        text: Text to speak
        voice: Optional explicit voice name
        language: Reply language; when supplied, overrides an incompatible voice
    
    Returns:
        Path to generated audio file, or None if failed
    """
    text = clean_for_speech(text)
    if not EDGE_TTS_AVAILABLE:
        print("[KIRA TTS] edge-tts not available")
        return None
    
    if not text or not text.strip():
        return None
    
    voice = select_neural_voice(text, voice, language)
    if not voice:
        print("[KIRA TTS] No matching voice for the requested language")
        return None

    # Generate cache key based on text and voice
    cache_key = hashlib.md5(f"word-timings-v1:{voice}:{text}".encode()).hexdigest()
    audio_path = CACHE_DIR / f"{cache_key}.mp3"
    
    # Return cached file if it exists
    if audio_path.is_file() and audio_path.stat().st_size > 0:
        print(f"[KIRA TTS] Using cached audio: {cache_key[:8]}...")
        return str(audio_path)
    
    # Generate new audio
    print(f"[KIRA TTS] Generating speech with voice: {voice}")
    print(f"[KIRA TTS] Text: {text[:60]}...")
    
    try:
        # Run async function in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(_generate_speech(text, voice, str(audio_path)))
        finally:
            loop.close()
            asyncio.set_event_loop(None)
        
        if success and audio_path.exists():
            print(f"[KIRA TTS] Generated: {audio_path.name}")
            return str(audio_path)
        else:
            print("[KIRA TTS] Failed to generate audio")
            return None
            
    except Exception as e:
        print(f"[KIRA TTS] Error: {e}")
        return None


def list_voices():
    """List available voices."""
    if not EDGE_TTS_AVAILABLE:
        return []
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        voices = loop.run_until_complete(edge_tts.list_voices())
        loop.close()
        return voices
    except Exception as e:
        print(f"[KIRA TTS] Error listing voices: {e}")
        return []


def cleanup_cache(max_age_hours: int = 24):
    """Clean up old cached audio files."""
    import time
    cutoff = time.time() - (max_age_hours * 3600)
    
    for audio_file in CACHE_DIR.glob("*.mp3"):
        if audio_file.stat().st_mtime < cutoff:
            try:
                audio_file.unlink()
                _timing_path(audio_file).unlink(missing_ok=True)
            except Exception:
                pass
