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
Use the command bar at the bottom of the interface to type commands instead of using voice.

### Web Interface
With `main_window.py` running, the interface is served at `http://127.0.0.1:8766`;
the API uses port 8765.

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
```
The tests cover the audio envelope, fallback timing, interruption/mute, stale
callbacks, resource cleanup and the actual app's reactor wiring with rendering
and audio test doubles. A real headless Chromium test with decoded PCM audio also exercised the actual
WebGL renderer and the controls. These checks do not replace a Windows/WebView2
listening test.

## 🏗️ Architecture

### Core Modules

- **kira_voice_agent.py** — Voice recognition, TTS, command parsing, action execution
- **main_window.py** — Desktop UI with CustomTkinter and animated HUD
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
