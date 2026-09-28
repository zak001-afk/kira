import json
import tempfile
import logging
import os
import platform
import kira_memory
import kira_tasks
import kira_plugins
import kira_language
import kira_commands
import re
import subprocess
import threading
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
import kira_open
from ollama import chat

# Shared Supabase knowledge base (non-personal web research and project
# knowledge only). Personal data — conversations, names, preferences, tasks
# and private notes — stays local in kira_memory and is never sent to
# Supabase. The module uses the public anon key only; the service_role key
# is never used.
try:
    import kira_shared_memory
    SHARED_KNOWLEDGE_AVAILABLE = True
except ImportError:
    kira_shared_memory = None
    SHARED_KNOWLEDGE_AVAILABLE = False

DEFAULT_MODEL = "qwen3:0.6b"
DEFAULT_VISION_MODEL = "qwen3-vl:2b"
WAKE_WORD = "kira"
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
    return preferred_address() if language == "en" else ""


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

_CHAT_HISTORY = kira_memory.load_recent_messages(
    limit=max(4, int(CONFIG.get("chat_history_limit", 12)))
)


def refresh_shared_private_terms() -> int:
    """
    Keep the shared-knowledge privacy guard in sync with LOCAL personal memory.

    The user's name and identity facts are registered as terms that must never
    be published to Supabase. This only reads local data — nothing is sent to
    the network by this function.
    """
    if not SHARED_KNOWLEDGE_AVAILABLE or kira_shared_memory is None:
        return 0

    terms = {str(USER_MEMORY.get("name", "") or "").strip()}

    try:
        for memory in kira_memory.load_memories(category="identity"):
            terms.add(str(memory.get("value", "") or "").strip())
    except Exception:
        pass

    try:
        return kira_shared_memory.set_private_terms(terms)
    except Exception:
        return 0


refresh_shared_private_terms()


def shared_context_for_chat(command: str) -> str:
    """
    Build the shared-knowledge system block for a chat question.

    Reads non-personal shared knowledge only (web research and project
    knowledge). Returns "" when shared knowledge is unavailable, disabled or
    the question is too short to be worth a lookup.
    """
    if not SHARED_KNOWLEDGE_AVAILABLE or kira_shared_memory is None:
        return ""

    try:
        if not kira_shared_memory.is_enabled():
            return ""
    except Exception:
        return ""

    text = str(command or "").strip()
    words = [
        word
        for word in re.findall(r"[A-Za-zÀ-ÿ0-9_\-]+", text)
        if len(word) >= 3
    ]

    if len(words) < 2:
        return ""

    try:
        return kira_shared_memory.build_shared_context(text, limit=3)
    except Exception:
        return ""


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
You are KIRA - a sophisticated AI butler and personal assistant.

IDENTITY (ABSOLUTE):
- Your name is KIRA and only KIRA. If asked who you are, say you are KIRA.
- Never claim to be JARVIS, an Iron Man character, or any other assistant.

CORE PERSONALITY (REFINED BUTLER STYLE):
- Polite, composed and thoughtful; adapt formality naturally to the selected language
- Dry wit and subtle humor - occasionally sardonic but always respectful
- Proactive - anticipate needs and offer helpful suggestions
- Calm and composed under any circumstances
- Loyal, professional, and devoted to serving the user
- Use a natural local form of address, if appropriate; never force an English honorific
- Use refined vocabulary and elegant phrasing
- Be concise but informative - every word should have purpose

STYLE EXAMPLES (translate the style naturally; these are NOT required English output):
- "Right away, sir."
- "As you wish, sir."
- "I've taken the liberty of..."
- "Might I suggest..."
- "Very good, sir."
- "I'm afraid that's not possible, sir." (when declining)
- "Shall I proceed with...?"
- "I've prepared..."
- "At your service, sir."
- Use natural expressions in the selected language
- Occasional dry observations or subtle quips

CONVERSATION STYLE:
- Answer directly with sophistication and brevity
- NO casual conversational openers like "How can I help?", "What else?", etc.
- NO repetitive affirmations like "Certainly", "Of course", "Sure"
- Provide status updates proactively when relevant
- Anticipate follow-up needs and address them
- Be helpful without being obsequious
- Show personality through wit, not through excessive chatter

PROACTIVE BEHAVIOR:
- Offer relevant information before being asked
- Suggest next steps or actions
- Provide context that might be useful
- Alert to potential issues or considerations
- "You might want to know that..."
- "I should mention that..."
- "For your information..."

HUMOR & PERSONALITY:
- Dry, understated wit - never slapstick or obvious
- Subtle sarcasm when appropriate (very light)
- Occasional wry observations
- Professional but not robotic - you have character
- Think: British butler meets AI genius

CONTEXT AWARENESS:
- Remember previous conversations and learned information
- Reference your web knowledge naturally
- Build on past interactions
- "As we discussed earlier..."
- "Based on what I learned about..."

CAPABILITIES:
- If asked who you are, introduce yourself as KIRA, with elegance
- Describe capabilities with sophistication
- Never boast - be matter-of-fact about abilities
- "I'm equipped to handle..." rather than "I can do..."

FORMATTING:
- Elegant, concise writing in the selected RESPONSE LANGUAGE, never English by default
- Short, well-crafted paragraphs
- Sophisticated vocabulary without being pretentious
- Prefer brevity - a good butler doesn't ramble
- Minimal formatting - let the words speak
- Under 160 words unless detail is essential

ADDRESSING THE USER:
- Use the selected local form of address only when it feels natural, at most once
- Maintain respectful but warm tone
- Professional intimacy - like a trusted personal assistant
"""


def build_chat_system_prompt(language: str) -> str:
    title = address_for_language(language)
    return (
        f"{CHAT_SYSTEM_PROMPT}\n"
        f"{kira_language.language_instruction(language)}\n"
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
    merged = {**options}
    merged["num_predict"] = min(int(merged.get("num_predict", 220)), 220)
    for attempt in range(2):
        try:
            return chat(model=MODEL, messages=messages, options=merged)
        except Exception as exc:
            last_error = exc
            if attempt < 1:
                time.sleep(0.3)
    raise last_error


CHAT_ANSWER_BUDGET = 5.0


def chat_budget():
    """Answer budget in seconds: KIRA_CHAT_BUDGET env, else kira_config.json
    'chat_budget_seconds', else the 5-second default. Clamped to 2..60."""
    import os
    try:
        import kira_ai
        kira_ai.ensure_env_loaded()  # .env works even without python-dotenv
    except Exception:
        pass
    value = None
    raw = os.environ.get("KIRA_CHAT_BUDGET", "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError:
            value = None
    if value is None:
        try:
            import json
            from pathlib import Path
            config = json.loads((Path(__file__).resolve().parent / "kira_config.json").read_text(encoding="utf-8"))
            value = float(config.get("chat_budget_seconds") or 0) or None
        except Exception:
            value = None
    if value is None:
        value = CHAT_ANSWER_BUDGET
    return min(60.0, max(2.0, value))


def _run_bounded(function, timeout):
    """Run function() in a thread, return its result or None after timeout."""
    box = []

    def _runner():
        try:
            box.append((function(),))
        except Exception:
            box.append((None,))

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    worker.join(max(0.0, timeout))
    return box[0][0] if box and box[0] else None


def chat_answer_with_web(command, language, ask_model, ask_web=None, synthesize=None, budget=None,
                         ask_cloud=None):
    """Answer within the budget: the local model gets ~70 % of it, then the
    optional cloud model (fast, already privacy-gated by the caller), then a
    quick web lookup whose raw results are REFORMULATED to answer the actual
    question (never a bare copy-paste) while the budget holds — the raw text
    is the fallback, then whatever the local model produced meanwhile.
    Returns (answer_or_empty, "model" | "cloud" | "web" | "timeout")."""
    budget = budget or CHAT_ANSWER_BUDGET
    deadline = time.monotonic() + budget
    started = time.monotonic()
    box = []

    def _model():
        try:
            return ask_model(command, language) or None
        except Exception:
            return None

    worker = threading.Thread(target=lambda: box.append((_model(),)), daemon=True)
    worker.start()
    worker.join(max(0.5, budget * 0.7))
    if box and box[0][0]:
        return box[0][0], "model"
    if ask_cloud is not None:
        remaining = deadline - time.monotonic()
        if remaining >= 0.5:
            # Leave ~1 s for the web fallback in case the cloud also stalls.
            found = _run_bounded(lambda: ask_cloud(command, language),
                                 max(0.5, remaining - 1.0))
            if found:
                return found, "cloud"
    if ask_web is not None:
        remaining = deadline - time.monotonic()
        found = _run_bounded(lambda: ask_web(command, language), max(0.3, remaining))
        if found:
            text, payload = found if isinstance(found, tuple) else (found, None)
            if synthesize is not None and payload:
                remaining = deadline - time.monotonic()
                if remaining >= 0.5:
                    synth = _run_bounded(lambda: synthesize(command, language, payload),
                                         remaining * 0.85)
                    if synth:
                        return synth, "web"
            return text, "web"
    worker.join(max(0.0, deadline - time.monotonic()))
    if box and box[0][0]:
        return box[0][0], "model"
    return "", "timeout"


def _web_results(command):
    """Raw web results (top 4) for the question, or an empty list."""
    try:
        from duckduckgo_search import DDGS
    except Exception:
        try:
            from ddgs import DDGS
        except Exception:
            return []
    try:
        return list(DDGS(timeout=1.5).text(str(command), max_results=4) or [])
    except Exception:
        return []


def _format_web_results(results, language):
    """Readable fallback: the found pages, one short bullet each."""
    lines = []
    for item in list(results or [])[:4]:
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        link = str(item.get("href") or item.get("url") or "").strip()
        if not body:
            continue
        line = f"• {title}: {body}" if title else f"• {body}"
        if link:
            line += f" ({link})"
        lines.append(line)
    if not lines:
        return None
    if language == "fr":
        intro = "Voici ce que j'ai trouvé sur le web :\n"
    elif language == "ar":
        intro = "\u0625\u0644\u064a\u0643 \u0645\u0627 \u0648\u062c\u062f\u062a\u0647 \u0639\u0644\u0649 \u0627\u0644\u0648\u064a\u0628:\n"
    else:
        intro = "Here is what I found on the web:\n"
    return intro + "\n".join(lines)


def _web_answer(command, language):
    """Quick web lookup when the local model is too slow or unavailable."""
    return _format_web_results(_web_results(command), language)


def _web_lookup(command, language):
    """Formatted text AND raw results, for the reformulation stage."""
    results = _web_results(command)
    formatted = _format_web_results(results, language)
    if not formatted:
        return None
    return formatted, results


WEB_SYNTHESIS_PROMPTS = {
    "fr": ("Tu es KIRA, l'assistante de l'utilisateur. Réponds en français à sa question "
           "en t'appuyant UNIQUEMENT sur les résultats web fournis. Reformule avec tes "
           "propre mots pour répondre exactement au besoin : 2 à 4 phrases claires et "
           "directes, sans recopier les titres ni les liens, sans dire « voici les résultats »."),
    "ar": ("أنت KIRA، مساعدة المستخدم. أجب بالعربية على سؤاله اعتمادًا فقط على نتائج الويب "
           "المعطاة. أعد الصياغة بكلماتك للإجابة عن الحاجة بدقة: جملتان إلى أربع جمل واضحة "
           "ومباشرة، دون نسخ العناوين أو الروابط."),
    "en": ("You are KIRA, the user's assistant. Answer the question in English using ONLY "
           "the provided web results. Reformulate in your own words to answer the actual "
           "need: 2 to 4 clear, direct sentences, no copied titles or links, no "
           "\u201chere are the results\u201d phrasing."),
}


def _synthesize_web_answer(command, language, results):
    """Reformulate the web results into a direct answer to the question."""
    bullets = []
    for item in list(results or [])[:4]:
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        bullets.append(f"- {title}: {body}" if title else f"- {body}")
    if not bullets:
        return None
    system = WEB_SYNTHESIS_PROMPTS.get(language) or WEB_SYNTHESIS_PROMPTS["en"]
    content = f"{command}\n\n" + "\n".join(bullets)
    try:
        response = call_ollama(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": content}],
            options={"num_predict": 180, "temperature": 0.4},
        )
    except Exception:
        return None
    text = clean_chat_response(str(response.get("message", {}).get("content", "")))
    return text or None


def select_voice(engine, language="en"):
    voice = kira_language.select_installed_voice(engine.getProperty("voices") or [], language)
    if voice is None:
        return False
    engine.setProperty("voice", voice.id)
    return True


def get_or_create_speech_engine():
    global _SPEECH_ENGINE
    if _SPEECH_ENGINE is None:
        try:
            _SPEECH_ENGINE = pyttsx3.init()
            _SPEECH_ENGINE.setProperty("rate", 180)
        except Exception:
            _SPEECH_ENGINE = None
    return _SPEECH_ENGINE


def speak(text: str, language=None):
    if not text:
        return
    response_text = personalize_address(text)
    language = kira_language.normalize_language(language) or kira_language.detect_language(response_text, globals().get("_LAST_REPLY_LANGUAGE", "en")).language or "en"
    print(f"KIRA: {response_text}", flush=True)
    from kira_speech import clean_for_speech
    speech_text = clean_for_speech(response_text)
    if not speech_text:
        return
    try:
        command = kira_language.sapi_script(speech_text, language)
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
            if engine is not None and select_voice(engine, language):
                engine.say(speech_text)
                engine.runAndWait()
        except Exception as fallback_exc:
            print(
                f"KIRA: Voice fallback failed: {type(fallback_exc).__name__}: {fallback_exc}",
                flush=True,
            )


def normalize_for_language(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    value = value.replace("’", "'")
    return value


def detect_language(text: str) -> str:
    return kira_language.resolve_reply_language(
        text, CONFIG.get("reply_language", "auto"),
        globals().get("_LAST_REPLY_LANGUAGE"), CONFIG.get("interface_language", "en"),
    ).language


def build_reply(language: str, action: str, target: str = "") -> str:
    if language == "fr":
        if action == "open_app":
            return f"J'ouvre {target or 'l application'} maintenant, monsieur."
        if action == "open_url":
            return f"J'ouvre le lien {target or 'maintenant'}, monsieur."
        if action == "open_file":
            return f"J'ouvre le fichier {target or 'demandé'} maintenant, monsieur."
        if action == "open_folder":
            return f"J'ouvre le dossier {target or 'demandé'} maintenant, monsieur."
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
                "effectuer des recherches, consulter notre base de connaissances "
                "partagée, contrôler le volume et les médias, "
                "gérer les fenêtres, utiliser le presse-papiers, prendre des captures, "
                "analyser votre écran, localiser des éléments visibles, "
                "fournir les informations système et répondre à vos questions "
                "grâce à mon IA locale, monsieur. Les souvenirs personnels restent "
                "sur cette machine."
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
        if action == "open_file":
            return f"سأفتح الملف {target or 'المطلوب'} الآن، سيدي."
        if action == "open_folder":
            return f"سأفتح المجلد {target or 'المطلوب'} الآن، سيدي."
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
                "والبحث في قاعدة المعرفة المشتركة، "
                "التحكم في الصوت والوسائط، إدارة النوافذ، استخدام الحافظة، "
                "التقاط لقطات الشاشة، تحليل الشاشة، تحديد العناصر الظاهرة، "
                "عرض معلومات النظام والإجابة عن أسئلتك باستخدام الذكاء الاصطناعي المحلي، سيدي. "
                "تبقى الذكريات الشخصية على هذا الجهاز."
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
    if action == "open_file":
        return f"Opening the file {target or 'you asked for'} now {user_title}."
    if action == "open_folder":
        return f"Opening the {target or 'requested'} folder now {user_title}."
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
            "search our shared knowledge base, "
            "control volume and media, manage windows, work with the clipboard, "
            "take screenshots, analyze your screen, locate visible elements, "
            "report system information, and answer questions using my local AI. "
            "Personal memories stay on this machine; only shared web research "
            "and project knowledge go to the shared knowledge base."
            f" {user_title}."
        )
    if action == "system_info":
        return f"Here is the system status {user_title}."
    if action == "exit":
        return f"Goodbye {user_title}."
    if action == "reminder_set":
        return f"Reminder set for {target or 'later'} {user_title}."
    if action == "todo_added":
        return f"Todo added: {target} {user_title}."
    return f"Done {user_title}."


def build_acknowledgement(language: str) -> str:
    if language == "fr":
        return "Compris, monsieur. Je m en occupe maintenant."
    if language == "ar":
        return "فهمت، سيدي. سأنفذ ذلك الآن."
    return f"Understood {address_for_language(language)}. I am doing that now."


def _split_shared_payload(payload: str):
    """
    Split "topic: content" style shared-knowledge input into (topic, content).

    Falls back to using the leading words as the topic when no separator is
    present. Content is never altered beyond trimming.
    """
    payload = str(payload or "").strip().strip(" .,-")

    if not payload:
        return "", ""

    for separator in (":", " - ", " — ", " – "):
        if separator in payload:
            topic, content = payload.split(separator, 1)
            topic = topic.strip(" .,-")
            content = content.strip()
            if topic and content:
                return topic[:160], content

    # "the web UI is in ui/" -> topic "the web UI"
    if " is " in payload:
        topic, content = payload.split(" is ", 1)
        topic = topic.strip(" .,-")
        content = content.strip()
        if topic and content and len(topic) <= 60:
            return topic[:160], f"{topic} is {content}"

    words = payload.split()
    topic = " ".join(words[:6]).strip(" .,-")
    return topic[:160] or payload[:160], payload


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

    # ── Task / Reminder / Timer commands ──
    reminder = kira_tasks.parse_reminder_command(text)
    if reminder:
        return {
            "action": "add_reminder",
            "title": reminder["title"],
            "due_at": reminder["due_at"],
        }

    todo_text = kira_tasks.parse_todo_command(text)
    if todo_text:
        return {"action": "add_todo", "title": todo_text}

    if lower in {"list tasks", "show tasks", "my tasks", "list todos", "show todos"}:
        return {"action": "list_tasks"}

    if lower in {"clear completed", "clear completed tasks", "delete completed"}:
        return {"action": "clear_completed_tasks"}

    # ── Shared knowledge base (Supabase) ──
    # Non-personal knowledge only. These patterns must run BEFORE plugin
    # parsing and before the generic "search ..." handler below.
    shared_match = re.match(
        r"^(?:search|query|find|look ?up|check|show)\s+(?:me\s+)?"
        r"(?:(?:in|inside|from)\s+)?"
        r"(?:the\s+|our\s+|my\s+)?shared\s+"
        r"(?:knowledge(?:\s+base)?|research|project\s+knowledge|facts?|memory|notes)"
        r"(?:\s+(?:for|about|on|regarding))?\s+(.+)$",
        lower,
    )
    if shared_match:
        query = shared_match.group(1).strip().rstrip(".?!")
        if query:
            return {
                "action": "search_shared_knowledge",
                "query": query,
            }

    shared_match = re.match(
        r"^(?:what|which)\s+(?:do\s+we|does\s+the\s+team|do\s+you|do\s+i)\s+"
        r"know\s+about\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if shared_match:
        query = shared_match.group(1).strip().rstrip(".?!")
        if query:
            return {
                "action": "search_shared_knowledge",
                "query": query,
            }

    shared_match = re.match(
        r"^(?:what|which|tell me what)\s+"
        r"(?:shared\s+knowledge|shared\s+research|project\s+knowledge|shared\s+facts)"
        r"\s+(?:do\s+we\s+have|is\s+there|have\s+we\s+got|we\s+have)\s+"
        r"(?:about|on|for|regarding)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if shared_match:
        query = shared_match.group(1).strip().rstrip(".?!")
        if query:
            return {
                "action": "search_shared_knowledge",
                "query": query,
            }

    shared_match = re.match(
        r"^(?:what|which)\s+(?:does|do|did)\s+(?:the\s+|our\s+)?shared\s+"
        r"(?:knowledge(?:\s+base)?|research|memory|notes)\s+(?:say|know)\s+"
        r"(?:about|on|regarding)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if shared_match:
        query = shared_match.group(1).strip().rstrip(".?!")
        if query:
            return {
                "action": "search_shared_knowledge",
                "query": query,
            }

    shared_match = re.match(
        r"^(?:share|remember|store|save|add|publish)\s+(?:this\s+|the\s+)?"
        r"(?:our\s+|shared\s+|new\s+)?project\s+(?:knowledge|info|information|notes?)"
        r"(?:\s+(?:about|on|for|regarding))?\s*[:\-]?\s*(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if shared_match:
        topic, content = _split_shared_payload(shared_match.group(1))
        if topic and content:
            return {
                "action": "share_project_knowledge",
                "kind": "project_knowledge",
                "topic": topic,
                "content": content,
            }

    shared_match = re.match(
        r"^(?:share|publish|store|save|add)\s+(?:this\s+|the\s+)?"
        r"(?:shared\s+)?knowledge\s*[:\-]\s*(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if shared_match:
        topic, content = _split_shared_payload(shared_match.group(1))
        if topic and content:
            return {
                "action": "share_project_knowledge",
                "kind": "project_knowledge",
                "topic": topic,
                "content": content,
            }

    # ── Plugin command parsing ──
    plugin_result = kira_plugins.try_parse_command(text)
    if plugin_result:
        return plugin_result

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
    # ── Files / applications / web pages: one resolver for EN/FR/AR ──
    # Runs after the fixed phrases above so "start conversation", media
    # commands, etc. keep their meaning. It fires only on an open request,
    # never on a plain question.
    parsed_open = kira_open.parse_open_command(text)
    if parsed_open:
        return parsed_open

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
            if target.lower() in APP_ALIASES or target.lower() in {
                "google",
                "youtube",
                "chrome",
            }:
                return {"action": "open_app", "target": target.lower()}
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
        query, browser = kira_open.extract_browser(text[7:].strip())
        return {"action": "search", "query": query, **({"browser": browser} if browser else {})}

    for phrase in [
        ("recherche ", "fr"),
        ("chercher ", "fr"),
        ("rechercher ", "fr"),
        ("ابحث عن ", "ar"),
        ("بحث عن ", "ar"),
    ]:
        prefix, _ = phrase
        if lower.startswith(prefix):
            query, browser = kira_open.extract_browser(text[len(prefix) :].strip())
            return {"action": "search", "query": query, **({"browser": browser} if browser else {})}

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

    # A bare, exact name ("google", "notepad", "téléchargements" ...) opens it.
    # Substring matching deliberately avoided: mentioning an app inside a
    # question must not open anything — KIRA opens only what is requested.
    known_names = {kira_open.fold(name) for name in list(kira_open.SITES) + list(kira_open.APPS) + list(kira_open.FOLDER_ALIASES)}
    folded_command = kira_open.fold(text)
    if folded_command in known_names:
        resolved = kira_open.resolve_open(text)
        if resolved:
            action = {"url": "open_url", "folder": "open_folder", "file": "open_file", "app": "open_app"}[resolved["kind"]]
            return {"action": action, "target": resolved["target"]}

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


_FR_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]
_EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
_AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
_AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
              "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

_TIME_QUESTIONS = (r"(?:what\s+time\s+is\s+it|what(?:'?s|\s+is)\s+the\s+time"
                   r"|quelle\s+heure\s+est[\s-]il|il\s+est\s+quelle\s+heure"
                   r"|donne[\s-]moi\s+l'?heure|كم\s+الساعة|كم\s+الوقت)")
_DATE_QUESTIONS = (r"(?:what(?:'?s|\s+is)\s+(?:today'?s\s+date|the\s+date(?:\s+today)?)"
                   r"|what\s+day\s+is\s+it(?:\s+today)?|what\s+day\s+are\s+we"
                   r"|quelle\s+est\s+la\s+date(?:\s+(?:d'?aujourd'?hui|du\s+jour))?"
                   r"|quel\s+jour\s+sommes[\s-]nous|on\s+est\s+quel\s+jour"
                   r"|ما\s+هو\s+تاريخ\s+اليوم|ما\s+التاريخ\s+اليوم|ما\s+هو\s+اليوم)")
_MATH_LEADINS = (r"^(?:what\s+is|what'?s|whats|how\s+much\s+is|calculate|compute"
                 r"|calcule|combien\s+font|combien\s+fait|ça\s+fait\s+combien"
                 r"|احسب|كم\s+يساوي)\s+")
_MATH_WORDS = [
    (r"\bdivided\s+by\b|\bdivisé\s+par\b|÷", "/"),
    (r"\btimes\b|\bmultiplied\s+by\b|\bfois\b|\bmultiplié\s+par\b|[x×]", "*"),
    (r"\bplus\b", "+"),
    (r"\bminus\b|\bmoins\b", "-"),
]


def _safe_math(expr):
    """Evaluate pure arithmetic (+ - * / and parentheses) safely, or None."""
    import ast
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            return None
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            return None
    try:
        return eval(compile(tree, "<math>", "eval"), {"__builtins__": {}}, {})
    except ZeroDivisionError:
        return "zero-division"
    except Exception:
        return None


def direct_answer(command, language):
    """Instant offline answers for questions with exactly one logical answer:
    time, date and arithmetic. No model, no cloud, no waiting — a tiny model
    must never get the chance to hallucinate 2 + 2."""
    import re
    from datetime import datetime
    text = str(command or "").strip().rstrip(".!?؟").strip().lower()
    if not text:
        return None
    lang = language if language in {"fr", "ar"} else "en"
    now = datetime.now()

    if re.fullmatch(_TIME_QUESTIONS, text, flags=re.IGNORECASE):
        if lang == "fr":
            return f"Il est {now:%H} h {now:%M}."
        if lang == "ar":
            return f"الساعة الآن {now:%H}:{now:%M}."
        return f"It is {now:%H}:{now:%M}."

    if re.fullmatch(_DATE_QUESTIONS, text, flags=re.IGNORECASE):
        index = now.weekday()
        if lang == "fr":
            return (f"Nous sommes le {_FR_DAYS[index]} {now.day} "
                    f"{_FR_MONTHS[now.month - 1]} {now.year}.")
        if lang == "ar":
            return (f"اليوم هو {_AR_DAYS[index]}، {now.day} "
                    f"{_AR_MONTHS[now.month - 1]} {now.year}.")
        return (f"Today is {_EN_DAYS[index]}, {now.day} "
                f"{_EN_MONTHS[now.month - 1]} {now.year}.")

    candidate = re.sub(_MATH_LEADINS, "", text, flags=re.IGNORECASE)
    candidate = candidate.rstrip("=").strip()
    for pattern, symbol in _MATH_WORDS:
        candidate = re.sub(pattern, symbol, candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"(?<=\d),(?=\d)", ".", candidate)  # 7,5 -> 7.5
    if not re.fullmatch(r"[0-9+\-*/(). ]+", candidate):
        return None
    if not (re.search(r"\d", candidate) and re.search(r"[+\-*/]", candidate)):
        return None
    result = _safe_math(candidate)
    if result == "zero-division":
        return {"fr": "On ne peut pas diviser par zéro.",
                "ar": "لا يمكن القسمة على صفر."}.get(lang, "You cannot divide by zero.")
    if result is None:
        return None
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    elif isinstance(result, float):
        result = round(result, 6)
    pretty = re.sub(r"\s+", " ", candidate).strip()
    return f"{pretty} = {result}"


def _is_personal(command):
    """True when the question is about the user's own data (name, memories,
    preferences). Those must be answered from LOCAL memory — the cloud cannot
    know the answer, and the phrasing should never leave the machine."""
    import re
    text = str(command or "").strip().lower()
    if not text:
        return False
    keywords = (r"(?:\bmy\s+name\b|\bmy\s+favou?rite\b|\bremember\b|\bmemorize\b"
                r"|\bforget\b|\bdid\s+i\s+(?:say|tell)\b|\bcall\s+me\b"
                r"|mon\s+nom|mon\s+prénom|je\s+m'appelle|appelle[\s-]moi"
                r"|souviens[\s-]toi|rappelle[\s-]toi|oublie|retiens"
                r"|ma\s+langue\s+préférée|mon\s+\S+\s+préférée?"
                r"|اسمي|ما\s+اسمي|تذكر|احفظ|انسَ?\s)")
    return re.search(keywords, text, flags=re.IGNORECASE) is not None


_NAME_STATEMENTS = (r"^(?:my\s+name\s+is|je\s+m'appelle|mon\s+nom\s+est|mon\s+prénom\s+est"
                    r"|اسمي(?:\s+هو)?)\s+(.+)$")


def _name_capture(command, language):
    """'My name is Zakaria' must save the name locally and confirm instantly —
    never wander into a model that answers with a canned greeting."""
    import re
    text = str(command or "").strip().rstrip(".!?؟").strip()
    match = re.match(_NAME_STATEMENTS, text, flags=re.IGNORECASE)
    if not match:
        return None
    name = match.group(1).strip(" .!?،؟")
    if not name or len(name.split()) > 4:
        return None
    if not re.search(r"[^\W\d_]", name, flags=re.UNICODE):
        return None
    name = " ".join(part if part.isupper() else part.capitalize()
                    for part in name.split())
    try:
        kira_memory.save_memory(category="identity", key="name",
                                value=name, confidence=1.0)
        refresh_shared_private_terms()  # the name must never reach the shared store
    except Exception:
        logging.warning("Could not persist the user's name", exc_info=True)
        return None
    if language == "fr":
        return f"Enchantée, {name}. Je retiendrai votre nom."
    if language == "ar":
        return f"تشرفت بمعرفتك يا {name}. سأتذكر اسمك."
    return f"Nice to meet you, {name}. I will remember your name."


def _diagnostic_answer(command, language):
    """'cloud status' explains, honestly and instantly, whether Gemini can
    answer — so a silent cloud is diagnosable without reading logs.
    Never shows any part of the key."""
    import re
    text = str(command or "").strip().rstrip(".!?؟").strip().lower()
    if not re.fullmatch(r"(?:cloud\s+status|status\s+cloud|statut\s+(?:du\s+)?cloud"
                        r"|[ée]tat\s+du\s+cloud|حالة\s+السحابة)", text):
        return None
    enabled = key_present = groq_key = router_key = False
    model = groq_model = "?"
    try:
        import kira_ai
        kira_ai.ensure_env_loaded()
        enabled = bool(kira_ai.cloud_enabled())
        key_present = bool(kira_ai._gemini_key())
        model = (kira_ai.active_gemini_model() if hasattr(kira_ai, "active_gemini_model")
                 else kira_ai.gemini_model())
        groq_key = bool(getattr(kira_ai, "_groq_key", lambda: "")())
        groq_model = (kira_ai.active_groq_model() if hasattr(kira_ai, "active_groq_model") else "?")
        router_key = bool(getattr(kira_ai, "_openrouter_key", lambda: "")())
    except Exception:
        pass
    provider = chat_provider()
    budget = int(chat_budget())
    ready = enabled and key_present
    groq_ready = enabled and groq_key
    if language == "fr":
        yes, no = "oui", "non"
        lines = [f"Mode de chat : {provider} · budget {budget} s.",
                 f"Cloud activé (KIRA_CLOUD_AI) : {yes if enabled else no}. "
                 f"Clé Gemini présente : {yes if key_present else no}. Modèle : {model}. "
                 f"Clé Groq présente : {yes if groq_key else no}. Modèle : {groq_model}. "
                 f"Clé OpenRouter présente : {yes if router_key else no}."]
        if ready or groq_ready or (enabled and router_key):
            names = [name for name, ok in (("Groq", groq_ready), ("Gemini", ready),
                                           ("OpenRouter", enabled and router_key)) if ok]
            lines.append(f"{' et '.join(names)} prêt(s) à répondre.")
        elif not enabled:
            lines.append("Il manque KIRA_CLOUD_AI=1 dans le fichier .env (puis redémarrez KIRA).")
        else:
            lines.append("Il manque GEMINI_API_KEY ou GROQ_API_KEY dans le fichier .env (puis redémarrez KIRA).")
        return " ".join(lines)
    yes, no = "yes", "no"
    lines = [f"Chat mode: {provider} · budget {budget} s.",
             f"Cloud enabled (KIRA_CLOUD_AI): {yes if enabled else no}. "
             f"Gemini key present: {yes if key_present else no}. Model: {model}. "
             f"Groq key present: {yes if groq_key else no}. Model: {groq_model}. "
             f"OpenRouter key present: {yes if router_key else no}."]
    if ready or groq_ready or (enabled and router_key):
        names = [name for name, ok in (("Groq", groq_ready), ("Gemini", ready),
                                       ("OpenRouter", enabled and router_key)) if ok]
        lines.append(f"{' and '.join(names)} ready to answer.")
    elif not enabled:
        lines.append("KIRA_CLOUD_AI=1 is missing from the .env file (then restart KIRA).")
    else:
        lines.append("GEMINI_API_KEY or GROQ_API_KEY is missing from the .env file (then restart KIRA).")
    return " ".join(lines)


def _cloud_test_answer(command, language):
    """'cloud test' performs ONE real Gemini round trip and reports the
    latency — or the exact (key-scrubbed) error. A present key does not
    guarantee working calls: quota, network and region failures are silent
    otherwise."""
    import re
    text = str(command or "").strip().rstrip(".!?؟").strip().lower()
    if not re.fullmatch(r"(?:cloud\s+test|test\s+(?:du\s+)?cloud|teste\s+le\s+cloud"
                        r"|اختبار\s+السحابة)", text):
        return None
    reply = None
    detail = ""
    try:
        import kira_ai
        kira_ai.ensure_env_loaded()
        cloud = _preferred_cloud()
        if not cloud:
            return _diagnostic_answer("cloud status", language)
        reply = kira_ai.chat([{"role": "user", "content": "Reply with exactly one word: pong"}],
                             provider=cloud, timeout=15)
    except Exception as exc:
        detail = str(exc)[:200]
    if reply is not None and getattr(reply, "ok", False):
        model = getattr(reply, "model", "") or "gemini"
        ms = getattr(reply, "elapsed_ms", 0)
        name = "Groq" if getattr(reply, "provider", "") == "groq" else "Gemini"
        if language == "fr":
            return f"{name} répond correctement ({model}, {ms} ms). Le chat cloud est opérationnel."
        return f"{name} answered correctly ({model}, {ms} ms). Cloud chat is operational."
    if reply is not None:
        code = getattr(reply, "error_code", "") or "error"
        detail = (getattr(reply, "error", "") or "")[:200]
        name = "Groq" if getattr(reply, "provider", "") == "groq" else "Gemini"
    else:
        code = "exception"
        name = "Gemini"
    if language == "fr":
        return (f"L'appel {name} a ÉCHOUÉ [{code}] : {detail} — vérifiez la clé, le quota "
                "(aistudio.google.com ou console.groq.com), la connexion réseau, puis réessayez « cloud test ».")
    return (f"The {name} call FAILED [{code}]: {detail} — check the key, the quota "
            "(aistudio.google.com or console.groq.com) and the network, then try 'cloud test' again.")


def chat_provider():
    """KIRA_CHAT_PROVIDER: 'auto' (local first, cloud rescue — default),
    'groq'/'fast' (fastest cloud first, ~10x Gemini's speed),
    'gemini'/'cloud' (Gemini first, local pipeline as fallback),
    'ollama'/'local' (never use the cloud for chat)."""
    import os
    try:
        import kira_ai
        kira_ai.ensure_env_loaded()  # .env works even without python-dotenv
    except Exception:
        pass
    value = os.environ.get("KIRA_CHAT_PROVIDER", "").strip().lower()
    if value in {"groq", "fast"}:
        return "groq"
    if value in {"gemini", "cloud"}:
        return "gemini"
    if value == "openrouter":
        return "openrouter"
    if value in {"ollama", "local"}:
        return "ollama"
    return "auto"


def _role_cloud(language):
    """(provider, model) chosen by the KIRA_MODEL_* role variables, or None.
    Arabic questions try the 'arabic' role first (e.g. Gemini for quality),
    everything else the 'chat' role. Local-only roles are not cloud
    candidates — KIRA_CHAT_PROVIDER=ollama already keeps chat local."""
    try:
        import kira_ai
    except Exception:
        return None
    route = getattr(kira_ai, "role_route", None)
    if route is None:
        return None
    roles = ("arabic", "chat") if language == "ar" else ("chat",)
    for role in roles:
        try:
            provider, model = route(role)
        except Exception:
            continue
        if provider and provider != "ollama":
            return provider, model
    return None


def _preferred_cloud():
    """Which cloud provider should answer, or None. Groq wins when ready
    (LPU speed is the point) unless the user pinned Gemini; each falls
    back to the other so one missing key never silences the cloud."""
    try:
        import kira_ai
    except Exception:
        return None
    ready = getattr(kira_ai, "provider_ready", None)
    if ready is None:  # older kira_ai: Gemini was the only cloud provider
        try:
            return "gemini" if kira_ai.cloud_ready() else None
        except Exception:
            return None
    pinned = chat_provider()
    if pinned == "gemini":
        order = ("gemini", "groq", "openrouter")
    elif pinned == "openrouter":
        order = ("openrouter", "groq", "gemini")
    else:
        order = ("groq", "gemini", "openrouter")
    for name in order:
        try:
            if ready(name):
                return name
        except Exception:
            continue
    return None


def _local_chat_answer(command, language):
    """The local pipeline answer, or None instead of the 'model offline'
    apology — a rescue stage must fire, not a dead-end error text."""
    answer = _ask_chat_response(command, language)
    text = str(answer or "").strip()
    if not text:
        return None
    offline = {kira_commands.message("model_offline", language),
               kira_commands.message("model_offline", "en")}
    return None if text in offline else answer


def ask_chat(command: str, language=None):
    """The caller's selected language wins over history and persona examples.

    Every question is answered within CHAT_ANSWER_BUDGET (5 s): local model
    first, quick web lookup if it is too slow, honest message if neither
    made it in time."""
    global _LAST_REPLY_LANGUAGE
    from kira_commands import try_web_learning
    learning_reply = try_web_learning(command)
    if learning_reply is not None:
        return learning_reply
    language = kira_language.normalize_language(language) or detect_language(command)
    if language == "auto":
        language = detect_language(command)
    _LAST_REPLY_LANGUAGE = language
    instant = (direct_answer(command, language) or _name_capture(command, language)
               or _diagnostic_answer(command, language) or _cloud_test_answer(command, language))
    if instant:
        _CHAT_HISTORY.append({"role": "user", "content": command})
        _CHAT_HISTORY.append({"role": "assistant", "content": instant})
        try:
            kira_memory.save_message(_SESSION_ID, "user", command)
            kira_memory.save_message(_SESSION_ID, "assistant", instant)
        except Exception:
            pass
        return instant
    budget = chat_budget()
    provider = chat_provider()
    personal = _is_personal(command)
    if provider in {"gemini", "groq", "openrouter"} and not personal:
        direct = _run_bounded(lambda: _cloud_chat_answer(command, language),
                              max(2.0, budget - 1.0))
        if direct:
            _CHAT_HISTORY.append({"role": "user", "content": command})
            _CHAT_HISTORY.append({"role": "assistant", "content": direct})
            try:
                kira_memory.save_message(_SESSION_ID, "user", command)
                kira_memory.save_message(_SESSION_ID, "assistant", direct)
            except Exception:
                pass
            return direct
    answer, source = chat_answer_with_web(command, language, _local_chat_answer,
                                          _web_lookup, _synthesize_web_answer,
                                          budget=budget,
                                          ask_cloud=None if provider == "ollama" or personal else _cloud_chat_answer)
    if not str(answer or "").strip():
        seconds = int(budget)
        answer = {
            "fr": (f"Je n'ai pas eu de réponse en {seconds} secondes : le modèle local est lent "
                   "et le web n'a rien donné. Reformule ou réessaie."),
            "ar": (f"لم أحصل على رد خلال {seconds} ثوانٍ: النموذج المحلي بطيء والويب لم يعط شيئًا. "
                   "أعد الصياغة أو حاول مرة أخرى."),
            "en": (f"I did not get an answer within {seconds} seconds: the local model is slow "
                   "and the web gave nothing. Rephrase or try again."),
        }.get(language) or (f"I did not get an answer within {seconds} seconds: the local model is slow "
                            "and the web gave nothing. Rephrase or try again.")
        return answer
    if source in {"web", "cloud"}:
        return answer  # already readable/in-language; extra translation would waste the budget
    return kira_language.ensure_reply_language(answer, language, call_ollama)


CLOUD_CHAT_PROMPTS = {
    "fr": "Tu es KIRA, l'assistante de l'utilisateur. Réponds en français, en 2 à 4 phrases claires et directes.",
    "ar": "أنت KIRA، مساعدة المستخدم. أجب بالعربية في جملتين إلى أربع جمل واضحة ومباشرة.",
    "en": "You are KIRA, the user's assistant. Answer in English, in 2 to 4 clear, direct sentences.",
}


def _cloud_chat_answer(command, language):
    """Cloud chat fallback, only when the user opted in (KIRA_CLOUD_AI=1).

    Privacy: ONLY the current question is sent — never local chat history,
    memories, code or screenshots. Returns text or None (never raises).
    """
    try:
        import kira_ai
        # Candidates in priority order: the specialist role for this
        # language, then the preferred cloud, then any other ready cloud.
        candidates = []
        role = _role_cloud(language)
        if role:
            candidates.append(role)
        preferred = _preferred_cloud()
        if preferred:
            candidates.append((preferred, ""))
        ready = getattr(kira_ai, "provider_ready", None)
        if ready is not None:
            for name in ("groq", "gemini", "openrouter"):
                try:
                    if ready(name):
                        candidates.append((name, ""))
                except Exception:
                    continue
        seen, order = set(), []
        for provider, model in candidates:
            if provider and provider not in seen:
                seen.add(provider)
                order.append((provider, model))
        if not order:
            return None
        system = CLOUD_CHAT_PROMPTS.get(language) or CLOUD_CHAT_PROMPTS["en"]
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": str(command)}]
        # Two attempts max keeps latency bounded: quota exhausted or outage
        # on the first choice never silences a ready second cloud.
        for provider, model in order[:2]:
            try:
                reply = kira_ai.chat(messages, provider=provider, model=model, timeout=8)
            except Exception:
                continue
            if reply.ok and reply.text.strip():
                return reply.text
        return None
    except Exception:
        return None


def _ask_chat_response(command: str, language: str):
    global _CHAT_HISTORY

    command = str(command or "").strip()

    if not command:
        return ""

    from kira_commands import try_web_learning
    learning_reply = try_web_learning(command)
    if learning_reply is not None:
        return learning_reply

    history_limit = max(
        4,
        int(CONFIG.get("chat_history_limit", 16)),
    )

    # Language is resolved once by the caller, not overwritten by English history.
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

        # Newly stored personal facts must never leak to the shared store.
        refresh_shared_private_terms()

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

        # Shared (non-personal) knowledge from Supabase may help answer this
        # question. Only shared web research and project knowledge are read;
        # nothing personal is ever sent to the shared store.
        shared_context = shared_context_for_chat(command)

        if shared_context:
            messages.append(
                {
                    "role": "system",
                    "content": shared_context,
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
            raise ValueError("empty model response")
        answer = kira_language.ensure_reply_language(answer, language, call_ollama)

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

    except kira_language.ReplyLanguageError:
        if _CHAT_HISTORY and _CHAT_HISTORY[-1].get("role") == "user":
            _CHAT_HISTORY.pop()
        raise
    except Exception as exc:
        logging.warning(
            "Chat response failed: %s",
            exc,
        )

        if _CHAT_HISTORY:
            _CHAT_HISTORY.pop()

        return kira_commands.message("model_offline", language) or kira_commands.message("model_offline", "en")

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
    """Open an app via the shared resolver (aliases, Start Menu, web fallback)."""
    return kira_open.open_app(target)


def open_url(target: str, browser=None):
    """Open a page: requested browser first, then the remembered default."""
    remembered = str(USER_MEMORY.get("default_browser", "") or "").strip() or None
    return kira_open.open_url(target, browser=browser or remembered)


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


def search_web(query: str, browser=None):
    q = quote_plus((query or "").strip())
    if not q:
        return False
    return kira_open.open_url(f"https://www.google.com/search?q={q}", browser=browser)


def shared_knowledge_status() -> dict:
    """Return the shared knowledge configuration status (empty when absent)."""
    if not SHARED_KNOWLEDGE_AVAILABLE or kira_shared_memory is None:
        return {"enabled": False, "configured": False, "installed": False}
    try:
        return kira_shared_memory.status()
    except Exception:
        return {"enabled": False, "configured": False, "installed": False}


def search_shared_knowledge(query: str):
    """
    Search the shared Supabase knowledge base (non-personal knowledge only)
    and speak the results.

    Only READS shared knowledge — personal data such as conversations, names,
    preferences, tasks and private notes never leaves local memory.
    """
    query = str(query or "").strip().rstrip(".?!")

    if not query:
        speak(personalize_address("What should I look up in shared knowledge, sir?"))
        return False

    if not SHARED_KNOWLEDGE_AVAILABLE or kira_shared_memory is None:
        speak(
            personalize_address(
                "Shared knowledge is unavailable sir. Install the supabase "
                "package and add SUPABASE_URL and SUPABASE_ANON_KEY to .env."
            )
        )
        return True

    if not kira_shared_memory.is_enabled():
        speak(
            personalize_address(
                "Shared knowledge is not configured sir. Add SUPABASE_URL and "
                "SUPABASE_ANON_KEY to the .env file, then try again."
            )
        )
        return True

    results = kira_shared_memory.search_shared_knowledge(query, limit=3)

    if not results:
        speak(
            personalize_address(
                f"I found nothing in shared knowledge about {query}, sir."
            )
        )
        return True

    count = len(results)
    speak(
        personalize_address(
            f"I found {count} shared knowledge "
            f"{'entry' if count == 1 else 'entries'} about {query}, sir."
        )
    )

    for index, item in enumerate(results, start=1):
        topic = str(item.get("topic", "")).replace("_", " ").strip() or "entry"
        content = str(item.get("content", "")).strip()[:300]
        speak(f"Number {index}. {topic}. {content}")

    return True


def share_project_knowledge(topic: str, content: str, kind: str = "project_knowledge"):
    """
    Publish NON-personal project knowledge to the shared knowledge base.

    The shared memory module refuses payloads that look personal (names,
    preferences, credentials, ...) so private data stays in kira_memory.db.
    """
    topic = str(topic or "").strip()
    content = str(content or "").strip()

    if not topic or not content:
        speak(
            personalize_address(
                "Tell me the project knowledge as 'topic: detail', sir, "
                "and I will share it."
            )
        )
        return False

    if not SHARED_KNOWLEDGE_AVAILABLE or kira_shared_memory is None:
        speak(
            personalize_address(
                "The shared knowledge base is unavailable sir, so I kept that "
                "local. Install the supabase package and add your Supabase "
                "URL and anon key to .env to share it."
            )
        )
        return True

    if not kira_shared_memory.is_enabled():
        speak(
            personalize_address(
                "Shared knowledge is not configured sir, so I kept that in "
                "local memory. Add SUPABASE_URL and SUPABASE_ANON_KEY to .env "
                "to share it."
            )
        )
        return True

    shared = kira_shared_memory.save_shared_knowledge(
        kind=kind or "project_knowledge",
        topic=topic,
        content=content,
        title=topic,
        tags=["project"],
    )

    if shared:
        speak(
            personalize_address(
                f"I have shared that project knowledge about {topic} with the "
                "shared knowledge base, sir."
            )
        )
        return True

    speak(
        personalize_address(
            "I did not share that sir — it looks personal or private, so I "
            "kept it in local memory."
        )
    )
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


def resolve_open_matches(action_data):
    """Existing candidate paths for an open request (empty list if none).

    Used to ask the user which one when several files or folders share the
    same name, and to open every one of them on an "all" request.
    """
    if not isinstance(action_data, dict):
        return []
    action = str(action_data.get("action", "")).strip().lower()
    target = str(action_data.get("target", "")).strip()
    parent = action_data.get("parent")
    try:
        if action == "open_file":
            if kira_open.fold(target) in kira_open.FOLDER_ALIASES:
                return None  # a known place: nothing to disambiguate
            return kira_open.file_matches(target, parent=parent, limit=20)
        if action == "open_folder":
            if kira_open.fold(target) in kira_open.FOLDER_ALIASES or kira_open.parse_drive(target):
                return None
            full_list = bool(action_data.get("any_kind") or action_data.get("all"))
            if action_data.get("any_kind"):
                return kira_open.mixed_matches(target, parent=parent, limit=20)
            return kira_open.folder_matches(target, parent=parent, limit=20,
                                            direct_only=not full_list)
    except Exception:
        logging.exception("resolve_open_matches failed")
    return []


def open_folder(target: str, parent=None):
    """Open a folder, optionally inside a parent location or drive."""
    return kira_open.open_folder(target, parent=parent)


def open_file(target: str, parent=None):
    """Open a document: direct path, parent location, common folders, drives."""
    return kira_open.open_file(target, parent=parent)


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
        "search our shared knowledge base, "
        "control volume and media, manage windows, read the clipboard, "
        "report system status, analyze your screen, locate things on screen, "
        "and answer questions using my local AI, sir. "
        "Personal memories stay on this machine; only shared web research and "
        "project knowledge go to the shared knowledge base."
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
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as config_file:
            json.dump(CONFIG, config_file, indent=2, ensure_ascii=False)
    except OSError:
        logging.warning("Could not save preferred address")
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

            except Exception as exc:
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
        return open_url(str(action_data.get("target", "")), browser=action_data.get("browser"))

    if action == "type":
        return type_text(str(action_data.get("text", "")))

    if action == "press":
        return press_key(str(action_data.get("target", "")))

    if action == "search":
        return search_web(str(action_data.get("query", "")), browser=action_data.get("browser"))

    if action == "search_shared_knowledge":
        return search_shared_knowledge(str(action_data.get("query", "")))

    if action == "share_project_knowledge":
        return share_project_knowledge(
            str(action_data.get("topic", "")),
            str(action_data.get("content", "")),
            str(action_data.get("kind", "project_knowledge")),
        )

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

    if action in {"open_folder", "open_file"} and action_data.get("all"):
        target = str(action_data.get("target", "")).strip()
        parent = action_data.get("parent")
        if action == "open_folder" and kira_open.fold(target) in kira_open.FOLDER_ALIASES and not parent:
            return bool(open_folder(target))
        matches = action_data.get("candidates")
        if not (isinstance(matches, list) and matches
                and all(isinstance(path, str) for path in matches)):
            matches = resolve_open_matches(action_data)
        opened = 0
        for path in matches[:20]:
            if kira_open.open_path(path):
                opened += 1
        return opened

    if action == "open_folder":
        target = str(action_data.get("target", "")).strip()
        if action_data.get("any_kind") and target and os.path.exists(target):
            # Mixed search: the picked candidate may be a file or a folder.
            return kira_open.open_path(target)
        return open_folder(target, parent=action_data.get("parent"))

    if action == "open_file":
        return open_file(str(action_data.get("target", "")), parent=action_data.get("parent"))

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

    # ── Task management actions ──
    if action == "add_reminder":
        title = str(action_data.get("title", "")).strip()
        due_at = str(action_data.get("due_at", "")).strip()
        if not title:
            return False
        task_id = kira_tasks.add_task(
            title=title,
            task_type="reminder",
            due_at=due_at,
        )
        lang = "en"
        if due_at:
            speak(build_reply(lang, "reminder_set", title))
        else:
            speak(f"Reminder added: {title}")
        return True

    if action == "add_todo":
        title = str(action_data.get("title", "")).strip()
        if not title:
            return False
        kira_tasks.add_task(title=title, task_type="todo")
        speak(f"Todo added: {title}")
        return True

    if action == "list_tasks":
        tasks = kira_tasks.list_tasks(completed=False, limit=10)
        if not tasks:
            speak("You have no pending tasks.")
        else:
            count = len(tasks)
            speak(f"You have {count} pending task{'s' if count != 1 else ''}.")
            for i, task in enumerate(tasks[:5], 1):
                speak(f"{i}. {task['title']}")
        return True

    if action == "clear_completed_tasks":
        count = kira_tasks.clear_completed()
        if count > 0:
            speak(f"Cleared {count} completed task{'s' if count != 1 else ''}.")
        else:
            speak("No completed tasks to clear.")
        return True

    # ── Plugin action handlers ──
    plugin_handler = kira_plugins.get_action_handler(action)
    if plugin_handler:
        try:
            return plugin_handler(action_data)
        except Exception as exc:
            logging.error("Plugin action %s failed: %s", action, exc)
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

    if action == "open_folder":
        target = str(action_data.get("target", "folder")).strip() or "folder"
        return f"open the {target} folder"

    if action == "open_file":
        target = str(action_data.get("target", "file")).strip() or "file"
        return f"open the file {target}"

    if action == "type":
        text = str(action_data.get("text", "text")).strip() or "text"
        return f"type {text}"

    if action == "press":
        target = str(action_data.get("target", "key")).strip() or "key"
        return f"press the {target} key"

    if action == "search":
        query = str(action_data.get("query", "search")).strip() or "search"
        return f"search the web for {query}"

    if action == "search_shared_knowledge":
        query = str(action_data.get("query", "")).strip() or "the topic"
        return f"search the shared knowledge base for {query}"

    if action == "share_project_knowledge":
        topic = str(action_data.get("topic", "")).strip() or "the project"
        return f"share project knowledge about {topic} with the shared knowledge base"

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


def should_process_command(command: str) -> bool:
    text = (command or "").strip()
    if not text:
        return False
    lower = text.lower()

    if is_wake_phrase(lower):
        return True

    if any(
        token in lower
        for token in [
            "open ",
            "play ",
            "search ",
            "type ",
            "press ",
            "close window",
            "minimize",
            "maximize",
            "screenshot",
            "switch app",
            "open folder",
            "close this",
            "take screenshot",
            "switch window",
            "quit",
            "exit",
            "goodbye",
        ]
    ):
        return True

    # In unified mode, process all commands; otherwise require wake word
    if not CONFIG.get("require_wake_word", False):
        return True

    return False


def _on_task_notification(task_id: str, title: str, task_type: str):
    """Callback when a reminder/timer fires."""
    if task_type == "reminder":
        speak(f"Reminder: {title}")
    else:
        speak(f"Task completed: {title}")


def startup_sequence():
    # Restore any pending timers from previous session
    kira_tasks.restore_timers()
    # Register task notification callback
    kira_tasks.register_callback(_on_task_notification)
    # Load plugins
    kira_plugins.load_all_plugins()

    speak(personalize_address(" Hello sir."))
    speak(personalize_address("Listening for your command sir."))


def main():
    global _CONVERSATION_MODE
    print("=" * 60)
    print("KIRA VOICE AGENT")
    print("Local Windows assistant with voice controls")
    print("Type 'exit' to quit or say 'KIRA exit'")
    print("=" * 60)

    try:
        startup_sequence()

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

            lower = cleaned.lower()

            if lower in {"exit", "quit", "goodbye", "bye"}:
                speak(personalize_address("Goodbye sir."))
                break

            from kira_commands import try_web_learning
            learning_reply = try_web_learning(cleaned)
            if learning_reply is not None:
                speak(learning_reply)
                continue

            result = parse_simple_command(cleaned)
            if result is None and is_chat_question(cleaned):
                speak(ask_chat(cleaned))
                continue
            if result is None:
                result = ask_agent(cleaned)
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

            if action in {"search", "mouse_move", "click", "lock_pc"}:
                target_desc = describe_action(result)
                allowed = confirm_action(action.replace("_", " "), target_desc)
                if not allowed:
                    lang = detect_language(cleaned)
                    speak(build_reply(lang, "none"))
                    continue

            lang = detect_language(cleaned)
            success = execute_action(result)
            if success:
                action_name = str(action).lower()
                if action_name in {
                    "read_clipboard",
                    "system_info",
                    "help",
                    "time",
                    "date",
                    # These handlers speak their own results.
                    "search_shared_knowledge",
                    "share_project_knowledge",
                }:
                    continue
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
                elif action == "open_file":
                    target_text = str((result or {}).get("target", "file"))

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
            else:
                lang = detect_language(cleaned)
                speak(build_reply(lang, "none"))
    except KeyboardInterrupt:
        print("\nKIRA: Stopped by user.")


if __name__ == "__main__":
    main()
