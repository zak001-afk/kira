# KIRA — Local AI Computer Agent

**KIRA** is a sophisticated local AI assistant with voice control, computer automation, persistent memory, task management, and an extensible plugin system. Built for Windows with a cinematic HUD interface.

## ✨ Features

### Core Capabilities
- **Voice Control** — Natural language voice commands with wake word detection
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

**Opening files, apps and web pages (EN/FR/AR):**
- "Open google maps" / "Ouvre gmail" / "افتح يوتيوب" — known web pages and
  Google services open in the default browser.
- "Open notepad" / "Lance spotify" — KIRA checks whether the app exists on the
  PC (alias, direct launch, Windows Start Menu / install-folder search); when
  it does not, it opens a correct browser page: the known web version when one
  exists, otherwise a Google search page for the requested name.
- Open wishes work as commands: "je veux que tu ouvres facebook",
  "j'aimerais ouvrir google maps", "i want you to open youtube".
- Opens are fast: no document scan on app opens, pruned/time-limited file
  searches, cached Start Menu walk.
- "Open my report.pdf" / "Ouvre le document budget" — files are found by direct
  path first, then searched in Desktop/Documents/Downloads/Pictures/Music/Videos
  and opened with their default application.
- "Open folder downloads" / "Ouvre le dossier documents" — opens folders.
- "Open this pc" / "Ouvre ce pc" — the Windows "This PC" view; "ouvre le
  disque c", "open c drive", "disque dur" open drives; "corbeille" opens the
  recycle bin.
- By default KIRA searches **the whole PC** for files and folders, then
  opens directly when exactly one matches and asks which one when several
  do. The question explains how to answer, and KIRA accepts "2", "le 2",
  "n°2", "numero 2", "le deuxième", "tous" (open everything) or "annule" —
  valid for 10 minutes. A named location ("dans le dossier archives",
  "dans le disque d") limits the search exactly there.
- "Cherche moi les dossiers dell sur le c et ouvre chaque dossier" runs as
  one command: KIRA finds every folder named "dell" on C: (system folders
  included) and opens them all. "Find every file named rapport and open
  them" works the same way on the whole PC. The drive scan is breadth-first
  with a generous budget, so matches behind huge system trees (Program
  Files, Windows…) are found too — up to 20 opened at once.
- A bare "cherche le dossier dell dans tous le local c" (without "ouvre")
  is a real search too: singular finds ask which one when several match,
  plural finds ("cherche les dossiers dell…") open everything directly.
  "cherche … sur internet" keeps searching the web, never the disk. The
  place can be said first: "cherche dans le c les dossiers dell" searches
  C: exactly. Run `python voir_action.py <phrase>` to see the parsed
  action for any sentence.
- A bare "cherche dell dans le c" lists everything containing the word —
  folders AND files, typos tolerated ("delll", "dalle") — numbered; answer
  with the number to open that exact location, or "tous" to open all.
  Every search answers in 5 seconds max, whole PC included.
- "Ouvre tous les rapports" / "open all reports" opens every match at once.
- "Ouvre le dossier projets" finds a folder by name on the PC; a bare
  "open folder" opens Documents. Nested requests work: "ouvre le dossier
  missions dans le dossier travail", "ouvre le fichier rapport dans le
  disque d". Files and folders missed in the standard places are searched
  on **every drive, one by one** (a few seconds, honestly answered when not
  found). Apps on PATH and portable apps without shortcuts launch too.
  Replies name the target only — the request is never repeated back.
- Nicknames and typos resolve to the real thing: "ouvre insta",
  "instagrame", "facebok", "yutube" work.
- Pages and searches open in **Chrome by default**. Name another browser for
  one request: "ouvre facebook sur firefox", "open google maps in edge",
  "open spotify with brave". Without Chrome, the system browser is used.
- Politeness and filler never hide the target: "Peux-tu m'ouvrir google ?",
  "ouvre moi l'application gmail", "stp ouvre youtube" all work.
- KIRA opens things on the computer running the KIRA engine (your PC). The
  interface preview without an engine honestly refuses instead.
- If an app is not installed, the failure says so in the reply language
  ("Je n'ai pas pu ouvrir X sur cet ordinateur...") instead of a generic error.
- Mentioning an app inside a question ("Who created Google?") opens nothing.

**Task Management:**
- "Remind me to call mom in 5 minutes"
- "Set a timer for 30 minutes"
- "Add todo buy groceries"
- "List tasks"
- "Clear completed tasks"

**Memory:**
- "Remember that my favorite color is blue"
- "Call me commander"
- "My name is Zakaria"

**System:**
- "System info"
- "What time is it"
- "What's today's date"
- "Help"

### Text Input
Use the command bar at the bottom of the conversation panel to type commands instead of using voice. Press **Ctrl+K** (or **Cmd+K**) to focus it.

### Holographic cockpit interface
KIRA's native window and browser mode use the same redesigned `ui/` interface:
- A blue-eyed android projection inside animated red orbital rings.
- Angular, double-framed conversation and live telemetry panels.
- A machined projection platform and lower quick-action console.
- Working voice/mute controls, command input, task creation/completion, settings,
  diagnostics and fullscreen. Search/Learn prepare a prompt rather than executing
  an incomplete command.
- Responsive layouts, keyboard focus indicators and reduced-motion support.

The portrait is an original AI-generated illustration with a local 2D lip/jaw
rig, not a generated talking video or a full 3D avatar. SVG/CSS render the field;
a small Canvas 2D mesh deforms the actual lip/skin pixels during speech. No WebGL,
CDN or external font requests are needed. The bundled artwork and fonts also work offline. AI replies, desktop
control and neural speech still require their existing backend dependencies.

Start the application normally:
```sh
python main_window.py    # Native desktop window (Windows / pywebview)
python launch_web.py     # Browser mode, with the desktop backend
```
The UI is served at `http://127.0.0.1:8766`. The shared `kira_ui.py` handler proxies
same-origin `/api/*` requests to the loopback API on port 8765; the browser never
needs a second port or a `localhost` URL to another service. Static files are
served without caching so relaunching picks up a changed interface. The Windows
build scripts include `ui/`, including its artwork and fonts. Rebuild an existing
`.exe` with `build_kira.bat` to update its bundled interface.

**Hardware-independent visual preview** (no Ollama, microphone or Windows agent):
```sh
python kira_ui.py --preview
# For a proxied development workspace only:
python kira_ui.py --preview --host 0.0.0.0 --port 8766
```
Preview mode starts the real telemetry/task API, but does **not** load computer
control or AI chat. It is labelled **INTERFACE PREVIEW**. `psutil` provides real
system readings; unavailable readings show dashes, never simulated numbers.
Tasks still use the local SQLite database. The standalone UI without `--preview`
can also proxy an already-running API (`--api-port` changes its port).
KIRA is a local, unauthenticated computer agent: do not expose it publicly.

### Still seeing the old interface on Windows?
The source launcher can be run with your existing virtual environment:
```powershell
.\.venv\Scripts\python.exe main_window.py
```
No executable rebuild is needed for this command. **Update the complete project**,
including `ui/` and `kira_ui.py`, not just `main_window.py`. Arena workspace changes
are not automatically installed on your PC. Likewise, `git pull` on `main` does
not download an unmerged feature branch: fetch and switch to the branch containing
the redesign, or merge its pull request before updating `main`.

After updating, close the previous KIRA window and relaunch. The new title and UI
read **HOLOGRAPHIC COCKPIT 03 / LANGUAGES 01**. The console prints `[KIRA UI]`, the Python interpreter
and the absolute `ui/` path so you can identify the actual checkout being served.
The launcher rejects a missing or older UI bundle instead of quietly mixing versions.
Keep your `.venv`, configuration and local database; do not use a destructive reset
to get past a Git warning about local edits.

### Interface language, automatic replies and multilingual voices
Open **SETTINGS** (or **PARAMÈTRES** after switching to French):
- **Interface language** changes menus, buttons, statuses, task messages and help
  immediately. The bundled UI translations are English, French and Arabic; Arabic
  has RTL layout/text support and a local Noto Sans Arabic font. Past conversation
  text is deliberately not rewritten or translated by changing this setting.
- **Replies and voice → Automatic** follows the language of each question or its
  recognized transcript. Short/ambiguous follow-ups keep the preceding language.
  Choose a fixed language to always receive replies in it instead.
- An isolated instruction such as **“Réponds-moi en français”**, **“Reply in
  Spanish”** or **“أجب بالعربية”** selects that reply language and remembers it.
  An instruction attached to a question takes precedence for that question,
  without swallowing the question as a settings command. Translation requests
  keep their requested target language. Select **Automatic** again to switch
  freely between languages.
- **Voice input language** controls the browser recognizer separately. Its Auto
  option follows the current conversation language. **Web Speech listens in one
  locale at a time; this is not universal automatic detection of raw microphone
  audio.** Choose the listening language before switching to a different spoken
  language if transcription is wrong. Typed questions do not have this limitation.

The same language now travels from `/api/command` or `/api/chat` through the model,
written response and `/api/tts`. French requests no longer get an English canned
“sir” greeting. The model prompt no longer forces English, and confidently wrong-
language replies receive one translation attempt before being saved/displayed.
Actions are never re-executed for a translation. Conversational replies are not
cached across language choices or conversation turns.

Edge TTS selects an appropriate voice (for example `fr-FR-DeniseNeural` for French),
rather than always using Jenny. Browser fallback sets both the utterance locale
and a matching installed voice, including late-loading voice catalogs. If neither
engine has a matching voice, KIRA keeps the written reply and displays a notice
instead of silently reading it with an English voice. Word timing and lip sync
continue to follow the selected voice. Windows SAPI/pyttsx3 fallback also selects
by language instead of penalizing French voices.

Detection is local, using `langid` plus explicit-language, short-message and script
rules. There is no new model download or extra translation cloud service. Install
the new dependency in the **same environment used to launch KIRA**:
```powershell
.\.venv\Scripts\python.exe -m pip install langid
.\.venv\Scripts\python.exe main_window.py
```
`requirements.txt` includes it for fresh installs. Without it, explicit settings
and common-language/script heuristics still work, but automatic coverage is
reduced and Settings reports it. A language appearing in the catalog does **not**
guarantee that the chosen Ollama model or a speech provider supports it. The
configured small model may need to be replaced with a stronger multilingual model
for reliable answers. Detection can be ambiguous, especially on short or mixed-
language inputs; select a fixed reply language when needed. Existing desktop
command parsers/integrations retain their own language coverage.

Preferences are saved locally, independently for interface, replies and microphone.
The native window now uses a persistent pywebview profile instead of private mode:
`%LOCALAPPDATA%/KIRA/WebViewProfile` on Windows (XDG data directory elsewhere).
This profile is outside the checkout/build and does not modify your configuration
or conversation database. Native Windows listening tests and real model-language
quality still need checking on the target PC; automated tests use model/audio
fixtures and never execute desktop actions.

### Speech-reactive holographic field
KIRA's spoken replies drive the red field, portrait drift and voice waveform.
Neural audio is analysed locally with the Web Audio API: loudness expands the
rings, bass adds breadth, and treble brightens the field. Pauses relax it; ending
or muting playback returns it to idle. No microphone audio is analysed for this
effect. Slow ambient orbital motion is independent of speech.

Browser speech uses word-boundary events when available, with approximate
text-paced motion otherwise. This field motion does not recognize word meaning.
The additional mouth rig estimates speech shapes as described below. Without
Web Audio, playback still works with estimated timing. **Reduce motion** disables all ambient animation,
waveform movement, lip/jaw movement and speech displacement, leaving a subtle brightness cue.

**Check motion and voice:**
1. Open **SETTINGS** in the right panel, or use **HOLOGRAM** on the lower console.
   **MOTION: AUTO** follows the system; **ON** explicitly opts into motion;
   **OFF** keeps it still. The preference is remembered.
2. Open **DIAGNOSTICS**, then **TEST MOTION**. The dialog closes so you can watch
   the field breathe for three seconds, without audio, Ollama or a desktop command.
3. With voice output enabled, use **TEST VOICE**. The status under the left-hand
   waveform shows **AUDIO** for measured output, **WORD TIMING** for browser
   boundaries, **ESTIMATED** for approximate timing, or **QUIET / NO SIGNAL**.
4. Mute a reply mid-sentence; the portrait and rings settle back to idle.

### Lip synchronization (LIP SYNC 01)
The face now speaks as well as the field moving. The 2D facial rig opens the jaw,
rounds/widens the lips for vowel-like shapes, closes them for M/B/P-like shapes,
and provides a small lower-lip movement for F/V-like shapes. It warps the original
portrait texture and composites a small matching oral photograph, rather than
placing a cartoon mouth over the face. Its position follows the portrait at every
screen size, including `object-fit` letterboxing.

**Timing and its limits:**
- `/api/tts` now includes optional `word_timings` (start/duration in seconds),
  captured from the same Edge TTS stream as the MP3 and cached alongside it.
  Existing MP3 clients remain compatible. Edge versions with or without the
  `boundary` option are supported, and missing timing metadata never blocks audio.
- Word boundaries give a better time anchor; individual visemes within each word
  are **estimated from spelling**, not measured phonemes or forced alignment.
  English, French and Arabic letters have lightweight shape heuristics; irregular
  pronunciations, accents and other languages are approximate.
- Real playback time drives the timeline, and measured audio level gates the jaw.
  Leading silence, pauses, buffering, end-of-playback, interruptions and mute
  release or reset the mouth. Browser word events are used when available; the
  fallback is explicitly labelled as estimated timing.
- The animation stays still while waiting for a response or listening to the
  microphone. It only samples KIRA's own output audio. No talking-head model,
  face-recognition library, extra cloud service or GPU inference is added.

**Try it:** keep voice enabled and **SETTINGS → LIPS: ON**. Open **DIAGNOSTICS** and
click **TEST VOICE** for “Hello. Bonjour…” using the actual speech player.
**TEST LIPS** is a separate, labelled four-second visual check with no audio, AI
request or desktop action. Lip animation can be disabled independently; global
**MOTION: OFF** or the system's Reduce Motion in Auto mode also disables it.

The result is lightweight, audio-synchronized **2D approximation**, not human-
quality phoneme-perfect lip synchronization. A new portrait would need new facial
landmarks. If Canvas is unavailable, ordinary speech and the static portrait
remain available.

**Developer checks** (Node.js 22+ and Python, no npm packages required):
```sh
node --check ui/app.js
node --check ui/speech.mjs
node --check ui/hologram.mjs
node --check ui/lips.mjs
node --check ui/mouth.mjs
node --check ui/i18n.mjs
node --check ui/locale.mjs
node --test tests/*.test.mjs
python -m unittest discover -s tests -p "test_*.py"
```
These cover the audio envelope and lifecycle, actual controller/compositor wiring,
reduced motion, safe message rendering, command concurrency, unavailable data,
static assets, the same-origin API proxy, viseme timing, mouth geometry, and the
TTS word-timing cache. Optional real-browser regressions:
```sh
pip install playwright
playwright install chromium
python tests/cockpit_browser.py
```
The browser suite uses API fixtures, never desktop actions. It checks nine screen
sizes, commands, task creation/completion, persisted settings, offline states and
reduced motion. A decoded-PCM fixture exercises the real audio analyser and mouth
renderer, including speech intervals, silence, end-of-playback and mute; the tests
also check real painted mouth pixels. This is not a listening test of the Edge
service or a validation of human-quality phonemes. These checks do not replace a
Windows/WebView2 listening and desktop-control test.

## 🏗️ Architecture

### Core Modules

- **kira_voice_agent.py** — Voice recognition, TTS, command parsing, action execution
- **main_window.py** — Native pywebview window hosting the holographic cockpit
- **main_window_tk.py** — Legacy CustomTkinter interface
- **kira_ui.py** — Shared static asset server and same-origin API proxy
- **ui/** — Offline-capable cockpit, artwork, speech player and compositor
- **kira_memory.py** — SQLite-based persistent memory system
- **kira_tasks.py** — Task, reminder, and timer management
- **kira_plugins.py** — Plugin discovery and registration system
- **kira_api.py** — REST API bridge for web UI
- **kira_language.py** — Offline detection, explicit-language policy and voice matching
- **kira_commands.py** — Shared native/web command path with language metadata
- **kira_open.py** — Open-resolver for files, applications and web pages (EN/FR/AR)

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

## 🔌 API Reference

### REST API Endpoints

**GET** `/api/status` — System status  
**GET** `/api/config` — Current configuration  
**GET** `/api/history` — Conversation history  
**GET** `/api/memories` — Stored memories  
**GET** `/api/tasks` — Task list  
**GET** `/api/system` — System telemetry  

**POST** `/api/command` — Process a command  
**POST** `/api/chat` — Send chat message  
**POST** `/api/task` — Add a task  
**POST** `/api/remember` — Store a memory  

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
