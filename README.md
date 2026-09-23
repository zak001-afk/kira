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

The portrait is an original AI-generated illustration, not a live avatar or a
lip-synced video. SVG/CSS render the field without WebGL, a CDN or external font
requests. The bundled artwork and fonts also work offline. AI replies, desktop
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
read **HOLOGRAPHIC COCKPIT 01**. The console prints `[KIRA UI]`, the Python interpreter
and the absolute `ui/` path so you can identify the actual checkout being served.
The launcher rejects a missing or older UI bundle instead of quietly mixing versions.
Keep your `.venv`, configuration and local database; do not use a destructive reset
to get past a Git warning about local edits.

### Speech-reactive holographic field
KIRA's spoken replies drive the red field, portrait drift and voice waveform.
Neural audio is analysed locally with the Web Audio API: loudness expands the
rings, bass adds breadth, and treble brightens the field. Pauses relax it; ending
or muting playback returns it to idle. No microphone audio is analysed for this
effect. Slow ambient orbital motion is independent of speech.

Browser speech uses word-boundary events when available, with approximate
text-paced motion otherwise. This is speech-rhythm animation, **not** phoneme/lip
synchronization or word-meaning recognition. Without Web Audio, playback still
works with estimated timing. **Reduce motion** disables all ambient animation,
waveform movement and speech displacement, leaving a subtle brightness cue.

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

**Developer checks** (Node.js 22+ and Python, no npm packages required):
```sh
node --check ui/app.js
node --check ui/speech.mjs
node --check ui/hologram.mjs
node --test tests/*.test.mjs
python -m unittest discover -s tests -p "test_*.py"
```
These cover the audio envelope and lifecycle, actual controller/compositor wiring,
reduced motion, safe message rendering, command concurrency, unavailable data,
static assets and the same-origin API proxy. Optional real-browser regressions:
```sh
pip install playwright
playwright install chromium
python tests/cockpit_browser.py
```
The browser suite uses API fixtures, never desktop actions. It checks nine screen
sizes, commands, task creation/completion, persisted settings, offline states and reduced motion.
These checks do not replace a Windows/WebView2 listening and desktop-control test.

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
