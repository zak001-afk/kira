# KIRA Launch Modes

KIRA can be launched in two different modes:

## 1. Native Desktop App (Recommended)

**How to launch:**
- **Windows:** Double-click `launch_kira.bat`
- **Command line:** `python main_window.py`

**Features:**
- Runs as a native desktop window (no browser chrome)
- Uses pywebview to embed the web UI
- Direct Python-JS bridge for instant communication
- Looks and feels like a real desktop application
- Window can be resized, minimized, maximized
- Close the window to exit KIRA

**Requirements:**
- `pywebview` package (installed via requirements.txt)
- On Windows: Uses Edge WebView2 runtime (usually pre-installed)

---

## 2. Web Browser Mode

**How to launch:**
- **Command line:** `python launch_web.py`

**Features:**
- Opens in your default web browser
- Two local servers: API (port 8765) and UI (port 8766)
- Communication via HTTP REST API
- Can access from other devices on your network
- Good for development and testing

**Requirements:**
- No additional dependencies (uses built-in http.server)

---

## Which mode should I use?

- **Native app mode** is recommended for daily use
- **Browser mode** is useful for:
  - Development and debugging
  - Accessing KIRA from other devices
  - Systems where pywebview is not available
  - Testing the web UI

---

## Troubleshooting

### Native app won't start
- Make sure pywebview is installed: `pip install pywebview`
- On Windows, ensure Edge WebView2 runtime is installed
- Check the console for error messages

### Browser mode won't start
- Check if ports 8765 and 8766 are available
- Try accessing `http://localhost:8766` manually in your browser

### Both modes fail
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check that Ollama is running: `ollama serve`
- Verify the model is available: `ollama list`

---

## Technical Details

### Native App Architecture
```
main_window.py
├── Starts API server (port 8765)
├── Starts UI server (port 8766)
├── Creates pywebview window
└── Exposes Python API to JavaScript
    └── window.pywebview.api.send_command()
    └── window.pywebview.api.get_system_info()
    └── window.pywebview.api.get_tasks()
```

### Browser Mode Architecture
```
launch_web.py
├── Starts API server (port 8765)
├── Starts UI server (port 8766)
└── Opens browser to http://localhost:8766
    └── Communicates via HTTP REST API
        └── POST /api/command
        └── GET /api/system
        └── GET /api/tasks
```

---

**KIRA v8.1** — Your AI assistant, your way.
