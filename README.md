# KIRA — Local AI Computer Agent

**KIRA** is a fully local, voice-controlled desktop assistant for Windows.
Talk to it in **English, French, or Arabic** and it opens apps, searches the
web, types, presses keys, manages windows and media, reads your clipboard,
reports system status — and can even *see your screen*: it locates a visible
UI element with a vision model, clicks it, and verifies the result.

Everything runs on your machine. No cloud APIs, no API keys, no telemetry.

```
 you ──► mic ──► Vosk/Google STT ──► rule-based parser ─┬─► action done ✓
                        │                               │
                        │                         no match? ▼
                        │                     Ollama LLM (qwen3) ──► action done ✓
                        │                               │
                        └────────── chat question ──────►
                                        SQLite memory ◄──┤
```

## Highlights

- **Fully local** — chat via [Ollama](https://ollama.com) (`qwen3:0.6b` by
  default), vision via `qwen3-vl:2b`, offline speech recognition via Vosk,
  offline text-to-speech via Windows SAPI (`pyttsx3` fallback).
- **Trilingual** — commands and conversation in English, French and Arabic.
- **Layered command routing** — a fast deterministic parser handles ~100
  built-in phrases; anything ambiguous falls to the local LLM, and questions
  fall to the chat personality.
- **Screen vision with verification** — "find the save button and click it":
  KIRA screenshots, asks the vision model for coordinates, clicks at ≥70%
  confidence, then compares before/after screenshots to confirm it worked.
- **Persistent memory** — remembers your name, preferences and past messages
  in a local SQLite database; deterministic recall for personal facts.
- **Built-in calculator** — "what is 15% of 200", "calculate 2 to the power
  of 10", in three languages, evaluated through a safe AST whitelist.
- **Voice reminders** — "remind me in 10 minutes to call mom" sets a real
  timer that speaks back when it fires (English, French and Arabic).
- **Configurable everything** — your own app aliases, websites and
  confirmation rules live in `kira_config.json`, not in code.
- **Graphic UI** — dark `customtkinter` interface with a state machine
  (READY / LISTENING / THINKING / EXECUTING / SPEAKING), animated core,
  chat panel, quick commands and typed input.
- **Safe by default** — sensitive actions (web search, mouse clicks, locking
  the PC) ask for voice confirmation; destructive steps fail loudly.

## Requirements

| Requirement | Notes |
|---|---|
| Windows 10/11 | Linux/macOS can run the parser/tests, but the full agent targets Windows |
| Python 3.10+ | 64-bit |
| [Ollama](https://ollama.com/download) | must be running (`ollama serve`) |
| Microphone + speakers | for voice mode; the UI also accepts typed commands |

## Quick start

```powershell
git clone https://github.com/zak001-afk/kira.git
cd kira
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Pull the LLM/vision models and (optionally) an offline speech model:
python scripts/setup_models.py

# Run KIRA:
python main_window.py
```

`scripts/setup_models.py` checks that Ollama is up (starts it if needed),
pulls the models referenced by `kira_config.json`, and can download a small
Vosk model + point `offline_model_path` at it.

## Voice commands

Wake word **"kira"** is optional by default (`require_wake_word`). A separator
after the wake word is fine: *"kira, open chrome"*, *"kira: open chrome"*.

| Say (EN) | Say (FR) | Say (AR) | Action |
|---|---|---|---|
| open chrome | ouvrir chrome | افتح كروم | launch an app (aliases for notepad, calc, paint, vscode…) |
| open youtube | — | — | open a website |
| open folder projects | ouvrir le dossier … | افتح مجلد … | open a folder |
| search weather in Tunis | recherche la météo | ابحث عن الطقس | web search *(asks confirmation)* |
| type hello world | écris bonjour | اكتب مرحبا | type text into the focused window |
| press enter | appuie entrée | اضغط … | press a key |
| open chrome and search x | — | — | chained sequence |
| close window / minimize / maximize | ferme la fenêtre … | اغلق النافذة … | window management |
| volume up / down / mute | monte le volume … | ارفع الصوت … | volume & media keys |
| play pause / next track | lecture | تشغيل | media control |
| lock pc | verrouille | قفل الكمبيوتر | lock workstation *(asks confirmation)* |
| copy / paste / read clipboard | copier / coller | نسخ / لصق | clipboard |
| screenshot | capture d'écran | لقطة شاشة | save `kira_screenshot.png` |
| system info | état du système | معلومات النظام | CPU / RAM / battery report |
| time / date | quelle heure est-il | كم الساعة | clock |
| work mode | — | — | run your configured shortcut |
| call me commander | appelle-moi … | نادني … | change how KIRA addresses you |
| remember my browser is firefox | — | — | persist a preference |
| what is my name | — | — | deterministic memory recall |
| forget my name | — | — | delete a stored fact |
| what's on my screen | qu'est-ce qu'il y a sur mon écran | ماذا يوجد على الشاشة | vision: describe the screen |
| find the save button and click it | trouve le bouton et clique | — | vision: locate → click → verify |
| conversation mode / stop conversation | mode conversation | وضع المحادثة | toggle chat mode |
| calculate 2 to the power of 10 | calcule dix fois trois | كم يساوي ١٢ ضرب ٢ | safe local arithmetic (words & % work) |
| open github / gmail / netflix | ouvrir netflix | — | known websites (extendable in config) |
| remind me in 5 minutes to call mom | rappelle-moi dans 2 heures de … | ذكرني بعد 10 دقائق … | set a spoken reminder |
| list reminders / cancel reminders | mes rappels / annule les rappels | تذكيراتي / الغ التذكيرات | manage reminders |
| clear chat | efface la conversation | محادثة جديدة | new conversation |
| exit | au revoir | خروج | quit |

Anything the parser doesn't recognize is sent to the local LLM, which maps it
to one of the allowed actions — or, if it reads as a question, to the
conversational chat mode with your stored memories as context.

## Configuration

`kira_config.json` (all keys optional — defaults are merged at load):

```jsonc
{
  "model": "qwen3:0.6b",          // chat/command LLM (Ollama tag)
  "vision_model": "qwen3-vl:2b",  // vision LLM for screen understanding
  "vision_click_confidence": 0.7, // minimum confidence before a visual click
  "require_wake_word": false,     // only react to "kira …" when true
  "conversation_mode": false,     // start in chat mode
  "chat_history_limit": 12,       // messages kept in the rolling context
  "preferred_address": "sir",     // sir, commander, captain, madam… (see ADDRESS_OPTIONS)
  "offline_model_path": "",       // absolute path to a Vosk model folder
  "app_aliases": {},              // your apps:  "notion": "notion.exe"
  "websites": {},                 // your sites: "my blog": "https://…"
  "require_confirmation": [       // actions that ask before executing
    "search", "mouse_move", "click", "lock_pc"
  ],
  "shortcuts": {                  // voice-triggered sequences
    "work mode": [
      {"action": "open_app", "target": "vscode"},
      {"action": "open_app", "target": "chrome"}
    ]
  }
}
```

Notes:

- `require_wake_word: true` is now actually enforced — only phrases
  containing "kira" are handled (conversation mode keeps the channel open).
- Set `require_confirmation: []` to disable confirmation prompts entirely.

Environment variables `KIRA_MODEL` / `KIRA_VISION_MODEL` override the model
names (see `.env.example`).

## Persistent memory

KIRA keeps two kinds of memory in `kira_memory.db` (SQLite, local only,
git-ignored):

- **Structured facts** — explicit statements like *"my name is Zakaria"*
  become `(category, key, value)` rows with a confidence score. Recalls such
  as *"what is my name"* are answered **deterministically** — never invented
  by the small LLM. *"forget my name"* deletes the row.
- **Conversation log** — recent messages feed the rolling chat context
  (with per-session ids) so follow-ups work across restarts.

## Screen vision

The vision pipeline never clicks blind:

1. **Locate** — the vision model receives a screenshot and must return JSON
   `{found, x, y, label, confidence}` in absolute pixels; out-of-screen or
   low-confidence results are rejected.
2. **Click** — only when `confidence ≥ vision_click_confidence` (default 0.70).
3. **Verify** — before/after screenshots are compared by the model; if the
   expected change isn't visible, KIRA tells you rather than claiming success.

Temporary screenshots live in the system temp dir and are deleted after use.
Plain *"click"* and mouse moves always ask for voice confirmation.

## Project structure

```
kira/
├── main_window.py        # customtkinter UI (orb, state machine, chat panel)
├── kira_voice_agent.py   # backend: STT, parser, LLM routing, actions, vision, TTS
├── kira_calculator.py    # safe AST-whitelisted arithmetic (EN/FR/AR)
├── kira_reminders.py     # in-process spoken reminders with daemon timers
├── kira_memory.py        # SQLite persistence (facts + conversations)
├── kira_config.json      # user configuration (see above)
├── dev.py                # watch-and-restart development mode
├── scripts/
│   └── setup_models.py   # one-time model installer (Ollama + Vosk)
├── assets/               # icons
├── tests/                # pytest suite (runs anywhere — hardware is stubbed)
├── KIRA.spec             # PyInstaller spec (single source of truth for builds)
└── build_kira.bat        # release build → dist/ → Desktop + shortcut
```

## Development

```powershell
dev_mode.bat        # auto-restarts KIRA whenever a source file changes

pip install -r requirements-dev.txt
pytest              # 169 unit tests — no mic, display or Ollama needed
ruff check .        # lint
python -m compileall dev.py kira_memory.py kira_voice_agent.py main_window.py scripts tests
```

Tests stub the hardware-facing modules (`pyautogui`, audio, Ollama, …) in
`tests/conftest.py`, so they pass on any OS and in CI (GitHub Actions runs the
suite on Ubuntu + Windows, plus a Windows dependency-resolution check).

## Building the EXE

```powershell
build_kira.bat
```

This runs PyInstaller with `KIRA.spec` (which bundles `customtkinter`, icons
and the config), then copies `dist\KIRA` to your Desktop and creates a
shortcut. You do **not** need to rebuild while developing — use dev mode.

## Troubleshooting

- **"I cannot reach Ollama right now"** — install Ollama, run `ollama serve`,
  then `python scripts/setup_models.py`. Chat and vision features need it;
  built-in commands do not.
- **No headset microphone found** — KIRA prefers a physical mic (Realtek
  headset) and skips speakers/hands-free outputs; check
  `PREFERRED_MICROPHONE` at the top of `kira_voice_agent.py`.
- **Robotic or wrong voice** — speech uses the Windows SAPI voice
  *Microsoft Zira Desktop* when present, then falls back to `pyttsx3`.
- **Offline recognition does nothing** — set `offline_model_path` in
  `kira_config.json` to a valid Vosk model directory (setup script can do it).
- **Logs** — `kira.log` in the project folder records commands, model I/O and
  vision failures.

## License

MIT — see [LICENSE](LICENSE).
