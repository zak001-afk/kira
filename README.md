# KIRA — Local AI Computer Agent

**KIRA** is a sophisticated local AI assistant with voice control, computer automation, persistent memory, task management, and an extensible plugin system. Built for Windows with a cinematic gold **AI Command Center** interface (in French).

## ✨ Features

### Core Capabilities
- **AI Command Center UI** — Gold/black HUD with holographic AI avatar, live system gauges (CPU / RAM / Disk / Network), agents panel, recent tasks and a 9-view navigation dock
- **Voice Control** — Natural language voice commands with wake word detection (all voices are **female**: Denise, Éloïse, Vivienne)
- **Local Kokoro Voice (TTS)** — Free, offline neural voice (no ElevenLabs, no paid API, no key): KIRA speaks through a local Kokoro engine with a modular provider system (Edge neural voices as automatic fallback)
- **Computer Control** — Open apps, control windows, manage files, automate tasks
- **Persistent Memory** — SQLite-based memory system that remembers across sessions
- **Multi-Language** — Supports English, French, and Arabic
- **Vision System** — Screen analysis and visual element location using Ollama vision models
- **Task Management** — Timers, reminders, notes, and to-do lists
- **Plugin System** — Extensible architecture for adding new capabilities
- **Web API** — REST API for web UI integration
- **Resource Efficient** — Optimized animations and lazy loading for low overhead

### Computer Control Actions
- Open applications and websites
- Type text and press keys
- Web search
- Mouse control (move, click)
- Volume and media controls
- Window management (close, minimize, maximize, switch)
- Clipboard operations
- Screenshot capture
- System information
- File management (create, read, search, delete)

### Task Management
- **Reminders** — "Remind me to call mom in 5 minutes"
- **Timers** — "Set a timer for 30 minutes"
- **To-Do Lists** — "Add todo buy groceries"
- **Notes** — Persistent notes storage
- Auto-scheduling and notifications

### Plugin Architecture
Extend KIRA with custom plugins:
```python
# plugins/my_plugin.py
PLUGIN_NAME = "My Plugin"
PLUGIN_VERSION = "1.0"

def my_action(action_data):
    # Your custom logic here
    return True

def register(kira_plugins_module):
    kira_plugins_module.register_action("my_action", my_action)
```

## 🚀 Installation

### Requirements
- Windows 10/11
- Python 3.8+
- Ollama (for AI capabilities)

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd kira
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

> **Using (or repairing) the virtual environment**
>
> `.venv/pyvenv.cfg` records the absolute path of the Python that created it,
> so a checkout copied from another machine can arrive with a venv that will
> not start (`did not find executable at ...`). Run this with any working
> Python from PATH:
>
> ```bash
> python scripts/setup_venv.py            # or double-click setup_venv.bat
> ```
>
> It repoints the environment at the local interpreter when that is safe
> (same Python major.minor, so the installed binary extensions still match),
> otherwise rebuilds it, then installs `requirements.txt` and
> `requirements-dev.txt`. `--rebuild` forces a clean environment, `--no-install`
> skips the pip step.

3. **Install Ollama**
Download from https://ollama.ai and install the required models:
```bash
ollama pull qwen3:0.6b
ollama pull qwen3-vl:2b
```

4. **Run KIRA**
```bash
python main_window.py  # Native desktop app (recommended)
python launch_web.py     # Browser mode
```

### Development Mode
For hot-reload during development:
```bash
python dev.py
```

`dev.py` polls the project every 0.8s and restarts `main_window.py` whenever a
watched file (`.py`, `.json`, `.js`, `.css`, `.html`, images, fonts) changes, so
code edits show up without relaunching. It ignores `.venv`, `__pycache__`,
`build`, `dist` and other generated directories. Closing the KIRA window now
stops dev mode instead of resurrecting the app; run `python dev.py
--auto-restart` to restore the old auto-restart behavior (with a guard:
three fast startup crashes in a row stop the watcher).

### Desktop shortcut
Double-clicking **KIRA** on the desktop starts the app itself — one instance,
no watcher. The shortcut points at `launch_kira.bat`, which:

- launches `main_window.py` through `.venv\Scripts\python.exe` (falling back
  to PATH only if the venv is missing) — it never uses a stale
  system-registered interpreter, so a broken `pyvenv.cfg` cannot produce a
  `did not find executable at ...` failure;
- prints a clear error pointing at `setup_venv.bat` if no interpreter works.

### Single instance
Every launcher (`main_window.py`, `dev.py`, `launch_desktop.py`) takes the
same single-instance lock (`single_instance.py`). Starting KIRA while it is
already running prints who holds the lock and exits (code 3) instead of
opening a second window that fights over ports 8765/8766. A lock left by a
crashed run is detected and cleaned at the next launch; `--force` overrides
it deliberately. The lock lives in `kira.lock` at the project root
(`%APPDATA%\KIRA\kira.lock` for a frozen build).

### Build Executable
```bash
build_kira.bat
```

## 📖 Usage

### Voice Commands

**Basic Commands:**
- "Open Chrome"
- "Search for weather today"
- "Type hello world"
- "Press enter"
- "Take screenshot"
- "Volume up/down/mute"
- "Lock computer"

**Task Management:**
- "Remind me to call mom in 5 minutes"
- "Set a timer for 30 minutes"
- "Add todo buy groceries"
- "List tasks"
- "Clear completed tasks"

**Memory (always local):**
- "Remember that my favorite color is blue"
- "Call me commander"
- "My name is Zakaria"

**Shared Knowledge (Supabase — non-personal only):**
- "Search shared knowledge for python decorators"
- "What do we know about row level security"
- "Remember project knowledge: the HUD lives in kira_theme.py"
- "Share knowledge: the web UI is served by main_window.py"

**System:**
- "System info"
- "What time is it"
- "What's today's date"
- "Help"

### Text Input
Use the command bar at the bottom of the interface to type commands instead of using voice.

### Web Interface
With `main_window.py` running, the interface is served at `http://127.0.0.1:8766`;
the API uses port 8765.

### Visage naturel de KIRA
Le visage utilise un **portrait fictif photoréaliste généré par IA**, avec un
teint, des yeux et des lèvres naturels ; seuls le décor et les anneaux restent
verts. Ce n'est ni une personne réelle ni une caméra en direct. Les lèvres
animées reprennent les couleurs du même portrait et suivent le moteur vocal
existant. Le visage est composé après les effets lumineux du décor pour ne
pas devenir vert ou surexposé.

Dans **Paramètres → Luminosité de l'avatar**, la valeur initiale est **90 %**
(**100 %** restitue les couleurs de l'image). Une préférence déjà enregistrée,
même à 45 %, reste prioritaire. Après mise à jour, relancez KIRA ; le terminal
indique **AI COMMAND CENTER MED / NATURAL AVATAR 01**. Copiez tout le dossier
`ui/`, pas uniquement `app.js` : le nouveau portrait et `avatar.mjs` sont requis.

### Speech-reactive neural core
The core now moves with KIRA's spoken reply rather than running a fixed talking
animation. Neural audio is analysed locally with the Web Audio API: loudness
controls expansion and glow, while low/high frequencies reshape the energy shell
and animate the inner rings. Pauses relax the core; playback ending or muting it
returns it smoothly to idle. No microphone audio is analysed for this effect.

Browser speech uses word-boundary events when the selected voice supplies them.
Otherwise it uses approximate text-paced motion. This is speech-rhythm animation,
not phoneme/lip synchronization or word-meaning recognition. If Web Audio is
unavailable, audio still plays normally with estimated motion. The operating
system's **Reduce motion** preference disables deformation and moving effects,
leaving a subtle brightness cue.

**If the core appears still:**
1. Close KIRA, update your checkout and relaunch `python main_window.py`.
2. Look for **SPEECH SYNC 02** in the right-hand panel. If it is absent, you
   are running an older copy/build. The source UI is now served without caching.
3. Click **MOTION: AUTO** once to select **MOTION: ON**. This is an explicit
   opt-in to animation even if Windows requests reduced motion; Off/Auto remain
   available, and your choice is remembered.
4. Click **TEST MOTION**. The whole core should breathe for three seconds. This
   checks rendering without audio, Ollama or a command to your computer.
5. Leave voice output on and click **TEST VOICE**. Watch the red meter:
   **AUDIO** means real audio samples, **WORD TIMING** means browser word events,
   and **ESTIMATED** means approximate timing. **QUIET / NO SIGNAL** means no
   measurable output at that moment; **SYSTEM SETTING** means motion is disabled.
6. Ask for a longer reply, then mute it mid-sentence. The core should settle.

The complete neuron now expands with speech, so the response is visible rather
than limited to the small central light. Quiet audio gets gentle gain. A slow
browser voice no longer stops animating merely because its timing estimate ran
out; that fallback remains approximate until real speech-end/boundary events.
If the visual-only test works but voice does not, report the meter/status text
and whether you can hear the reply. Neither test analyses the microphone.

**Developer checks** (Node.js 22+, no npm packages required):
```sh
node --check ui/app.js
node --check ui/speech.mjs
node --test tests/*.test.mjs
python -m unittest discover -s tests -p "test_*.py"
python -m ruff check .     # linter, from requirements-dev.txt
```
The Python tests are hermetic: the health/diagnostic probes are stubbed, so
nothing needs Ollama, the network or a microphone to pass. `ruff check .` runs
the rule set pinned in `pyproject.toml` (pyflakes + bugbear + whitespace) and
runs in CI before the test suite.
The tests cover the audio envelope, fallback timing, interruption/mute, stale
callbacks, resource cleanup and the actual app's reactor wiring with rendering
and audio test doubles. A real headless Chromium test with decoded PCM audio also exercised the actual
WebGL renderer and the controls. These checks do not replace a Windows/WebView2
listening test.

## 🏗️ Architecture

### Source layout (refactored 2026-10)

The code lives in the **`src/kira/` package**, organised by responsibility —
presentation is fully separated from logic:

```
src/kira/
├── core/           kira_language, kira_speech, kira_cache
├── services/       kira_ai, kira_planner, kira_tts, kira_voice_agent
├── data/           kira_memory, kira_tasks, kira_shared_memory
├── api/            kira_api (same-origin REST bridge)
├── presentation/   kira_ui, kira_theme, main_window, main_window_tk, launch_web
├── tools/          kira_commands, kira_open, kira_code, kira_docs, kira_ops,
│                   kira_agents, kira_info, kira_web, kira_scheduler,
│                   kira_plugins, kira_tools, kira_health, kira_build
├── bin/            tools_add_provider_keys
└── paths.py        PROJECT_ROOT anchor (.env, ui/, assets/, plugins/, db…)
```

The root-level names (`kira_ai.py`, `main_window.py`, …) are thin
**compatibility shims**: every historical import, launch command, test and
the PyInstaller build keep working unchanged; `python main_window.py`,
`python launch_web.py` and `python main_window_tk.py` behave exactly as
before. Data and resources stay at the repository root (`.env`,
`kira_memory.db`, `ui/`, `assets/`, `plugins/`, `kira_workspace/`…).

### Core Modules

- **kira_voice_agent.py** — Voice recognition, TTS, command parsing, action execution
- **main_window.py** — Desktop UI with CustomTkinter and animated HUD
- **kira_memory.py** — SQLite-based persistent memory system (local only)
- **kira_shared_memory.py** — Supabase shared knowledge (non-personal only)
- **kira_tasks.py** — Task, reminder, and timer management
- **kira_plugins.py** — Plugin discovery and registration system
- **kira_api.py** — REST API bridge for web UI

### Data Flow

```
Voice/Text Input
    ↓
Command Parser (parse_simple_command)
    ↓
Plugin Parser (try_parse_command)
    ↓
Action Router (execute_action)
    ↓
Action Handler (open_app, search, etc.)
    ↓
Response (speak/display)
```

### Memory System

KIRA uses SQLite with WAL mode for efficient concurrent access:
- **conversations** — Chat history with session tracking
- **memories** — User preferences and facts
- **tasks** — Timers, reminders, todos

Personal data (conversations, names, preferences, tasks, private notes)
**always stays local** in `kira_memory.db`. It is never sent to Supabase.

### Shared Knowledge (Supabase)

KIRA can share **non-personal** knowledge with a Supabase project so several
KIRA instances reuse the same knowledge base:

- public web research (`search_and_learn`, `learn_from_url`) — kind `web_research`
- learned public web pages (`learn_from_url`) — kind `web_page`
- shared project knowledge ("remember project knowledge: …") — kind `project_knowledge`

Setup:

1. Run `SUPABASE_SCHEMA.sql` in the Supabase SQL editor. It creates the
   `shared_knowledge` table with Row Level Security (public read, insert and
   refresh; deletions restricted to authenticated users), a privacy-guard
   trigger and a ranked search function.
2. Copy `.env.example` to `.env` and fill in:
   - `SUPABASE_URL` — your project URL
   - `SUPABASE_ANON_KEY` — the **anon / publishable** key only

Security and privacy:

- KIRA only ever uses the public **anon** key. The `service_role` key
  bypasses Row Level Security and is **never** used by KIRA: if KIRA detects
  one in the environment it is ignored and a warning is logged, and if a
  service_role key is placed in `SUPABASE_ANON_KEY` the client refuses to
  connect.
- Content that looks personal (names, preferences, credentials, contact
  details, private notes) is refused by `kira_shared_memory.py` and stays
  local. KIRA also registers the user's name and identity facts from local
  memory as terms that can never be published.
- The guard fails closed: when KIRA is unsure, the entry is kept local and
  simply not shared (`SUPABASE_SCHEMA.sql` enforces the same rules again with
  a trigger, even for privileged roles).
- Without a `.env`, shared knowledge is simply disabled and KIRA works fully
  offline exactly as before.

Voice commands: "search shared knowledge for …", "what do we know about …",
"remember project knowledge: …". Learned web research is saved locally
**and** shared to Supabase best-effort.

### Animation System

The HUD uses optimized canvas animations:
- Matrix rain background
- Animated neural core orb
- System telemetry panels
- Frame-skipping for performance

## 🔧 Configuration

Edit `kira_config.json`:

```json
{
  "model": "qwen3:0.6b",
  "vision_model": "qwen3-vl:2b",
  "require_wake_word": false,
  "conversation_mode": false,
  "chat_history_limit": 12,
  "preferred_address": "sir",
  "shortcuts": {
    "work mode": [
      {"action": "open_app", "target": "vscode"},
      {"action": "open_app", "target": "chrome"}
    ]
  }
}
```

### Configuration Options

- **model** — Ollama model for text generation
- **vision_model** — Ollama model for vision tasks
- **require_wake_word** — Require "KIRA" before commands
- **conversation_mode** — Enable continuous conversation
- **chat_history_limit** — Number of messages to remember
- **preferred_address** — How to address the user (sir, captain, etc.)
- **shortcuts** — Custom multi-action shortcuts

## 🔊 KIRA Voice — local Kokoro TTS

KIRA speaks with a **fully local, free neural voice** (Kokoro v1.0, Apache-2.0 weights).
No ElevenLabs, no paid API, no API key — and once installed it works **completely offline**.

### Pipeline

```
USER → KIRA LLM/Orchestrator → Persona → Speech Formatter → Kokoro TTS → Audio
```

- The **speech formatter** (`src/kira/services/tts/speech_formatter.py`) turns long replies into
  short spoken sentences: markdown, code blocks and tables are never read aloud, clichés
  ("Certainly, sir.") are dropped, numbers and names survive, and replies are capped at a few
  spoken sentences (details stay visible in the UI).
- The **TTS manager** (`src/kira/services/tts/manager.py`) owns speaking modes
  (`normal`, `alert`, `serious`, `system`, `success`), the sentence-by-sentence audio queue
  (no overlapping clips) and barge-in: a new user utterance stops speech instantly.
- The **TTSProvider** contract (`src/kira/services/tts/base.py`) keeps engines swappable:
  `KokoroTTSProvider` (local) today, Piper/XTTS tomorrow — plus `EdgeTTSProvider`, the
  automatic fallback for non-English replies or when the local engine is off.
- Only KIRA speaks. Specialized agents return text to KIRA; KIRA's voice says it.

### Setup (one time, internet only for the download)

```bat
scripts\setup_kokoro.bat
```

That installs a Python 3.13 side-venv (`.kokoro-venv`) with the `kokoro-onnx` runtime and
downloads the model once (~354 MB into `models/kokoro/`). KIRA then starts its own local voice
server (`scripts/kokoro_server.py` on `http://127.0.0.1:7860`) automatically at launch.
Without the setup, KIRA stays fully functional and falls back to Edge voices (or text-only).

### Voices and tuning

Test and compare voices, speeds and modes in the built-in **VOICE LAB** (Paramètres →
Diagnostics → `VOICE LAB`, or `ui/voice_test.html`). English **female** Kokoro voices:
`af_heart` (default), `bf_emma`, `bf_isabella`, `bf_alice`, `bf_lily` (UK) and `af_nicole`,
`af_nova`, `af_sarah`, `af_river`, `af_sky`, `af_kore`, `af_jessica`, `af_bella`, `af_alloy` (US).
Only female voices are offered: male names (Kokoro `am_*`/`bm_*`, Edge `henri`, Windows
`David`…) are never selected by KIRA — they would only be used if the OS offers no female
voice at all for a language.
Default: `af_heart`, speed `0.94` — calm, precise, not robotic. Every clip is smoothed
before it leaves the engine: level-matched to a constant loudness, softly limited instead of
clipped (the raw model peaks above full scale), micro-faded at the trimmed edges, and given a
±3% tempo variation so consecutive sentences do not march at one speed. Pauses between
sentences follow the speaking mode (normal 0.45 s, serious 0.60 s, alert 0.14 s…) with a small
variation, which is what makes a reply breathe instead of ticking. All tuning lives in one
place: the `KIRA_TTS_*` section of `.env` (see `.env.example`). GPU acceleration is optional
(`KIRA_TTS_DEVICE=auto`); measured here, DirectML cannot run the Kokoro v1.0 encoder, so the
server automatically rebuilds itself on CPU — synthesis stays ~2× faster than real time and
KIRA never loses its voice.

### Voice status in the cockpit

The HUD shows the engine state (`● KIRA VOICE — ONLINE`, `◐ KIRA — SPEAKING`,
`○ KIRA VOICE — OFFLINE`) and the central orb follows the speaking state
(IDLE / LISTENING / THINKING / SPEAKING / INTERRUPTED / ERROR).
If the voice engine dies mid-session, KIRA keeps working as a text-only assistant.

## 🔌 API Reference

### REST API Endpoints

**GET** `/api/status` — System status  
**GET** `/api/config` — Current configuration  
**GET** `/api/history` — Conversation history  
**GET** `/api/memories` — Stored memories  
**GET** `/api/tasks` — Task list  
**GET** `/api/system` — System telemetry  
**GET** `/api/tts/status` — Voice layer state (engine, device, voices)  
**GET** `/api/tts/voices` — Voices of every engine

**POST** `/api/command` — Process a command  
**POST** `/api/chat` — Send chat message  
**POST** `/api/task` — Add a task  
**POST** `/api/remember` — Store a memory  
**POST** `/api/tts` — Text-to-speech audio (Kokoro local → Edge fallback)  
**POST** `/api/tts/plan` — Speech-formatted sentences for a reply (no audio)  
**POST** `/api/tts/stop` — Stop speaking and clear the queue  
**POST** `/api/tts/mode` — Select the speaking mode  

## 🎨 Customization

### Themes
Edit `kira_theme.py` to customize colors and animations.

### Plugins
Create new plugins in the `plugins/` directory following the example template.

### Voice
Configure TTS voice in `kira_voice_agent.py` by modifying `SAPI_VOICE`.

## 🐛 Troubleshooting

**Microphone not working:**
- Check microphone permissions
- Run KIRA and select the correct microphone when prompted

**Ollama connection failed:**
- Ensure Ollama is running: `ollama serve`
- Verify models are installed: `ollama list`

**Slow performance:**
- Reduce animation frame rate in `main_window.py`
- Disable matrix rain if needed
- Use a smaller Ollama model

**Memory database locked:**
- Close other KIRA instances
- Delete `kira_memory.db` to reset (loses history)

## 📊 Performance

Optimized for resource efficiency:
- **Animation:** 60ms frame interval with frame-skipping
- **System stats:** Updated every 2 seconds
- **SQLite:** WAL mode with 2MB cache
- **Memory:** Lazy imports and connection pooling
- **Threading:** Background threads for timers and API

## 📝 License

This project is provided as-is for educational and personal use.

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- More plugins (email, calendar, weather)
- Additional languages
- Improved vision capabilities
- Better error handling
- Performance optimizations

## 🙏 Acknowledgments

- **Ollama** — Local LLM inference
- **CustomTkinter** — Modern UI framework
- **PyAutoGUI** — Computer automation
- **Three.js** — Web UI 3D graphics

---

**KIRA** — Your local AI companion, always ready to assist.

## Consolidated branches

The active interface follows MED’s French black-and-gold design. See
[BRANCH_CONSOLIDATION.md](BRANCH_CONSOLIDATION.md) for integration decisions,
validation, and the manual transition to `main`, `zakaria`, and the MED branch.
