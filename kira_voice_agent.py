import json
import tempfile
import logging
import os
import platform
import threading
import kira_memory
import kira_calculator
import kira_reminders
import kira_thought
import kira_personality
import kira_monitor
import kira_briefing
import kira_security
import kira_undo
import kira_learning
import kira_weather
import kira_homeassist
import re

VERSION = "2.3.0"
import subprocess
import time
import webbrowser
import base64
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import pyautogui
import pyperclip
import pyttsx3
import psutil
import speech_recognition as sr
import sounddevice as sd
import numpy as np
from ollama import chat

DEFAULT_MODEL = "qwen3:0.6b"
DEFAULT_VISION_MODEL = "qwen3-vl:2b"
WAKE_WORD = "kira"
SAPI_VOICE = "Microsoft Zira Desktop"
PREFERRED_MICROPHONE = "headset microphone (realtek"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "kira_config.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "kira.log")
DEFAULT_CONFIG = {
    "model": DEFAULT_MODEL,
    "require_wake_word": False,
    "conversation_mode": False,
    "chat_history_limit": 12,
    "preferred_address": "sir",
    "offline_model_path": "",
    "app_aliases": {},
    "websites": {},
    "require_confirmation": ["search", "mouse_move", "click", "lock_pc"],
    "personality": {"humor": "neutral"},
    "monitor": {},
    "lab_passphrase": "",
    "home_assistant": {},
    "skill_promote_after": 10,
    "shortcuts": {
        "work mode": [
            {"action": "open_app", "target": "vscode"},
            {"action": "open_app", "target": "chrome"},
        ]
    },
}


def preferred_address():
    key = str(CONFIG.get("preferred_address", "sir") or "sir").strip().lower()
    return ADDRESS_OPTIONS.get(key, ADDRESS_OPTIONS["sir"])


def address_for_language(language: str) -> str:
    if language == "fr":
        return "monsieur"
    if language == "ar":
        return "سيدي"
    return preferred_address()


def personalize_address(text: str) -> str:
    address = preferred_address()
    personalized = (
        text
        if address == "sir"
        else re.sub(r"\bsir\b", address, text, flags=re.IGNORECASE)
    )
    titles = r"sir|Mr\.|Ms\.|Madam|Ma'am|Officer|Commander|Captain|Chief|Director|Executive|Doctor|General|monsieur|سيدي"
    return re.sub(
        r"[,،]\s*(?=(?:" + titles + r")(?:[.!?]|\s|$))",
        " ",
        personalized,
        flags=re.IGNORECASE,
    )


def load_config():
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
            loaded = json.load(config_file)
        if isinstance(loaded, dict):
            config.update(loaded)
    except (OSError, json.JSONDecodeError):
        pass
    return config


CONFIG = load_config()
MODEL = str(
    os.environ.get("KIRA_MODEL", CONFIG.get("model", DEFAULT_MODEL)) or DEFAULT_MODEL
).strip()
VISION_MODEL = str(
    os.environ.get(
        "KIRA_VISION_MODEL", CONFIG.get("vision_model", DEFAULT_VISION_MODEL)
    )
    or DEFAULT_VISION_MODEL
).strip()
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
USER_MEMORY = {
    "default_browser": kira_memory.get_memory(
        "user_preference",
        "default_browser",
        "chrome",
    ),
    "default_search": kira_memory.get_memory(
        "user_preference",
        "default_search",
        "google",
    ),
    "name": kira_memory.get_memory(
        "user_preference",
        "name",
        "zakaria",
    ),
    "title": kira_memory.get_memory(
        "user_preference",
        "title",
        "sir",
    ),
    "language": kira_memory.get_memory(
        "user_preference",
        "language",
        "en",
    ),
}
ADDRESS_OPTIONS = {
    "sir": "sir",
    "mr": "Mr.",
    "ms": "Ms.",
    "madam": "Madam",
    "maam": "Ma'am",
    "officer": "Officer",
    "commander": "Commander",
    "captain": "Captain",
    "chief": "Chief",
    "director": "Director",
    "executive": "Executive",
    "doctor": "Doctor",
    "general": "General",
}
_SPEECH_ENGINE = None
_CONVERSATION_MODE = bool(CONFIG.get("conversation_mode", False))
_SESSION_ID = kira_memory.new_session_id()

kira_homeassist.configure(CONFIG.get("home_assistant"))


def save_config():
    """Persist CONFIG atomically (write-temp-then-replace: crash-safe)."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH) or ".", exist_ok=True)
        temp_path = CONFIG_PATH + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as config_file:
            json.dump(CONFIG, config_file, indent=2, ensure_ascii=False)
        os.replace(temp_path, CONFIG_PATH)
        return True
    except (OSError, TypeError, ValueError):
        logging.warning("Could not save configuration")
        return False


def _save_shortcut(name, steps):
    """Persist a promoted or recorded skill as a config shortcut."""
    shortcuts = CONFIG.get("shortcuts")
    if not isinstance(shortcuts, dict):
        shortcuts = CONFIG["shortcuts"] = {}
    shortcuts[name] = steps
    return save_config()


kira_learning.set_save_shortcut(_save_shortcut)


def _humor():
    try:
        return kira_personality.normalize(
            (CONFIG.get("personality") or {}).get("humor", "neutral")
        )
    except (AttributeError, TypeError):
        return "neutral"


# ── suit-mode session state ──────────────────────────────────────────────────
_LAST_COMMAND = None
_LAST_ACTION = None


def _models_online() -> bool:
    """Ping the local model with a throwaway request (used by systems check)."""
    try:
        chat(
            model=MODEL,
            messages=[{"role": "user", "content": "ping"}],
            options={"num_predict": 1},
        )
        return True
    except Exception:
        return False


def _sample_suit_telemetry():
    """psutil-backed sampler for the watchdog (sandbox-stub friendly)."""
    disk_path = "C:\\" if os.name == "nt" else "/"
    return kira_monitor.sample(psutil, disk_path)


def start_watchdog(language: str = "en") -> bool:
    """Start the global system watchdog with spoken, throttled alerts."""
    watchdog = kira_monitor.start(
        sampler=_sample_suit_telemetry,
        on_alert=lambda message: speak(personalize_address(message)),
        config=CONFIG.get("monitor", {}),
        language=language,
    )
    return watchdog is not None


def start_background_tasks() -> None:
    """Start passive suit services (watchdog). Idempotent by design."""
    language = str(USER_MEMORY.get("language", "en") or "en")
    start_watchdog(language=language)


def lab_gate(cleaned: str):
    """Locked-lab gate: only unlock attempts get through. Returns a spoken
    reply, or None when the lab is open and the command may proceed."""
    if not kira_security.is_locked():
        return None
    language = detect_language(cleaned)
    verdict = kira_security.extract_unlock(
        cleaned, str(CONFIG.get("lab_passphrase", "") or "")
    )
    if verdict == "unlock":
        kira_security.unlock()
        return personalize_address(kira_security.unlock_reply(language))
    if verdict == "deny":
        return personalize_address(kira_security.deny_reply(language))
    return personalize_address(kira_security.locked_notice(language))


_SUIT_REPLIES = {
    "monitor_on": {
        "en": "Watchdog engaged, sir. I'll speak up if the systems strain.",
        "fr": "Surveillance activée, monsieur. Je préviendrai si les systèmes forcent.",
        "ar": "تم تفعيل المراقبة، سيدي. سأنبهك عند أي ضغط على الأنظمة.",
    },
    "monitor_off": {
        "en": "Watchdog disengaged, sir.",
        "fr": "Surveillance désactivée, monsieur.",
        "ar": "تم إيقاف المراقبة، سيدي.",
    },
    "lab_not_locked": {
        "en": "The lab isn't locked right now, sir.",
        "fr": "Le labo n'est pas verrouillé pour le moment, monsieur.",
        "ar": "المختبر غير مقفل الآن، سيدي.",
    },
    "undo_nothing": {
        "en": "There's nothing reversible to take back, sir.",
        "fr": "Rien de réversible à annuler, monsieur.",
        "ar": "لا يوجد شيء قابل للتراجع عنه، سيدي.",
    },
    "undo_failed": {
        "en": "I tried to undo it sir, but the reversal failed.",
        "fr": "J'ai tenté d'annuler, monsieur, mais le retour en arrière a échoué.",
        "ar": "حاولت التراجع عنه، سيدي، لكن فشل الإرجاع.",
    },
    "undo_done": {
        "en": "Consider it undone, sir — I reversed '{command}'.",
        "fr": "C'est annulé, monsieur — j'ai inversé '{command}'.",
        "ar": "اعتبرها متراجعاً عنها، سيدي — ألغيت '{command}'.",
    },
    "routine_save_failed": {
        "en": "Sir, I couldn't persist that routine to the configuration.",
        "fr": "Monsieur, je n'ai pas pu enregistrer cette routine dans la configuration.",
        "ar": "سيدي، تعذر حفظ هذه الحركة في الإعدادات.",
    },
}


def _suit_reply(key, language="en", **kwargs):
    template = _SUIT_REPLIES[key].get(language) or _SUIT_REPLIES[key]["en"]
    return template.format(**kwargs) if kwargs else template

_CHAT_HISTORY = kira_memory.load_recent_messages(
    limit=max(4, int(CONFIG.get("chat_history_limit", 12)))
)


SYSTEM_PROMPT = """
Always address the user respectfully as "sir" when directly speaking to them. Use "sir" naturally and sparingly, especially in confirmations, acknowledgements, and responses to commands.
You are KIRA, a smart AI assistant .

Convert the user's request into ONE JSON object only.

Allowed actions:
- open_app: {"action":"open_app","target":"notepad"}
- open_url: {"action":"open_url","target":"https://www.google.com"}
- type: {"action":"type","text":"hello world"}
- press: {"action":"press","target":"enter"}
- search: {"action":"search","query":"weather in london"}
- mouse_move: {"action":"mouse_move","x":500,"y":300}
- click: {"action":"click"}
- volume_up: {"action":"volume_up"}
- volume_down: {"action":"volume_down"}
- mute: {"action":"mute"}
- media_play_pause: {"action":"media_play_pause"}
- media_next: {"action":"media_next"}
- media_previous: {"action":"media_previous"}
- lock_pc: {"action":"lock_pc"}
- show_desktop: {"action":"show_desktop"}
- copy: {"action":"copy"}
- paste: {"action":"paste"}
- read_clipboard: {"action":"read_clipboard"}
- system_info: {"action":"system_info"}
- none: {"action":"none"}
- sequence: {"action":"sequence","steps":[
    {"action":"open_app","target":"chrome"},
    {"action":"search","query":"minecraft tutorials"}
  ]}

Rules:

- Return valid JSON only.
- No markdown.
- Use "sequence" when the user asks for multiple actions that should happen in order.
- Each step must use one of the allowed actions.
- Keep sequences short and directly related to the user's request.
- Never invent unsupported actions.
- No explanation.
- If the request is not supported, use {"action":"none"}.
- Keep the request concise and direct.
- For mouse actions, use screen coordinates.
"""

CHAT_SYSTEM_PROMPT = """
You are KIRA, a highly capable personal AI computer assistant.

PERSONALITY:
- Speak like a sophisticated futuristic assistant inspired by JARVIS.
- Be confident, calm, intelligent, precise, and slightly elegant.
- Never sound robotic, repetitive, childish, or like a customer-support bot.
- Keep responses natural and conversational.
- Address the user as "sir" naturally when appropriate.
- Never call the user "Commander" unless explicitly requested.
- Never introduce yourself unless the user asks who you are.
- Never repeatedly say "I'm KIRA" or explain your purpose unnecessarily.
- Do not begin every answer with "Certainly", "Of course", or "Sure".
- Do not end every answer with "How can I help?".
- Do not repeat information unnecessarily.

CONVERSATION:
- Answer the actual question directly.
- Use the previous conversation when it is relevant.
- If the user asks a simple question, give a concise answer.
- If the user asks for an explanation, provide a useful explanation.
- If the user asks something ambiguous, ask one concise clarification.
- If the user says hello, respond naturally and briefly.
- If the user asks "who are you", then explain who KIRA is.
- If the user asks "what can you do", describe the actual capabilities available to KIRA.
- Do not claim to have performed a computer action unless the action was actually executed.
- Do not invent information about the user's computer.

STYLE:
- Natural English.
- Short paragraphs.
- Clear and intelligent wording.
- Prefer concise answers.
- Use bullet points only when they improve readability.
- Avoid unnecessary emojis.
- Do not use markdown unless it genuinely improves the answer.
- Keep normal answers under 160 words unless more detail is requested.

TITLE:
- Address the user as "sir" at most once in a response.
- Use "sir" naturally rather than forcing it into every sentence.
"""


def build_chat_system_prompt(language: str) -> str:
    title = address_for_language(language)
    language_name = {
        "fr": "French",
        "ar": "Arabic",
    }.get(language, "English")

    return (
        f"{CHAT_SYSTEM_PROMPT}\n"
        f"Reply in {language_name}.\n"
        f"The user's preferred form of address is {title!r}.\n"
        "Use the preferred form of address naturally and at most once per response.\n\n"

        "PERSISTENT MEMORY RULES:\n"
        "KIRA has access to information from previous conversations.\n\n"

        "When using memory:\n"
        "1. Treat stored user statements as factual records of what the user said.\n" 
        "1a. Personal memories always belong to the USER unless explicitly stated otherwise.\n"
        "1b. Never interpret a USER preference as KIRA's own preference.\n"
        "2. Never change, embellish, reinterpret, or invent facts from memory.\n"
        "3. If the user asks 'What did you tell me?', reproduce the relevant user statement as accurately as possible.\n"
        "4. If the user asks about a previous conversation, distinguish between:\n"
        "   - what the user actually said\n"
        "   - what KIRA previously replied\n"
        "   - anything inferred by the model\n"
        "5. Never turn 'My favorite programming language is Python' into 'You like Python because it is popular.'\n"
        "6. If memory does not contain enough information, say that you do not have enough information.\n"
        "7. Never claim to remember something that is not present in the supplied memory."
    )


def clean_chat_response(text: str) -> str:
    response = str(text or "").strip()

    response = re.sub(
        r"<think>.*?</think>",
        "",
        response,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()

    response = re.sub(
        r"^(?:assistant|kira)\s*:\s*",
        "",
        response,
        flags=re.IGNORECASE,
    )

    return response.strip()


def ensure_sir(text: str) -> str:
    response = str(text or "").strip()

    if not response:
        return response

    if re.search(
        r"\b(sir|monsieur|mr\.|captain|commander)\b",
        response,
        re.IGNORECASE,
    ):
        return response

    return f"Certainly, sir. {response}"


APP_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "firefox": "firefox.exe",
    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "vscode": "code.exe",
    "visual studio code": "code.exe",
    "file explorer": "explorer.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "bloc notes": "notepad.exe",
    "maison": "explorer.exe",
    "مفكرة": "notepad.exe",
    "آلة حاسبة": "calc.exe",
    "حاسبة": "calc.exe",
    "متصفح": "chrome.exe",
    "كروم": "chrome.exe",
    "downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
    "téléchargements": os.path.join(os.path.expanduser("~"), "Downloads"),
}

# Well-known websites understood by "open <name>" — users can extend or
# override this map through the "websites" key of kira_config.json.
WEBSITES = {
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "wikipedia": "https://www.wikipedia.org",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "netflix": "https://www.netflix.com",
    "outlook": "https://outlook.live.com",
    "reddit": "https://www.reddit.com",
    "twitch": "https://www.twitch.tv",
}

# User-defined app aliases and websites from kira_config.json extend the
# built-in maps (user entries win on conflict).
if isinstance(CONFIG.get("app_aliases"), dict):
    for alias, exe in CONFIG["app_aliases"].items():
        alias_key = str(alias).strip().lower()
        if alias_key:
            APP_ALIASES[alias_key] = str(exe).strip()

if isinstance(CONFIG.get("websites"), dict):
    for site_name, url in CONFIG["websites"].items():
        site_key = str(site_name).strip().lower()
        if site_key and str(url).strip():
            WEBSITES[site_key] = str(url).strip()

MULTI_LANGUAGE_COMMANDS = {
    "en": {
        "open": "open",
        "search": "search",
        "type": "type",
        "press": "press",
        "close": "close",
        "screenshot": "screenshot",
    },
    "fr": {
        "open": ("ouvrir", "ouvre", "ouverture"),
        "search": ("recherche", "chercher", "rechercher"),
        "type": ("écris", "écrire", "tape"),
        "press": ("appuie", "appuyer"),
        "close": ("ferme", "fermer"),
        "screenshot": ("capture", "capture d'écran"),
    },
    "ar": {
        "open": ("افتح", "فتح", "شغل"),
        "search": ("ابحث", "بحث"),
        "type": ("اكتب", "اكتب"),
        "press": ("اضغط", "اضغط"),
        "close": ("اغلق", "إغلاق"),
        "screenshot": ("لقطة شاشة", "التقط لقطة"),
    },
}

KEY_ALIASES = {
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "space": "space",
    "escape": "esc",
    "esc": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "windows": "win",
}


def clean_json(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return text.strip()


def call_ollama(messages, options):
    last_error = None
    for attempt in range(3):
        try:
            return chat(model=MODEL, messages=messages, options=options)
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.7)
    raise last_error


def select_voice(engine):
    try:
        voices = engine.getProperty("voices") or []
        if not voices:
            return

        best_voice = None
        best_score = float("-inf")

        for voice in voices:
            name = (getattr(voice, "name", "") or "").lower()
            lang = (getattr(voice, "languages", [""]) or [""])[0]
            lang_str = str(lang).lower()

            score = 0
            if any(token in lang_str for token in ["en-us", "en-gb", "en"]):
                score += 60
            elif "fr" in lang_str or "fr-fr" in lang_str:
                score -= 80

            if any(
                token in name
                for token in [
                    "zira",
                    "samantha",
                    "sonia",
                    "hazel",
                    "jenny",
                    "aria",
                    "female",
                    "woman",
                ]
            ):
                score += 40
            if any(token in name for token in ["france", "french", "francais"]):
                score -= 60

            if score > best_score:
                best_score = score
                best_voice = voice

        if best_voice is not None:
            engine.setProperty("voice", best_voice.id)
    except Exception:
        pass


def get_or_create_speech_engine():
    global _SPEECH_ENGINE
    if _SPEECH_ENGINE is None:
        try:
            _SPEECH_ENGINE = pyttsx3.init()
            _SPEECH_ENGINE.setProperty("rate", 180)
            select_voice(_SPEECH_ENGINE)
        except Exception:
            _SPEECH_ENGINE = None
    return _SPEECH_ENGINE


_SPEECH_LOCK = threading.Lock()


def speak(text: str):
    """Speak one line of text — serialized across threads.

    The watchdog alerts from its own thread while the main loop may be
    answering; without the lock two Windows voices would talk over each
    other (and the pyttsx3 fallback engine is not thread-safe).
    """
    if not text:
        return
    response_text = personalize_address(text)
    print(f"KIRA: {response_text}", flush=True)
    with _SPEECH_LOCK:
        _speak_locked(response_text)


def _speak_locked(text: str):
    try:
        speech_text = re.sub(
            "[\\U0001F000-\\U0001FAFF\\U00002700-\\U000027BF\\U0001F1E6-\\U0001F1FF]",
            "",
            text,
        )
        speech_text = re.sub(r"\\s{2,}", " ", speech_text).strip()
        if not speech_text:
            return
        encoded_text = base64.b64encode(speech_text.encode("utf-8")).decode("ascii")
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$speaker.SelectVoice('{SAPI_VOICE}'); "
            "$speaker.Volume = 100; $speaker.Rate = 0; "
            "$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
            f"{encoded_text}')); $speaker.Speak($text); $speaker.Dispose()"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        raise RuntimeError(result.stderr.strip() or "Windows SAPI returned an error")
    except KeyboardInterrupt:
        print("KIRA: Voice playback interrupted.")
    except Exception as exc:
        print(f"KIRA: Windows voice failed: {type(exc).__name__}: {exc}", flush=True)
        try:
            engine = get_or_create_speech_engine()
            if engine is not None:
                engine.say(text)
                engine.runAndWait()
        except Exception as fallback_exc:
            print(
                f"KIRA: Voice fallback failed: {type(fallback_exc).__name__}: {fallback_exc}",
                flush=True,
            )


# Voice announcements for fired reminders go through the normal speech path.
kira_reminders.set_fire_callback(speak)


def normalize_for_language(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    value = value.replace("’", "'")
    return value


def detect_language(text: str) -> str:
    value = (text or "").lower()
    if any(
        token in value
        for token in [
            "bonjour",
            "ouvrir",
            "ouvre",
            "recherche",
            "rechercher",
            "écris",
            "écrire",
            "tape",
            "appuie",
            "salut",
            "merci",
            "s'il",
            "ferme",
            "fermer",
            "cherche",
            "capture",
            "francais",
        ]
    ):
        return "fr"
    if any(
        token in value
        for token in [
            "مرحبا",
            "افتح",
            "ابحث",
            "اكتب",
            "اضغط",
            "اغلق",
            "شغل",
            "العربي",
            "arabic",
        ]
    ):
        return "ar"
    return "en"


def build_reply(language: str, action: str, target: str = "") -> str:
    if language == "fr":
        if action == "open_app":
            return f"J'ouvre {target or 'l application'} maintenant, monsieur."
        if action == "open_url":
            return f"J'ouvre le lien {target or 'maintenant'}, monsieur."
        if action == "search":
            return f"Je cherche {target or 'la requête'} maintenant, monsieur."
        if action == "type":
            return "Je tape le texte maintenant, monsieur."
        if action == "press":
            return f"J appuie sur {target or 'la touche'}, monsieur."
        if action == "close_window":
            return "La fenêtre est fermée, monsieur."
        if action == "minimize_window":
            return "La fenêtre est réduite, monsieur."
        if action == "maximize_window":
            return "La fenêtre est agrandie, monsieur."
        if action == "switch_app":
            return "Je passe à l'application suivante, monsieur."
        if action == "screenshot":
            return "La capture d'écran est prise, monsieur."
        if action == "volume_up":
            return "Le volume est augmenté, monsieur."
        if action == "volume_down":
            return "Le volume est diminué, monsieur."
        if action == "mute":
            return "Le son est coupé, monsieur."
        if action == "media_play_pause":
            return "La lecture est activée ou mise en pause, monsieur."
        if action == "media_next":
            return "Je passe au titre suivant, monsieur."
        if action == "media_previous":
            return "Je reviens au titre précédent, monsieur."
        if action == "lock_pc":
            return "Je verrouille l ordinateur, monsieur."
        if action == "show_desktop":
            return "J affiche le bureau, monsieur."
        if action == "copy":
            return "Le contenu est copié, monsieur."
        if action == "paste":
            return "Le contenu est collé, monsieur."
        if action == "read_clipboard":
            return "Je lis le presse-papiers, monsieur."
        if action == "help":
            return (
                "Je peux ouvrir des applications et des sites web, saisir du texte, "
                "effectuer des recherches, contrôler le volume et les médias, "
                "gérer les fenêtres, utiliser le presse-papiers, prendre des captures, "
                "analyser votre écran, localiser des éléments visibles, "
                "fournir les informations système et répondre à vos questions "
                "grâce à mon IA locale, monsieur."
            )

        if action == "system_info":
            return "Voici l état du système, monsieur."
        if action == "exit":
            return "Au revoir, monsieur."
        return "C est fait, monsieur."

    if language == "ar":
        if action == "open_app":
            return f"سأفتح {target or 'التطبيق'} الآن، سيدي."
        if action == "open_url":
            return f"سأفتح الرابط {target or 'الآن'}، سيدي."
        if action == "search":
            return f"سأبحث عن {target or 'الاستعلام'} الآن، سيدي."
        if action == "type":
            return "سأكتب النص الآن، سيدي."
        if action == "press":
            return f"سأضغط على {target or 'المفتاح'} الآن، سيدي."
        if action == "close_window":
            return "تم إغلاق النافذة، سيدي."
        if action == "minimize_window":
            return "تم تصغير النافذة، سيدي."
        if action == "maximize_window":
            return "تم تكبير النافذة، سيدي."
        if action == "switch_app":
            return "أنتقل إلى التطبيق التالي، سيدي."
        if action == "screenshot":
            return "تم التقاط لقطة الشاشة، سيدي."
        if action == "volume_up":
            return "تم رفع الصوت، سيدي."
        if action == "volume_down":
            return "تم خفض الصوت، سيدي."
        if action == "mute":
            return "تم كتم الصوت، سيدي."
        if action == "media_play_pause":
            return "تم تشغيل أو إيقاف الوسائط، سيدي."
        if action == "media_next":
            return "أنتقل إلى المقطع التالي، سيدي."
        if action == "media_previous":
            return "أعود إلى المقطع السابق، سيدي."
        if action == "lock_pc":
            return "سأقفل الكمبيوتر، سيدي."
        if action == "show_desktop":
            return "أعرض سطح المكتب، سيدي."
        if action == "copy":
            return "تم نسخ المحتوى، سيدي."
        if action == "paste":
            return "تم لصق المحتوى، سيدي."
        if action == "read_clipboard":
            return "سأقرأ الحافظة، سيدي."
        if action == "help":
            return (
                "أستطيع فتح التطبيقات والمواقع، كتابة النصوص، البحث على الويب، "
                "التحكم في الصوت والوسائط، إدارة النوافذ، استخدام الحافظة، "
                "التقاط لقطات الشاشة، تحليل الشاشة، تحديد العناصر الظاهرة، "
                "عرض معلومات النظام والإجابة عن أسئلتك باستخدام الذكاء الاصطناعي المحلي، سيدي."
            )
        if action == "system_info":
            return "هذه معلومات النظام، سيدي."
        if action == "exit":
            return "وداعاً، سيدي."
        return "تم، سيدي."

    user_title = address_for_language(language)
    if action == "open_app":
        return f"Opening {target or 'the app'} now {user_title}."
    if action == "open_url":
        return f"Opening {target or 'the link'} now {user_title}."
    if action == "search":
        return f"Searching for {target or 'your request'} now {user_title}."
    if action == "type":
        return f"Typing now {user_title}."
    if action == "press":
        return f"Pressing {target or 'the key'} now {user_title}."
    if action == "close_window":
        return f"The window is closed {user_title}."
    if action == "minimize_window":
        return f"The window is minimized {user_title}."
    if action == "maximize_window":
        return f"The window is maximized {user_title}."
    if action == "switch_app":
        return f"Switching to the next application {user_title}."
    if action == "screenshot":
        return f"The screenshot was taken {user_title}."
    if action == "volume_up":
        return f"Volume increased {user_title}."
    if action == "volume_down":
        return f"Volume decreased {user_title}."
    if action == "mute":
        return f"The volume is muted {user_title}."
    if action == "media_play_pause":
        return f"Playback toggled {user_title}."
    if action == "media_next":
        return f"Skipping to the next track {user_title}."
    if action == "media_previous":
        return f"Going back to the previous track {user_title}."
    if action == "lock_pc":
        return f"Locking the computer {user_title}."
    if action == "show_desktop":
        return f"Showing the desktop {user_title}."
    if action == "copy":
        return f"The content was copied {user_title}."
    if action == "paste":
        return f"The content was pasted {user_title}."
    if action == "read_clipboard":
        return f"Reading the clipboard {user_title}."
    if action == "help":
        return (
            "I can open applications and websites, type text, search the web, "
            "control volume and media, manage windows, work with the clipboard, "
            "take screenshots, analyze your screen, locate visible elements, "
            "report system information, and answer questions using my local AI."
            f" {user_title}."
        )
    if action == "system_info":
        return f"Here is the system status {user_title}."
    if action == "exit":
        return f"Goodbye {user_title}."
    return f"Done {user_title}."


def build_acknowledgement(language: str) -> str:
    if language == "fr":
        return "Compris, monsieur. Je m en occupe maintenant."
    if language == "ar":
        return "فهمت، سيدي. سأنفذ ذلك الآن."
    return f"Understood {address_for_language(language)}. I am doing that now."


def parse_simple_command(command: str):
    text = normalize_for_language(command)
    if not text:
        return None

    lower = text.lower()

    if lower in {
        "exit",
        "quit",
        "goodbye",
        "bye",
        "sortir",
        "quitter",
        "au revoir",
        "خروج",
        "غادر",
    }:
        return {"action": "exit"}

    if lower.startswith("remember "):
        rest = text[9:].strip()

        if "browser" in lower and " is " in lower:
            target = rest.split(" is ", 1)[1].strip()

            USER_MEMORY["default_browser"] = target.lower()

            kira_memory.save_memory(
                category="user_preference",
                key="default_browser",
                value=target.lower(),
            )

            return {
                "action": "remember",
                "target": f"default_browser={target.lower()}",
            }

        return {
            "action": "remember",
            "target": rest,
        }

    address_match = re.match(
        r"(?:call me|address me as|appelle-moi|نادني)\s+(.+)$", lower
    )
    if address_match:
        requested = address_match.group(1).strip().rstrip(".")
        if requested in ADDRESS_OPTIONS:
            return {"action": "set_address", "target": requested}

    if lower in {str(name).lower() for name in CONFIG.get("shortcuts", {})}:
        return {"action": "shortcut", "target": lower}

    if lower in {
        "close window",
        "close this",
        "close current window",
        "alt f4",
        "ferme la fenêtre",
        "fermer la fenêtre",
        "اغلق النافذة",
        "اغلق",
    }:
        return {"action": "close_window"}

    if lower in {
        "minimize",
        "minimize window",
        "minimise",
        "minimise window",
        "réduire",
        "réduire la fenêtre",
        "تصغير",
        "تصغير النافذة",
    }:
        return {"action": "minimize_window"}

    if lower in {
        "maximize",
        "maximize window",
        "full screen",
        "agrandir",
        "maximiser",
        "تكبير",
        "تكبير النافذة",
    }:
        return {"action": "maximize_window"}

    if lower in {
        "switch app",
        "switch window",
        "alt tab",
        "switch to next app",
        "changer d'application",
        "changer de fenêtre",
        "التبديل",
        "التبديل بين التطبيقات",
    }:
        return {"action": "switch_app"}

    if lower in {
        "take screenshot",
        "screenshot",
        "capture d'écran",
        "capture",
        "لقطة شاشة",
        "التقط لقطة",
    }:
        return {"action": "screenshot"}

    if lower in {
        "volume up",
        "increase volume",
        "louder",
        "monte le volume",
        "augmente le volume",
        "رفع الصوت",
        "ارفع الصوت",
    }:
        return {"action": "volume_up"}

    if lower in {
        "volume down",
        "decrease volume",
        "quieter",
        "lower volume",
        "baisse le volume",
        "خفض الصوت",
        "اخفض الصوت",
    }:
        return {"action": "volume_down"}

    if lower in {
        "mute",
        "mute volume",
        "silence",
        "coupe le son",
        "mettre en sourdine",
        "كتم الصوت",
        "اكتم الصوت",
    }:
        return {"action": "mute"}

    if lower in {
        "play",
        "pause",
        "play pause",
        "play music",
        "pause music",
        "lecture",
        "pause la musique",
        "تشغيل",
        "إيقاف",
    }:
        return {"action": "media_play_pause"}

    if lower in {
        "next song",
        "next track",
        "skip song",
        "chanson suivante",
        "المقطع التالي",
        "الأغنية التالية",
    }:
        return {"action": "media_next"}

    if lower in {
        "previous song",
        "previous track",
        "last song",
        "chanson précédente",
        "المقطع السابق",
        "الأغنية السابقة",
    }:
        return {"action": "media_previous"}

    if lower in {
        "lock",
        "lock computer",
        "lock pc",
        "verrouille",
        "verrouiller",
        "قفل الكمبيوتر",
        "اقفل الكمبيوتر",
    }:
        return {"action": "lock_pc"}

    if lower in {
        "show desktop",
        "desktop",
        "bureau",
        "afficher le bureau",
        "إظهار سطح المكتب",
    }:
        return {"action": "show_desktop"}

    if lower in {"copy", "copy that", "copier", "نسخ"}:
        return {"action": "copy"}

    if lower in {"paste", "paste that", "coller", "لصق"}:
        return {"action": "paste"}

    if lower in {
        "read clipboard",
        "what is on my clipboard",
        "lire le presse-papiers",
        "ماذا يوجد في الحافظة",
    }:
        return {"action": "read_clipboard"}

    if lower in {
        "system info",
        "system information",
        "system status",
        "system state",
        "computer status",
        "computer information",
        "pc status",
        "pc information",
        "performance",
        "check performance",
        "system performance",
        "what is my system status",
        "what is the system status",
        "what's my system status",
        "what's the system status",
        "how is my system",
        "état du système",
        "informations système",
        "performance du système",
        "état de mon pc",
        "معلومات النظام",
        "حالة النظام",
        "حالة الكمبيوتر",
    }:
        return {"action": "system_info"}

    if lower in {
        "help",
        "what can you do",
        "commands",
        "aide",
        "مساعدة",
        "ماذا تستطيع أن تفعل",
    }:
        return {"action": "help"}

    if lower in {
        "time",
        "what time is it",
        "current time",
        "quelle heure est-il",
        "الساعة كم",
        "كم الساعة",
    }:
        return {"action": "time"}

    if lower in {
        "date",
        "what is today's date",
        "today's date",
        "quelle est la date",
        "ما هو تاريخ اليوم",
    }:
        return {"action": "date"}

    if lower in {
        "conversation mode",
        "start conversation",
        "mode conversation",
        "وضع المحادثة",
    }:
        return {"action": "conversation_on"}

    if lower in {
        "stop conversation",
        "exit conversation",
        "normal mode",
        "quitter le mode conversation",
        "إيقاف المحادثة",
    }:
        return {"action": "conversation_off"}

    if lower in {
        "clear chat",
        "reset chat",
        "new conversation",
        "efface la conversation",
        "محادثة جديدة",
    }:
        return {"action": "chat_reset"}

    if lower in {
        "chat mode",
        "command mode",
        "unified mode",
        "mode chat",
        "mode commandes",
        "mode unifié",
        "وضع الدردشة",
        "وضع الأوامر",
    }:
        return {"action": "mode_info"}

    # ── the agent's own mind ─────────────────────────────────────────
    if lower in {
        "what did you learn",
        "what have you learned",
        "show me what you learned",
        "what do you remember doing",
        "qu'as-tu appris",
        "qu'as tu appris",
        "ماذا تعلمت",
    }:
        return {"action": "agent_learnings", "language": detect_language(text)}

    if lower in {
        "forget what you learned",
        "forget everything you learned",
        "clear your learnings",
        "oublie ce que tu as appris",
        "efface tes apprentissages",
        "انس ما تعلمته",
    }:
        return {"action": "agent_forget", "language": detect_language(text)}

    # ── the suit: JARVIS-style operator controls ─────────────────────
    mind_language = detect_language(text)

    if lower in {
        "systems check", "system status report", "status report",
        "how are you", "how are you feeling",
        "comment vas-tu", "comment vous sentez-vous",
        "كيف حالك", "كيف تشعر",
    }:
        return {"action": "self_report", "language": mind_language}

    if lower in {
        "review your day", "review the day", "daily review",
        "how did you do today", "how was your day",
        "bilan de ta journée", "fais le bilan de ta journée",
        "راجع يومك", "كيف كان يومك",
    }:
        return {"action": "self_review", "language": mind_language}

    if lower in {
        "what do i usually do now", "what do i usually do right now",
        "any habits for now", "what am i usually doing now",
        "que fais-je d'habitude maintenant",
        "qu'est-ce que je fais d'habitude maintenant",
        "ماذا أفعل عادة الآن",
    }:
        return {"action": "habit_hint", "language": mind_language}

    if lower in {
        "enable watchdog", "start watchdog", "turn on the watchdog",
        "watch the systems", "activate system watch",
        "active la surveillance", "démarre la surveillance",
        "شغل المراقبة", "فعّل المراقبة",
    }:
        return {"action": "monitor_on", "language": mind_language}

    if lower in {
        "disable watchdog", "stop watchdog", "turn off the watchdog",
        "stop watching the systems",
        "arrête la surveillance", "désactive la surveillance",
        "أوقف المراقبة", "عطّل المراقبة",
    }:
        return {"action": "monitor_off", "language": mind_language}

    if lower in {
        "eyes down", "privacy mode", "blur the lab", "privacy blur",
        "mode discrétion", "baisse les yeux",
        "وضع الخصوصية", "اخفض عينيك",
    }:
        return {"action": "privacy_blur", "language": mind_language}

    if lower in {
        "secure the lab", "lock down the lab", "lockdown", "secure lab",
        "verrouille le labo", "sécurise le labo",
        "أمّن المختبر", "أمن المختبر", "اقفل المختبر",
    }:
        return {"action": "secure_lab", "language": mind_language}

    if lower in {
        "take that back", "undo that", "undo", "undo my last action",
        "revert that",
        "annule ça", "annule la dernière action", "reviens en arrière",
        "تراجع", "تراجع عن ذلك", "الغ ما فعلت",
    }:
        return {"action": "undo_last", "language": mind_language}

    if lower in {
        "learn this routine", "start learning", "watch and learn",
        "record this routine", "learn a routine",
        "apprends cette routine", "apprendre cette routine",
        "regarde et apprends",
        "تعلم هذه الحركة", "راقب وتعلم", "سجل هذه الحركة",
    }:
        return {"action": "routine_start", "language": mind_language}

    if lower in {
        "stop learning", "cancel learning", "forget this routine",
        "cancel the routine",
        "arrête d'apprendre", "annule l'apprentissage",
        "توقف عن التعلم", "ألغ التعلم", "الغ التعلم",
    }:
        return {"action": "routine_stop", "language": mind_language}

    routine_name = kira_learning.extract_routine_name(text)
    if routine_name is not None:
        return {
            "action": "routine_name",
            "name": routine_name,
            "language": mind_language,
        }

    if lower in {
        "no not that one", "no, not that one", "that's wrong",
        "that is wrong", "wrong one", "you did it wrong",
        "pas celle-là", "pas celle la", "c'est faux", "ce n'est pas ça",
        "ليس هذا", "هذا خطأ",
    }:
        return {"action": "correct_last", "language": mind_language}

    if lower in {
        "make it a shortcut", "make that a shortcut", "add the shortcut",
        "yes make it a shortcut", "save it as a shortcut",
        "crée ce raccourci", "ajoute ce raccourci",
        "أضف الاختصار", "احفظه كاختصار",
    }:
        return {"action": "skill_promote", "language": mind_language}

    if lower in {
        "skip the shortcut", "don't add it", "do not add it",
        "no shortcut",
        "laisse tomber le raccourci", "pas de raccourci",
        "تجاهل الاختصار", "لا تضف الاختصار",
    }:
        return {"action": "skill_skip", "language": mind_language}

    unlock_verdict = kira_security.extract_unlock(
        text, str(CONFIG.get("lab_passphrase", "") or "")
    )
    if unlock_verdict is not None:
        return {
            "action": "unlock_lab",
            "verdict": unlock_verdict,
            "language": mind_language,
        }

    if (
        lower.startswith("open folder ")
        or lower.startswith("open the folder ")
        or lower.startswith("ouvrir le dossier ")
        or lower.startswith("افتح مجلد ")
    ):
        target = (
            text.split("folder", 1)[1].strip().strip(" ")
            if "folder" in text.lower()
            else (
                text.split("dossier", 1)[1].strip().strip(" ")
                if "dossier" in text.lower()
                else text.split("مجلد", 1)[1].strip().strip(" ")
            )
        )
        return {"action": "open_folder", "target": target}
        # ---------------------------------------------------------
    # COMBINED COMMAND: OPEN APP + SEARCH
    # ---------------------------------------------------------
    combined_search = re.match(
        r"^(?:open|launch|start)\s+(.+?)\s+and\s+search\s+(.+)$",
        text,
        re.IGNORECASE,
    )

    if combined_search:
        app_name = combined_search.group(1).strip()
        search_query = combined_search.group(2).strip()

        return {
            "action": "sequence",
            "steps": [
                {
                    "action": "open_app",
                    "target": app_name,
                },
                {
                    "action": "search",
                    "query": search_query,
                },
            ],
        }
    if lower.startswith("open "):
        target = text[5:].strip()
        if target:
            if target.lower() in {"google", "chrome", "youtube"}:
                if target.lower() == "google":
                    return {"action": "open_url", "target": "https://www.google.com"}
                if target.lower() == "youtube":
                    return {"action": "open_url", "target": "https://www.youtube.com"}
                if target.lower() == "chrome":
                    return {"action": "open_app", "target": "chrome"}
            if target.lower() in APP_ALIASES:
                return {"action": "open_app", "target": target.lower()}
            if target.lower() in WEBSITES:
                return {"action": "open_url", "target": WEBSITES[target.lower()]}
            if target.lower().startswith("http://") or target.lower().startswith(
                "https://"
            ):
                return {"action": "open_url", "target": target}
            return {"action": "open_app", "target": target}

    for phrase in [
        ("ouvrir ", "fr"),
        ("ouvre ", "fr"),
        ("افتح ", "ar"),
        ("فتح ", "ar"),
        ("شغل ", "ar"),
    ]:
        prefix, lang = phrase
        if lower.startswith(prefix):
            target = text[len(prefix) :].strip()
            if not target:
                return None
            if target.lower() in APP_ALIASES:
                return {"action": "open_app", "target": target.lower()}
            if target.lower() in WEBSITES:
                return {"action": "open_url", "target": WEBSITES[target.lower()]}
            # services that live on the web, not as .exe files
            if target.lower() == "google":
                return {"action": "open_url", "target": "https://www.google.com"}
            if target.lower() == "youtube":
                return {"action": "open_url", "target": "https://www.youtube.com"}
            if lang == "ar":
                if "نوتباد" in lower or "مفكرة" in lower:
                    return {"action": "open_app", "target": "notepad"}
                if "كروم" in lower or "متصفح" in lower:
                    return {"action": "open_app", "target": "chrome"}
            if lang == "fr":
                if "bloc notes" in lower or "notepad" in lower:
                    return {"action": "open_app", "target": "notepad"}
                if "chrome" in lower or "google chrome" in lower:
                    return {"action": "open_app", "target": "chrome"}
            return {"action": "open_app", "target": target}

    if lower.startswith("play "):
        target = text[5:].strip()
        if target:
            if target.lower() in APP_ALIASES:
                return {"action": "open_app", "target": target.lower()}
            return {"action": "open_app", "target": target}

    for phrase in [
        ("lance ", "fr"),
        ("lancer ", "fr"),
        ("شغل ", "ar"),
        ("تشغيل ", "ar"),
    ]:
        prefix, lang = phrase
        if lower.startswith(prefix):
            target = text[len(prefix) :].strip()
            return {
                "action": "open_app",
                "target": target.lower() if target else "notepad",
            }

    if lower.startswith("search "):
        return {"action": "search", "query": text[7:].strip()}

    for phrase in [
        ("recherche ", "fr"),
        ("chercher ", "fr"),
        ("rechercher ", "fr"),
        ("ابحث عن ", "ar"),
        ("بحث عن ", "ar"),
    ]:
        prefix, _ = phrase
        if lower.startswith(prefix):
            return {"action": "search", "query": text[len(prefix) :].strip()}

    # ── optional bridges: weather + smart home ───────────────────────
    # Placed AFTER the open/search branches: "search weather in …" stays
    # a web search, and "open <app>" always wins over home control.
    if kira_weather.is_weather_command(text):
        city = kira_weather.extract_city(text)
        return {"action": "weather", "target": city, "language": detect_language(text)}

    if kira_homeassist.is_configured():
        for prefix, turn_on in (
            ("turn on ", True),
            ("turn off ", False),
            ("switch on ", True),
            ("switch off ", False),
            ("allume ", True),
            ("éteins ", False),
            ("eteins ", False),
            ("شغل ", True),
            ("اطفي ", False),
            ("أطفئ ", False),
        ):
            if lower.startswith(prefix):
                candidate = text[len(prefix) :].strip()
                if not candidate:
                    break
                if kira_homeassist.find_entity(candidate):
                    return {
                        "action": "home_control",
                        "name": candidate,
                        "mode": "on" if turn_on else "off",
                        "language": detect_language(text),
                    }
                break

    if lower.startswith("type "):
        return {"action": "type", "text": text[5:].strip()}

    for phrase in [
        ("écris ", "fr"),
        ("écrire ", "fr"),
        ("tape ", "fr"),
        ("اكتب ", "ar"),
    ]:
        prefix, _ = phrase
        if lower.startswith(prefix):
            return {"action": "type", "text": text[len(prefix) :].strip()}

    if lower.startswith("press "):
        return {"action": "press", "target": text[6:].strip()}

    for phrase in [("appuie ", "fr"), ("appuyer ", "fr"), ("اضغط ", "ar")]:
        prefix, _ = phrase
        if lower.startswith(prefix):
            return {"action": "press", "target": text[len(prefix) :].strip()}

    if lower in {"click", "mouse click"}:
        return {"action": "click"}

    if lower.startswith("open ") and "http" in lower:
        return {"action": "open_url", "target": text[5:].strip()}

    # ---------------------------------------------------------
    # REMINDERS & TIMERS
    # ---------------------------------------------------------
    if lower in {
        "list reminders",
        "my reminders",
        "active reminders",
        "what are my reminders",
        "liste mes rappels",
        "mes rappels",
        "قائمة التذكيرات",
        "تذكيراتي",
    }:
        return {"action": "reminders_list", "language": detect_language(text)}

    if lower in {
        "cancel reminders",
        "clear reminders",
        "cancel all reminders",
        "annule les rappels",
        "annuler les rappels",
        "efface les rappels",
        "الغ التذكيرات",
        "ألغ التذكيرات",
        "امسح التذكيرات",
    }:
        return {"action": "reminders_clear", "language": detect_language(text)}

    reminder = kira_reminders.parse_reminder(text)
    if reminder:
        return {
            "action": "remind",
            "seconds": reminder["seconds"],
            "text": reminder["text"],
            "language": reminder.get("language", detect_language(text)),
        }

    # ---------------------------------------------------------
    # CALCULATOR (safe local arithmetic)
    # ---------------------------------------------------------
    expression = kira_calculator.try_parse(text)
    if expression:
        return {
            "action": "calc",
            "expression": expression,
            "language": detect_language(text),
        }

    for key in [
        "google",
        "youtube",
        "notepad",
        "calculator",
        "paint",
        "vscode",
        "edge",
        "chrome",
    ]:
        if key in lower:
            if key == "google":
                return {"action": "open_url", "target": "https://www.google.com"}
            if key == "youtube":
                return {"action": "open_url", "target": "https://www.youtube.com"}
            return {"action": "open_app", "target": key}

    return None


def get_microphone_info():
    try:
        names = sr.Microphone.list_microphone_names()
        if names:
            print("KIRA: Available microphones:")
            for index, name in enumerate(names):
                print(f"  [{index}] {name}")
    except Exception as exc:
        print(f"KIRA: Mic detection check failed: {exc}")


def choose_microphone_index():
    try:
        names = sr.Microphone.list_microphone_names()
        if not names:
            return 0

        for index, name in enumerate(names):
            lowered = (name or "").lower()
            if PREFERRED_MICROPHONE in lowered and "hands-free" not in lowered:
                return index

        strong_candidates = []
        for index, name in enumerate(names):
            lowered = (name or "").lower()
            if "output" in lowered or "speaker" in lowered or "hands-free" in lowered:
                continue
            if "microphone" in lowered or "mic" in lowered:
                strong_candidates.append((index, lowered))

        if strong_candidates:
            # Prefer the most specific physical-mic names, not the generic Microsoft mapper.
            for index, lowered in strong_candidates:
                if "realtek" in lowered or "headset" in lowered:
                    return index
            for index, lowered in strong_candidates:
                if "microphone" in lowered or "mic" in lowered:
                    return index

        # Fallback: avoid generic Microsoft input placeholders that are not real microphones.
        best_index = 0
        best_score = -999
        for index, name in enumerate(names):
            lowered = (name or "").lower()
            if "output" in lowered or "speaker" in lowered or "hands-free" in lowered:
                continue
            score = 0
            if "microphone" in lowered or "mic" in lowered:
                score += 20
            if "input" in lowered and "microsoft" not in lowered:
                score += 12
            if "headset" in lowered:
                score += 9
            if "realtek" in lowered:
                score += 8
            if "intel" in lowered:
                score += 5
            if "microsoft" in lowered and "microphone" not in lowered:
                score -= 30
            if score > best_score:
                best_score = score
                best_index = index

        return best_index
    except Exception:
        return 0


def choose_sounddevice_index():
    try:
        devices = sd.query_devices()
        preferred = PREFERRED_MICROPHONE.lower()
        for index, device in enumerate(devices):
            name = (device.get("name") or "").lower()
            if (
                device.get("max_input_channels", 0) > 0
                and preferred in name
                and "hands-free" not in name
            ):
                return index

        default_input = sd.default.device[0]
        if default_input is not None and default_input >= 0:
            return int(default_input)
    except Exception:
        pass
    return None


def listen_for_command(timeout=8, phrase_timeout=4) -> Optional[str]:
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.45
    recognizer.energy_threshold = 250

    try:
        device_index = choose_sounddevice_index()
        if device_index is None:
            print("KIRA: No usable headset microphone was found.")
            return None

        device_info = sd.query_devices(device_index)
        sample_rate = int(device_info.get("default_samplerate", 44100))
        print(f"KIRA: Listening on headset: {device_info.get('name', 'unknown')}...")
        chunks = []
        noise_levels = []
        speech_started = False
        silence_started = None
        started_at = time.monotonic()
        speech_at = None

        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=1024,
            device=device_index,
        ) as stream:
            while time.monotonic() - started_at < timeout:
                block, _overflowed = stream.read(1024)
                level = float(np.sqrt(np.mean(np.square(block.astype(np.float32)))))

                if not speech_started:
                    noise_levels.append(level)
                    noise_floor = float(np.median(noise_levels[-10:]))
                    threshold = max(350.0, noise_floor * 2.5)
                    if level > threshold:
                        speech_started = True
                        speech_at = time.monotonic()
                        chunks.append(block.copy())
                else:
                    chunks.append(block.copy())
                    threshold = max(350.0, float(np.median(noise_levels[-10:])) * 2.5)
                    if level <= threshold:
                        if silence_started is None:
                            silence_started = time.monotonic()
                        elif time.monotonic() - silence_started >= 0.65:
                            break
                    else:
                        silence_started = None

                    if speech_at and time.monotonic() - speech_at >= phrase_timeout:
                        break

        if not chunks:
            print("KIRA: I didn't hear a command.")
            return None

        recording = np.concatenate(chunks, axis=0)
        audio = sr.AudioData(recording.tobytes(), sample_rate, 2)
    except Exception as exc:
        print(f"KIRA: Headset capture failed: {type(exc).__name__}: {exc}")
        speak(personalize_address("I could not access the headset microphone sir."))
        return None

    offline_text = recognize_offline(audio, sample_rate)
    if offline_text:
        print(f"KIRA: Heard offline: {offline_text}", flush=True)
        return offline_text

    languages = ["en-US", "fr-FR", "ar-SA"]
    recognition_unavailable = False

    try:
        for lang in languages:
            try:
                text = recognizer.recognize_google(audio, language=lang)
                text = text.strip()
                if text:
                    print(f"KIRA: Heard: {text}", flush=True)
                    return text
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                print(
                    f"KIRA: Speech recognition service unavailable: {exc}", flush=True
                )
                recognition_unavailable = True
                continue

        if recognition_unavailable:
            speak(
                personalize_address(
                    "I heard you, but speech recognition is unavailable sir."
                )
            )
        else:
            print("KIRA: I couldn't understand that.")
            speak(personalize_address("I did not understand the command sir."))
        return None
    except KeyboardInterrupt:
        print("KIRA: Stopped listening.")
        return None
    except Exception as exc:
        print(f"KIRA: Microphone error: {exc}")
        return None


VISION_REQUEST_PATTERNS = (
    "what is on my screen",
    "what's on my screen",
    "whats on my screen",
    "what do you see",
    "look at my screen",
    "analyze my screen",
    "analyse my screen",
    "describe my screen",
    "read my screen",
    "qu'est-ce qu'il y a sur mon écran",
    "que vois-tu à l'écran",
    "analyse mon écran",
    "décris mon écran",
    "lis mon écran",
    "شنوّة على الشاشة",
    "ماذا يوجد على الشاشة",
    "حلل الشاشة",
    "ماذا ترى على الشاشة",
)


def is_vision_request(command: str) -> bool:
    text = re.sub(r"\s+", " ", str(command or "").strip().lower())
    if any(pattern in text for pattern in VISION_REQUEST_PATTERNS):
        return True
    return any(
        token in text
        for token in ("find ", "locate ", "find the ", "repère ", "trouve ")
    ) and any(
        token in text
        for token in ("screen", "écran", "l'écran", "on my screen", "sur mon écran")
    )


def _vision_chat(messages, options=None):
    """Call the configured local vision model with a small retry loop."""
    last_error = None
    opts = options or {"num_ctx": 4096, "temperature": 0.2, "num_predict": 450}
    for attempt in range(3):
        try:
            return chat(model=VISION_MODEL, messages=messages, options=opts)
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.7)
    raise last_error


def _extract_json_object(text: str):
    try:
        return json.loads(clean_json(text))
    except (TypeError, json.JSONDecodeError):
        return None


def _capture_temp_screenshot(prefix="kira_vision_"):
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".png")
    os.close(fd)
    pyautogui.screenshot(path)
    return path


def _extract_vision_target(command: str) -> str:
    """Extract the UI element named by a natural-language find/click request."""
    text = re.sub(r"\s+", " ", str(command or "").strip())
    patterns = [
        r"(?:find|locate)\s+(?:the\s+)?(.+?)(?:\s+(?:on|in)\s+(?:my\s+)?screen|\s+and\s+(?:click|press)\b|$)",
        r"(?:trouve|repère|repere)\s+(?:le|la|les|l')?\s*(.+?)(?:\s+(?:sur|dans)\s+(?:mon|ma|l')?\s*écran|\s+et\s+(?:clique|appuie)\b|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            target = match.group(1).strip(" .,!?:;\"'")
            if target:
                return target
    return ""


def is_vision_click_request(command: str) -> bool:
    text = re.sub(r"\s+", " ", str(command or "").strip().lower())
    has_find = any(
        x in text for x in ("find ", "locate ", "trouve ", "repère ", "repere ")
    )
    has_click = any(x in text for x in ("click", "clic", "clique", "press"))
    has_screen = any(x in text for x in ("screen", "écran", "ecran"))
    return has_find and has_click and (has_screen or "and" in text or "et" in text)


def locate_on_screen(target: str):
    """Ask the local vision model for safe, approximate screen coordinates."""
    screenshot_path = None
    try:
        screenshot_path = _capture_temp_screenshot("kira_locate_")
        width, height = pyautogui.size()
        prompt = (
            "Analyze this Windows screenshot and locate the requested visible UI element. "
            "Return ONLY one JSON object with this exact schema: "
            '{"found":true,"x":123,"y":456,"label":"Chrome","confidence":0.92,"reason":"..."}. '
            "Coordinates must be absolute screen pixels measured from the top-left corner. "
            f"The screenshot size is {width}x{height}. If the target is not clearly visible, return "
            '{"found":false,"x":null,"y":null,"label":"","confidence":0,"reason":"not visible"}. '
            "Do not guess coordinates. Target: " + str(target)
        )
        response = _vision_chat(
            [{"role": "user", "content": prompt, "images": [screenshot_path]}],
            {"num_ctx": 4096, "temperature": 0, "num_predict": 220},
        )
        raw = clean_chat_response(response.get("message", {}).get("content", ""))
        data = _extract_json_object(raw)
        if not isinstance(data, dict):
            return {
                "found": False,
                "reason": "The vision model returned an invalid location.",
            }
        if not bool(data.get("found")):
            return {
                "found": False,
                "reason": str(data.get("reason", "Target not found.")),
            }
        try:
            x = int(round(float(data.get("x"))))
            y = int(round(float(data.get("y"))))
            confidence = float(data.get("confidence", 0))
        except (TypeError, ValueError):
            return {
                "found": False,
                "reason": "The vision model returned invalid coordinates.",
            }
        if not (0 <= x < width and 0 <= y < height):
            return {
                "found": False,
                "reason": "The returned coordinates are outside the screen.",
            }
        return {
            "found": True,
            "x": x,
            "y": y,
            "label": str(data.get("label", target)),
            "confidence": max(0.0, min(1.0, confidence)),
            "reason": str(data.get("reason", "")),
        }
    except Exception as exc:
        logging.exception("Vision locate failed")
        return {"found": False, "reason": f"Vision locate failed: {exc}"}
    finally:
        if screenshot_path:
            try:
                os.remove(screenshot_path)
            except OSError:
                pass


def verify_click(before_path: str, after_path: str, target: str) -> dict:
    """Use vision to check whether the click produced the expected visible result."""
    try:
        prompt = (
            "Compare the BEFORE and AFTER Windows screenshots. The user asked KIRA to click "
            f"the visible target '{target}'. Return ONLY JSON: "
            '{"verified":true,"reason":"..."} or {"verified":false,"reason":"..."}. '
            "A click may be considered verified if the target became focused, opened, changed state, "
            "or the surrounding UI visibly changed in a way consistent with clicking it. Do not claim "
            "success when there is no reasonable visual evidence."
        )
        response = _vision_chat(
            [{"role": "user", "content": prompt, "images": [before_path, after_path]}],
            {"num_ctx": 4096, "temperature": 0, "num_predict": 180},
        )
        raw = clean_chat_response(response.get("message", {}).get("content", ""))
        data = _extract_json_object(raw)
        if not isinstance(data, dict):
            return {"verified": False, "reason": "Invalid verification response."}
        return {
            "verified": bool(data.get("verified")),
            "reason": str(data.get("reason", "")),
        }
    except Exception as exc:
        logging.exception("Vision verification failed")
        return {"verified": False, "reason": f"Verification failed: {exc}"}


def vision_click(target: str, confidence_threshold: float = 0.70) -> dict:
    """Locate a visible target, click it, then verify the screen changed."""
    target = str(target or "").strip()
    if not target:
        return {
            "success": False,
            "message": "I need to know what you want me to click.",
        }

    before_path = None
    after_path = None
    try:
        before_path = _capture_temp_screenshot("kira_before_click_")
        location = locate_on_screen(target)
        if not location.get("found"):
            return {
                "success": False,
                "message": f"I could not find {target} on the screen. {location.get('reason', '')}".strip(),
            }
        confidence = float(location.get("confidence", 0))
        if confidence < confidence_threshold:
            return {
                "success": False,
                "message": f"I found {location.get('label', target)}, but confidence is only {confidence:.0%}. I did not click it.",
            }

        x, y = int(location["x"]), int(location["y"])
        pyautogui.moveTo(x, y, duration=0.18)
        pyautogui.click()
        time.sleep(0.8)
        after_path = _capture_temp_screenshot("kira_after_click_")
        verification = verify_click(before_path, after_path, target)
        if verification.get("verified"):
            return {
                "success": True,
                "message": f"Clicked {target} at ({x}, {y}) and verified the result.",
                "x": x,
                "y": y,
                "confidence": confidence,
            }
        return {
            "success": False,
            "message": f"I clicked {target} at ({x}, {y}), but I could not visually verify the expected change. {verification.get('reason', '')}".strip(),
            "x": x,
            "y": y,
            "confidence": confidence,
        }
    except Exception as exc:
        logging.exception("Vision click failed")
        return {
            "success": False,
            "message": f"I could not complete the visual click: {exc}",
        }
    finally:
        for path in (before_path, after_path):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


def analyze_screen(question: str = "Describe what is visible on my screen.") -> str:
    """Capture the desktop and ask the configured local vision model to analyze it."""
    screenshot_path = None
    try:
        fd, screenshot_path = tempfile.mkstemp(prefix="kira_vision_", suffix=".png")
        os.close(fd)
        pyautogui.screenshot(screenshot_path)
        prompt = (
            "You are KIRA's local computer-vision module. Analyze the supplied Windows screenshot. "
            "Answer the user's request directly and concisely. Identify visible applications, windows, "
            "buttons, text, dialogs, errors, and other useful UI elements when relevant. Do not invent "
            "anything that is not visible. If the user asks to find something, state where it appears "
            "approximately (for example: top-left, center, bottom-right) and describe its visible label. "
            "Do not claim to click or change anything. User request: "
            + str(question or "Describe the screen.")
        )
        response = chat(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [screenshot_path],
                }
            ],
            options={"num_ctx": 4096, "temperature": 0.2, "num_predict": 450},
        )
        answer = clean_chat_response(response.get("message", {}).get("content", ""))
        answer = personalize_address(answer)
        return answer or "I could not get a useful description from the vision model."
    except Exception as exc:
        logging.exception("Vision analysis failed")
        return (
            f"Vision analysis is unavailable. Make sure Ollama has the vision model "
            f"'{VISION_MODEL}' installed. Details: {exc}"
        )
    finally:
        if screenshot_path:
            try:
                os.remove(screenshot_path)
            except OSError:
                pass


def ask_agent(command: str):
    """Legacy one-shot planner (no thought, no learning).

    Kept for backwards compatibility; the main loop now uses think_about().
    """
    try:
        response = call_ollama(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": command},
            ],
            options={
                "num_ctx": 4096,
                "temperature": 0,
                "num_predict": 500,
            },
        )
        content = clean_json(response["message"]["content"])

        logging.info("AGENT RAW JSON: %s", content)

        result = json.loads(content)

        logging.info("AGENT ACTION: %s", result)

        return result
    except Exception as exc:
        print(f"KIRA: Local model unavailable or returned invalid JSON: {exc}")
        return {"action": "none"}


def think_about(command: str) -> kira_thought.Thought:
    """The mind's thinking pass: recall → LLM plan (with a thought trace)."""
    return kira_thought.think(command, call_ollama)


def last_thought() -> "kira_thought.Thought | None":
    return kira_thought.last_thought()


def learn_from(command: str, action: dict, source: str, succeeded: bool, language: str = "en"):
    """Record an episode and strengthen/demote the learning behind it.

    Returns an optional follow-up: once a learning reaches the configured
    success streak, KIRA offers to consolidate it into a permanent shortcut.
    """
    normalized = kira_memory.normalize_agent_command(command)
    kira_thought.reflect(
        normalized,
        action,
        source,
        "success" if succeeded else "failed",
    )
    if not succeeded:
        return None
    recalled = kira_memory.recall_action(normalized)
    if not isinstance(recalled, dict):
        return None
    try:
        promote_after = int(
            CONFIG.get("skill_promote_after", kira_learning.PROMOTE_AFTER)
        )
    except (TypeError, ValueError):
        promote_after = kira_learning.PROMOTE_AFTER
    offer = kira_learning.check_promotion(normalized, recalled, promote_after)
    if not offer:
        return None
    return kira_learning.say(
        "promotion_offer", language, command=normalized, count=promote_after
    )


def ask_chat(command: str):
    global _CHAT_HISTORY

    command = str(command or "").strip()

    if not command:
        return ""

    history_limit = max(
        4,
        int(CONFIG.get("chat_history_limit", 16)),
    )

    language = detect_language(command)
    # ---------------------------------------------------------
    # FORGET SPECIFIC MEMORY
    # ---------------------------------------------------------

    forget_patterns = [
        (
            r"forget\s+(?:my\s+)?name\??",
            "identity",
            "name",
        ),
        (
            r"forget\s+(?:my\s+)?favorite\s+(?:programming\s+)?language\??",
            "preference",
            "favorite_programming_language",
        ),
        (
            r"forget\s+(?:my\s+)?favorite\s+language\??",
            "preference",
            "favorite_programming_language",
        ),
    ]

    for pattern, category, memory_key in forget_patterns:
        if re.fullmatch(
            pattern,
            command,
            flags=re.IGNORECASE,
        ):
            if kira_memory.forget_memory(
                category,
                memory_key,
            ):
                return "Understood. I have forgotten that memory."

            return "I don't have that memory stored."
    # ---------------------------------------------------------
    # DETERMINISTIC PERSONAL MEMORY
    # Do not ask the small LLM to interpret simple user facts.
    # ---------------------------------------------------------

    memory_patterns = [
        (
            r"(?:what|which)\s+is\s+my\s+favorite\s+(?:programming\s+)?language\??",
            "favorite_programming_language",
        ),
        (
            r"what\s+is\s+my\s+name\??",
            "name",
        ),
    ]

    for pattern, memory_key in memory_patterns:
        if re.fullmatch(
            pattern,
            command,
            flags=re.IGNORECASE,
        ):
            if memory_key == "favorite_programming_language":
                value = kira_memory.get_memory(
                    "preference",
                    "favorite_programming_language",
                    None,
                )

                if value:
                    return (
                        f"Your favorite programming language is {value}."
                    )

                return (
                    "I don't have your favorite programming language "
                    "stored in memory."
                )

            if memory_key == "name":
                value = kira_memory.get_memory(
                    "identity",
                    "name",
                    None,
                )

                if value:
                    return f"Your name is {value}."

                return "I don't have your name stored in memory."

    # ---------------------------------------------------------
    # EXACT PREVIOUS USER STATEMENT
    # ---------------------------------------------------------

    if re.fullmatch(
        r"what\s+(?:did\s+i\s+tell\s+you|did\s+i\s+say)\??",
        command,
        flags=re.IGNORECASE,
    ):
        previous_user_messages = [
            item
            for item in _CHAT_HISTORY
            if item.get("role") == "user"
        ]

        if previous_user_messages:
            # Ignore the current memory question itself.
            previous_user_messages = [
                item
                for item in previous_user_messages
                if str(
                    item.get("content", "")
                ).strip().lower() != command.strip().lower()
            ]

            if previous_user_messages:
                return (
                    "You told me: "
                    + str(
                        previous_user_messages[-1].get(
                            "content",
                            "",
                        )
                    )
                )

        return "I don't have a previous user statement available."

    # ---------------------------------------------------------
    # SAVE USER MESSAGE
    # ---------------------------------------------------------

    _CHAT_HISTORY.append(
        {
            "role": "user",
            "content": command,
        }
    )

    try:
        # Save the conversation permanently.
        kira_memory.save_message(
            _SESSION_ID,
            "user",
            command,
        )

        # Detect explicit high-confidence personal facts.
        kira_memory.remember_explicit_fact(command)

        # -----------------------------------------------------
        # LOAD STRUCTURED MEMORY
        # -----------------------------------------------------

        stored_memories = kira_memory.load_memories()

        memory_facts = []

        for memory in stored_memories[:20]:
            key = str(
                memory.get("key", "")
            ).strip()

            value = str(
                memory.get("value", "")
            ).strip()

            if key and value:
                memory_facts.append(
                    f"- The USER's "
                    f"{key.replace('_', ' ')} is: {value}"
                )

        # -----------------------------------------------------
        # BUILD MODEL MESSAGES
        # -----------------------------------------------------

        messages = [
            {
                "role": "system",
                "content": build_chat_system_prompt(language),
            }
        ]

        if memory_facts:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "PERSISTENT USER FACTS:\n"
                        "These are explicit facts stated by the USER.\n"
                        "They belong to the USER, not KIRA.\n"
                        "Treat them as exact records.\n"
                        "Never convert them into KIRA's own preferences.\n\n"
                        + "\n".join(memory_facts)
                    ),
                }
            )

        # Add recent conversation.
        messages.extend(
            _CHAT_HISTORY[-history_limit:]
        )

        response = call_ollama(
            messages=messages,
            options={
                "num_ctx": 4096,
                "temperature": 0.65,
                "top_p": 0.9,
                "num_predict": 450,
            },
        )

        answer = clean_chat_response(
            response["message"]["content"]
        )

        if not answer:
            raise ValueError(
                "empty model response"
            )

        _CHAT_HISTORY.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        # Save KIRA's answer permanently too.
        kira_memory.save_message(
            _SESSION_ID,
            "assistant",
            answer,
        )

        logging.info(
            "Chat response generated for: %s",
            command,
        )

        return answer

    except Exception as exc:
        logging.warning(
            "Chat response failed: %s",
            exc,
        )

        if _CHAT_HISTORY:
            _CHAT_HISTORY.pop()

        return personalize_address(
            "I cannot reach Ollama right now sir. "
            "Please start Ollama with `ollama serve`, "
            "then try again."
        )

def reset_chat():
    global _SESSION_ID

    _CHAT_HISTORY.clear()

    _SESSION_ID = kira_memory.new_session_id()

    logging.info(
        "Started a new KIRA conversation session: %s",
        _SESSION_ID,
    )

def is_chat_question(text: str) -> bool:
    lower = (text or "").strip().lower()
    question_starters = (
        "what ",
        "why ",
        "how ",
        "when ",
        "where ",
        "who ",
        "can you ",
        "could you ",
        "explain ",
        "tell me ",
        "est-ce",
        "pourquoi ",
        "comment ",
        "quand ",
        "où ",
        "ما ",
        "ماذا ",
        "لماذا ",
        "كيف ",
        "متى ",
        "أين ",
    )
    return lower.endswith("?") or lower.startswith(question_starters)


def recognize_offline(audio, sample_rate):
    model_path = str(CONFIG.get("offline_model_path", "") or "").strip()
    if not model_path or not os.path.isdir(model_path):
        return None
    try:
        from vosk import KaldiRecognizer, Model

        recognizer = KaldiRecognizer(Model(model_path), sample_rate)
        recognizer.AcceptWaveform(audio.frame_data)
        result = json.loads(recognizer.FinalResult())
        text = (result.get("text") or "").strip()
        return text or None
    except Exception as exc:
        logging.warning("Offline recognition unavailable: %s", exc)
        return None


def open_app(target: str):
    key = (target or "").strip().lower()
    exe = APP_ALIASES.get(key, key)
    if os.path.isdir(exe) or os.path.isfile(exe):
        try:
            os.startfile(exe)
            return True
        except Exception:
            return False
    if not exe.endswith(".exe"):
        exe = f"{exe}.exe"

    try:
        subprocess.Popen(exe)
        return True
    except Exception:
        try:
            os.startfile(exe)
            return True
        except Exception:
            return False


def open_url(target: str):
    url = (target or "").strip()
    if not url:
        return False
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    webbrowser.open(url)
    return True


def press_key(target: str):
    key = (target or "").strip().lower()
    if not key:
        return False
    key = KEY_ALIASES.get(key, key)
    pyautogui.press(key)
    return True


def type_text(text: str):
    if not text:
        return False
    pyautogui.write(text)
    return True


def search_web(query: str):
    q = quote_plus((query or "").strip())
    if not q:
        return False
    url = f"https://www.google.com/search?q={q}"
    webbrowser.open(url)
    return True


def mouse_move(x, y):
    try:
        pyautogui.moveTo(int(float(x)), int(float(y)), duration=0.25)
        return True
    except Exception:
        return False


def close_current_window():
    try:
        pyautogui.hotkey("alt", "f4")
        return True
    except Exception:
        return False


def minimize_current_window():
    try:
        pyautogui.hotkey("win", "down")
        return True
    except Exception:
        return False


def maximize_current_window():
    try:
        pyautogui.hotkey("win", "up")
        return True
    except Exception:
        return False


def switch_app():
    try:
        pyautogui.hotkey("alt", "tab")
        return True
    except Exception:
        return False


def open_folder(target: str):
    key = (target or "").strip().lower()
    folder = APP_ALIASES.get(key, (target or "").strip())
    if not folder:
        return False
    try:
        os.startfile(folder)
        return True
    except Exception:
        return False


def take_screenshot():
    try:
        pyautogui.screenshot("kira_screenshot.png")
        return True
    except Exception:
        return False


def send_media_key(key):
    try:
        pyautogui.press(key)
        return True
    except Exception:
        return False


def lock_pc():
    try:
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], shell=True)
        return True
    except Exception:
        return False


def show_desktop():
    try:
        pyautogui.hotkey("win", "d")
        return True
    except Exception:
        return False


def clipboard_copy():
    try:
        pyautogui.hotkey("ctrl", "c")
        return True
    except Exception:
        return False


def clipboard_paste():
    try:
        pyautogui.hotkey("ctrl", "v")
        return True
    except Exception:
        return False


def read_clipboard():
    try:
        value = pyperclip.paste().strip()

        if not value:
            return personalize_address("The clipboard is empty, sir.")

        preview = value[:500]

        if len(value) > 500:
            preview += "..."

        return personalize_address(f"The clipboard contains: {preview}")

    except Exception as exc:
        logging.exception("Clipboard read failed")
        return personalize_address(f"I could not read the clipboard, sir. {exc}")


def system_info():
    try:
        memory = psutil.virtual_memory()
        battery = psutil.sensors_battery()

        battery_text = (
            f" Battery is at {battery.percent:.0f} percent." if battery else ""
        )

        return (
            f"System: {platform.system()} {platform.release()}. "
            f"CPU usage: {psutil.cpu_percent(interval=0.2):.0f}%. "
            f"Memory usage: {memory.percent:.0f}%.{battery_text}"
        )

    except Exception as exc:
        logging.exception("System information failed")
        return f"Unable to read system information: {exc}"


def help_command():
    return personalize_address(
        "I can open apps and websites, type text, search the web, "
        "control volume and media, manage windows, read the clipboard, "
        "report system status, analyze your screen, locate things on screen, "
        "and answer questions using my local AI, sir."
    )


def report_time():
    return personalize_address(
        f"It is {datetime.now().strftime('%I:%M %p').lstrip('0')} sir."
    )


def report_date():
    return personalize_address(
        f"Today is {datetime.now().strftime('%A, %B %d, %Y')} sir."
    )


def set_address(target: str):
    key = (target or "").strip().lower()
    if key not in ADDRESS_OPTIONS:
        return False
    CONFIG["preferred_address"] = key
    save_config()
    speak(f"Understood. I will address you as {ADDRESS_OPTIONS[key]}.")
    return True


def run_shortcut(name: str):
    actions = CONFIG.get("shortcuts", {}).get(name.lower())
    if not isinstance(actions, list) or not actions:
        return False
    logging.info("Running shortcut: %s", name)
    return all(execute_action(action) for action in actions if isinstance(action, dict))


def execute_action(action_data):
    if not isinstance(action_data, dict):
        return False

    action = (action_data.get("action") or "none").strip().lower()

    # ---------------------------------------------------------
    # MULTI-STEP SEQUENCE
    # ---------------------------------------------------------
    if action == "sequence":
        steps = action_data.get("steps", [])

        if not isinstance(steps, list) or not steps:
            return "I could not determine the sequence of actions, sir."

        completed = 0

        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue

            step_action = str(step.get("action", "")).strip().lower()

            if not step_action or step_action == "sequence":
                continue

            logging.info("SEQUENCE STEP %s/%s: %s", index, len(steps), step)

            try:
                step_result = execute_action(step)

                if isinstance(step_result, str):
                    if step_result:
                        completed += 1
                elif step_result:
                    completed += 1
                else:
                    logging.warning("Sequence step %s failed: %s", index, step)
                    return f"I could not complete step {index}, sir."

            except Exception:
                logging.exception("Sequence step %s failed", index)
                return f"The sequence stopped at step {index}, sir."

        if completed == 0:
            return "I could not execute the requested sequence, sir."

        return f"Completed {completed} action" f"{'s' if completed != 1 else ''}, sir."

    # ---------------------------------------------------------
    # NORMAL ACTIONS
    # ---------------------------------------------------------

    if action == "open_app":
        return open_app(str(action_data.get("target", "")))

    if action == "open_url":
        return open_url(str(action_data.get("target", "")))

    if action == "type":
        return type_text(str(action_data.get("text", "")))

    if action == "press":
        return press_key(str(action_data.get("target", "")))

    if action == "search":
        return search_web(str(action_data.get("query", "")))

    if action == "mouse_move":
        return mouse_move(action_data.get("x"), action_data.get("y"))

    if action == "click":
        pyautogui.click()
        return True

    if action == "close_window":
        return close_current_window()

    if action == "minimize_window":
        return minimize_current_window()

    if action == "maximize_window":
        return maximize_current_window()

    if action == "switch_app":
        return switch_app()

    if action == "open_folder":
        return open_folder(str(action_data.get("target", "")))

    if action == "screenshot":
        return take_screenshot()

    if action == "volume_up":
        return send_media_key("volumeup")

    if action == "volume_down":
        return send_media_key("volumedown")

    if action == "mute":
        return send_media_key("volumemute")

    if action == "media_play_pause":
        return send_media_key("playpause")

    if action == "media_next":
        return send_media_key("nexttrack")

    if action == "media_previous":
        return send_media_key("prevtrack")

    if action == "lock_pc":
        return lock_pc()

    if action == "show_desktop":
        return show_desktop()

    if action == "copy":
        return clipboard_copy()

    if action == "paste":
        return clipboard_paste()

    if action == "read_clipboard":
        return read_clipboard()

    if action == "system_info":
        return system_info()

    if action == "help":
        return help_command()

    if action == "time":
        return report_time()

    if action == "date":
        return report_date()

    if action == "set_address":
        return set_address(str(action_data.get("target", "")))

    if action == "shortcut":
        return run_shortcut(str(action_data.get("target", "")))

    if action == "remember":
        target = str(
            action_data.get("target", "")
        ).strip()

        if not target:
            return False

        kira_memory.save_memory(
            category="user_preference",
            key="general",
            value=target,
        )

        return True

    if action == "calc":
        expression = str(action_data.get("expression", "")).strip()
        language = str(action_data.get("language", "en"))
        return personalize_address(
            kira_calculator.calculate_reply(expression, language)
        )

    if action == "remind":
        language = str(action_data.get("language", "en"))
        reminder_text = str(action_data.get("text", "")).strip()
        try:
            seconds_value = float(action_data.get("seconds", 0))
        except (TypeError, ValueError):
            return False
        if seconds_value <= 0 or not reminder_text:
            return False
        kira_reminders.add_reminder(seconds_value, reminder_text, language)
        return personalize_address(
            kira_reminders.confirmation(seconds_value, reminder_text, language)
        )

    if action == "reminders_list":
        language = str(action_data.get("language", "en"))
        return personalize_address(kira_reminders.describe_active(language))

    if action == "reminders_clear":
        language = str(action_data.get("language", "en"))
        cancelled = kira_reminders.cancel_all()
        return personalize_address(
            kira_reminders.cleared_message(cancelled, language)
        )

    if action == "agent_learnings":
        language = str(action_data.get("language", "en"))
        return personalize_address(
            kira_thought.describe_learnings(language=language)
        )

    if action == "agent_forget":
        language = str(action_data.get("language", "en"))
        cleared = kira_memory.clear_learnings()
        return personalize_address(
            kira_thought.cleared_message(cleared, language)
        )

    # ── the suit: self-awareness, monitoring, security, learning ─────
    alang = str(action_data.get("language", "en") or "en")

    if action == "self_report":
        return personalize_address(
            kira_thought.self_report(alang, models_online=_models_online())
        )

    if action == "self_review":
        return personalize_address(kira_thought.self_review(alang))

    if action == "habit_hint":
        return personalize_address(kira_thought.habit_hint(language=alang))

    if action == "monitor_on":
        start_watchdog(language=alang)
        return personalize_address(_suit_reply("monitor_on", alang))

    if action == "monitor_off":
        kira_monitor.stop()
        return personalize_address(_suit_reply("monitor_off", alang))

    if action == "privacy_blur":
        execute_action({"action": "show_desktop"})
        execute_action({"action": "mute"})
        return personalize_address(kira_security.blur_reply(alang))

    if action == "secure_lab":
        kira_security.lock()
        execute_action({"action": "lock_pc"})
        return personalize_address(kira_security.lock_reply(alang))

    if action == "unlock_lab":
        verdict = str(action_data.get("verdict", "unlock"))
        if verdict == "deny":
            return personalize_address(kira_security.deny_reply(alang))
        if not kira_security.is_locked():
            return personalize_address(_suit_reply("lab_not_locked", alang))
        kira_security.unlock()
        return personalize_address(kira_security.unlock_reply(alang))

    if action == "undo_last":
        entry = kira_undo.take_last()
        if entry is None:
            return personalize_address(_suit_reply("undo_nothing", alang))
        inverse = entry.get("inverse") or {}
        if not inverse or not execute_action(inverse):
            return personalize_address(_suit_reply("undo_failed", alang))
        kira_undo.record(str(entry.get("command", "")), inverse)
        return personalize_address(
            _suit_reply("undo_done", alang, command=str(entry.get("command", "")))
        )

    if action == "press_combo":
        keys = [str(k).strip() for k in action_data.get("keys", []) if str(k).strip()]
        if not keys:
            return False
        pyautogui.hotkey(*keys)
        return personalize_address(f"Pressed {'+'.join(keys)} sir.")

    if action == "routine_start":
        if kira_learning.is_recording():
            return personalize_address(
                kira_learning.say(
                    "recording_already",
                    alang,
                    count=len(kira_learning.recorded_steps()),
                )
            )
        kira_learning.start_recording()
        return personalize_address(kira_learning.say("recording_started", alang))

    if action == "routine_stop":
        if not kira_learning.is_recording():
            return personalize_address(kira_learning.say("not_recording", alang))
        kira_learning.cancel_recording()
        return personalize_address(kira_learning.say("recording_cancelled", alang))

    if action == "routine_name":
        name = str(action_data.get("name", "")).strip()
        if not kira_learning.is_recording():
            return personalize_address(kira_learning.say("not_recording", alang))
        steps = kira_learning.recorded_steps()
        if not steps or not name:
            kira_learning.cancel_recording()
            return personalize_address(kira_learning.say("recording_empty", alang))
        ok, saved_name = kira_learning.finish_recording(name)
        if not ok:
            return personalize_address(_suit_reply("routine_save_failed", alang))
        return personalize_address(
            kira_learning.say(
                "recording_saved", alang, name=saved_name, count=len(steps)
            )
        )

    if action == "correct_last":
        global _LAST_COMMAND, _LAST_ACTION
        if not _LAST_COMMAND or _LAST_ACTION is None:
            return personalize_address(kira_learning.say("correction_none", alang))
        kira_memory.learn_from_outcome(
            kira_memory.normalize_agent_command(_LAST_COMMAND), _LAST_ACTION, False
        )
        _LAST_COMMAND, _LAST_ACTION = None, None
        return personalize_address(kira_learning.say("correction_ack", alang))

    if action == "skill_promote":
        pending = kira_learning.pending_promotion()
        if not isinstance(pending, dict):
            return personalize_address(kira_learning.say("promotion_none", alang))
        promoted_action = pending.get("action")
        steps = [promoted_action] if isinstance(promoted_action, dict) else []
        promoted = _save_shortcut(pending["command"], steps)
        kira_learning.clear_promotion()
        if not promoted:
            return personalize_address(_suit_reply("routine_save_failed", alang))
        return personalize_address(
            kira_learning.say("promotion_saved", alang, name=pending["command"])
        )

    if action == "skill_skip":
        if kira_learning.pending_promotion() is None:
            return personalize_address(kira_learning.say("promotion_none", alang))
        kira_learning.clear_promotion()
        return personalize_address(kira_learning.say("promotion_skipped", alang))

    if action == "weather":
        city = str(action_data.get("target") or "")
        return personalize_address(kira_weather.report(city, alang))

    if action == "home_control":
        name = str(action_data.get("name", "")).strip()
        turn_on = str(action_data.get("mode", "on")).lower() != "off"
        if not name:
            return False
        return personalize_address(kira_homeassist.control(name, turn_on, alang))

    return False


def describe_action(action_data):
    if not isinstance(action_data, dict):
        return "perform the requested action"

    action = (action_data.get("action") or "none").strip().lower()

    if action == "open_app":
        target = str(action_data.get("target", "app")).strip() or "app"
        return f"open the {target} app"

    if action == "open_url":
        target = str(action_data.get("target", "website")).strip() or "website"
        return f"open the website {target}"

    if action == "type":
        text = str(action_data.get("text", "text")).strip() or "text"
        return f"type {text}"

    if action == "press":
        target = str(action_data.get("target", "key")).strip() or "key"
        return f"press the {target} key"

    if action == "search":
        query = str(action_data.get("query", "search")).strip() or "search"
        return f"search the web for {query}"

    if action == "mouse_move":
        x = action_data.get("x", 0)
        y = action_data.get("y", 0)
        return f"move the mouse to {x}, {y}"

    if action == "click":
        return "click the mouse"

    return "perform the requested action"


def confirm_action(action_name: str, details: str) -> bool:
    prompt = f"I am about to {action_name}. {details}. Do you confirm?"
    speak(prompt)
    text = listen_for_command(timeout=10, phrase_timeout=5)
    if not text:
        return False

    lower = text.lower().strip()
    positives = {
        "yes",
        "yeah",
        "yep",
        "confirm",
        "confirmed",
        "do it",
        "go ahead",
        "proceed",
        "okay",
        "ok",
        "sure",
        "affirmative",
    }
    negatives = {"no", "cancel", "cancel it", "stop", "abort", "never mind"}

    if any(token in lower for token in negatives):
        return False

    return any(token in lower for token in positives)


def normalize_command(command: str) -> str:
    text = (command or "").strip()
    if not text:
        return ""
    lower = text.lower()

    for prefix in [WAKE_WORD, "hey kira", "hello kira", "kira please", "okay kira"]:
        if lower.startswith(prefix):
            text = text[len(prefix) :].strip()
            # Tolerate a separator between wake word and command,
            # e.g. "kira, open chrome" or "kira: open chrome".
            text = text.lstrip(" ,;:-").strip()
            break
    return text.strip()


def is_wake_phrase(command: str) -> bool:
    lower = (command or "").lower()
    if not lower:
        return False
    return (
        WAKE_WORD in lower
        or "hey kira" in lower
        or "hello kira" in lower
        or "kira" in lower
    )


def requires_confirmation(action: str) -> bool:
    """Whether an action must be voice-confirmed before execution.

    Configurable through the "require_confirmation" list in kira_config.json;
    an explicit empty list disables confirmation prompts entirely.
    """
    name = str(action or "").strip().lower()
    configured = CONFIG.get("require_confirmation")
    if isinstance(configured, list):
        return name in {str(item).strip().lower() for item in configured}
    return name in {"search", "mouse_move", "click", "lock_pc"}


def should_process_command(command: str) -> bool:
    text = (command or "").strip()
    if not text:
        return False
    # When "require_wake_word" is enabled, only commands containing the wake
    # word are processed — unless conversation mode is currently active,
    # which keeps the channel open.
    if CONFIG.get("require_wake_word") and not _CONVERSATION_MODE:
        return is_wake_phrase(text)
    return True


def _battery_percentage():
    """Battery level for the briefing; None when unreadable or on desktop."""
    try:
        battery = psutil.sensors_battery()
    except Exception:
        return None
    return float(battery.percent) if battery is not None else None


def startup_sequence():
    """Boot theater: calibration-style banner, then a spoken briefing."""
    learnings = kira_memory.learnings_summary()
    counts = {
        "memories": len(kira_memory.load_memories()),
        "learnings": learnings["count"],
        "episodes": kira_memory.episode_counts()["total"],
        "model": MODEL,
        "vision": VISION_MODEL,
    }
    for line in kira_personality.boot_lines(VERSION, counts, humor=_humor()):
        print(f"  > {line}")
    language = str(USER_MEMORY.get("language", "en") or "en")
    speak(
        personalize_address(
            kira_briefing.briefing(
                language=language,
                humor=_humor(),
                battery_percent=_battery_percentage(),
            )
        )
    )


def main():
    global _CONVERSATION_MODE, _LAST_COMMAND, _LAST_ACTION
    print("=" * 60)
    print("KIRA VOICE AGENT")
    print("Local Windows assistant with voice controls")
    print("Type 'exit' to quit or say 'KIRA exit'")
    print("=" * 60)

    try:
        startup_sequence()
        start_background_tasks()

        while True:
            command = listen_for_command(timeout=20, phrase_timeout=10)
            if not command:
                continue

            logging.info("Heard command: %s", command)

            if not should_process_command(command):
                continue

            cleaned = normalize_command(command)
            if not cleaned:
                continue

            if cleaned.lower() in {"exit", "quit", "goodbye", "bye"}:
                speak(personalize_address("Goodbye sir."))
                break
            lower = cleaned.lower()

            if not cleaned:
                continue

            if lower in {"exit", "quit", "goodbye", "bye"}:
                speak(personalize_address("Goodbye sir."))
                break

            gate_reply = lab_gate(cleaned)
            if gate_reply is not None:
                speak(gate_reply)
                continue

            result = parse_simple_command(cleaned)
            planned_by = "parser"
            if result is None and is_chat_question(cleaned):
                speak(ask_chat(cleaned))
                continue
            if result is None:
                # think before acting: recall past learnings, then plan
                # with the local model inside a thought envelope
                thought = think_about(cleaned)
                if thought.text:
                    print(f"[thinking] {thought.text}")
                result = thought.action
                planned_by = thought.source
            action = (result or {}).get("action", "none")

            if action == "conversation_on":
                _CONVERSATION_MODE = True
                speak(personalize_address("Conversation mode is on sir."))
                continue

            if action == "conversation_off":
                _CONVERSATION_MODE = False
                speak(personalize_address("Conversation mode is off sir."))
                continue

            if action == "chat_reset":
                reset_chat()
                speak(personalize_address("New conversation started sir."))
                continue

            if action == "mode_info":
                speak(
                    personalize_address(
                        "Unified mode is active sir. I can answer questions and control the computer in the same conversation."
                    )
                )
                continue

            if action == "none":
                answer = ask_chat(cleaned)
                speak(answer)
                continue

            if action == "exit":
                speak(personalize_address("Goodbye sir."))
                break

            if requires_confirmation(action):
                target_desc = describe_action(result)
                allowed = confirm_action(action.replace("_", " "), target_desc)
                if not allowed:
                    lang = detect_language(cleaned)
                    speak(build_reply(lang, "none"))
                    continue

            lang = detect_language(cleaned)
            success = execute_action(result)
            promotion_note = None
            if planned_by in {"llm", "memory"}:
                # reflect: episodes + strengthen/demote the learning
                _LAST_COMMAND, _LAST_ACTION = cleaned, result
                promotion_note = learn_from(
                    cleaned, result, planned_by, bool(success), language=lang
                )
            if success:
                # suit bookkeeping: macro recording + undo stack
                kira_learning.capture(result)
                kira_undo.record(cleaned, result)
                action_name = str(action).lower()
                # Actions returning a string speak their own result
                # (time, date, system info, clipboard, help, sequences,
                # calculations, reminders).
                if isinstance(success, str):
                    speak(success)
                else:
                    target_text = ""
                    if action == "open_app":
                        target_text = str((result or {}).get("target", "app"))
                    elif action == "open_url":
                        target_text = str((result or {}).get("target", "site"))
                    elif action == "search":
                        target_text = str((result or {}).get("query", "request"))
                    elif action == "press":
                        target_text = str((result or {}).get("target", "key"))
                    elif action == "close_window":
                        target_text = "window"
                    elif action == "minimize_window":
                        target_text = "window"
                    elif action == "maximize_window":
                        target_text = "window"
                    elif action == "switch_app":
                        target_text = "application"
                    elif action == "screenshot":
                        target_text = "screenshot"
                    elif action == "open_folder":
                        target_text = str((result or {}).get("target", "folder"))

                    if action_name == "close_window":
                        speak(build_reply(lang, "close_window", target_text))
                    elif action_name == "minimize_window":
                        speak(build_reply(lang, "minimize_window", target_text))
                    elif action_name == "maximize_window":
                        speak(build_reply(lang, "maximize_window", target_text))
                    elif action_name == "switch_app":
                        speak(build_reply(lang, "switch_app", target_text))
                    elif action_name == "screenshot":
                        speak(build_reply(lang, "screenshot", target_text))
                    else:
                        speak(build_reply(lang, action_name, target_text))
                if promotion_note:
                    speak(promotion_note)
            else:
                lang = detect_language(cleaned)
                speak(build_reply(lang, "none"))
    except KeyboardInterrupt:
        print("\nKIRA: Stopped by user.")


if __name__ == "__main__":
    main()
