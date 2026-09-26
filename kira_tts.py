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


async def _generate_speech(text: str, voice: str, output_path: str) -> bool:
    """Generate speech audio using edge-tts."""
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return True
    except Exception as e:
        print(f"[KIRA TTS] Error generating speech: {e}")
        return False


def generate_speech(text: str, voice: str = None) -> str | None:
    """
    Generate speech audio from text.
    
    Args:
        text: Text to speak
        voice: Voice name (default: Jenny)
    
    Returns:
        Path to generated audio file, or None if failed
    """
    text = clean_for_speech(text)
    if not EDGE_TTS_AVAILABLE:
        print("[KIRA TTS] edge-tts not available")
        return None
    
    if not text or not text.strip():
        return None
    
    # Use default voice if not specified
    if voice is None:
        voice = DEFAULT_VOICE
    elif voice.lower() in FEMALE_VOICES:
        voice = FEMALE_VOICES[voice.lower()]
    
    # Generate cache key based on text and voice
    cache_key = hashlib.md5(f"{voice}:{text}".encode()).hexdigest()
    audio_path = CACHE_DIR / f"{cache_key}.mp3"
    
    # Return cached file if it exists
    if audio_path.exists():
        print(f"[KIRA TTS] Using cached audio: {cache_key[:8]}...")
        return str(audio_path)
    
    # Generate new audio
    print(f"[KIRA TTS] Generating speech with voice: {voice}")
    print(f"[KIRA TTS] Text: {text[:60]}...")
    
    try:
        # Run async function in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(_generate_speech(text, voice, str(audio_path)))
        loop.close()
        
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
            except Exception:
                pass
