"""
KIRA — Neural Interface (Native App)

This is the main entry point for KIRA as a native desktop application.
It uses pywebview to create a native window that renders the web UI,
making it look and feel like a real desktop app (no browser chrome).
"""

import os
import sys
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer
from kira_ui import KiraUIHandler, UI_BUILD_LABEL, validate_ui_bundle, print_ui_info, webview_profile_directory
from functools import partial
import kira_commands

# Add project root to path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Import KIRA backend modules with error handling
backend = None
BACKEND_ERROR = None

try:
    import kira_api
    print("[OK] kira_api loaded")
except Exception as e:
    print(f"[ERROR] Failed to import kira_api: {e}")
    kira_api = None

try:
    import kira_voice_agent as backend
    print("[OK] kira_voice_agent loaded")
except Exception as e:
    print(f"[WARNING] Failed to import kira_voice_agent: {e}")
    print("         Some features may not work (voice, actions, chat)")
    BACKEND_ERROR = str(e)
    backend = None

try:
    import kira_tasks
    print("[OK] kira_tasks loaded")
except Exception as e:
    print(f"[WARNING] Failed to import kira_tasks: {e}")
    kira_tasks = None

# Import caching
try:
    from kira_cache import command_cache, start_cache_cleanup_thread
    CACHE_ENABLED = True
    print("[OK] Caching enabled")
except ImportError:
    CACHE_ENABLED = False
    print("[WARNING] Caching not available")

# Try to import webview
try:
    import webview
    WEBVIEW_AVAILABLE = True
except ImportError:
    WEBVIEW_AVAILABLE = False
    print("Warning: pywebview not installed. Install with: pip install pywebview")

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

API_PORT = 8765
UI_PORT = 8766
HOST = "127.0.0.1"
WINDOW_TITLE = f"KIRA — {UI_BUILD_LABEL}"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900


# ─────────────────────────────────────────────
# HTTP Server for UI files
# ─────────────────────────────────────────────

class QuietHandler(KiraUIHandler):
    """Serve the cockpit and its same-origin API from the native window."""

    api_port = API_PORT


def _port_busy(host, port):
    """True si le port est déjà pris (vieux KIRA, autre application…)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def start_api_server():
    """Démarre l'API en essayant plusieurs ports si l'un est occupé.

    Un vieux processus KIRA qui traîne sur 8765 faisait échouer l'API en
    silence : l'UI répondait ensuite 503 à chaque message. On contourne
    en prenant le premier port libre et on le reflète dans le proxy UI.
    """
    for port in (API_PORT, 8767, 8769, 8771):
        try:
            server = kira_api.start_server(host=HOST, port=port, daemon=True)
            QuietHandler.api_port = port
            print(f"       API server started on port {port}")
            return server
        except Exception as error:
            print(f"       Port {port} indisponible ({error}), essai du suivant…")
    return None


def wait_api_healthy(timeout=4.0):
    """Attend que /health réponde avant d'ouvrir la fenêtre."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://{HOST}:{QuietHandler.api_port}/health", timeout=0.8
            ) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def start_ui_server():
    """Start HTTP server for UI files on UI_PORT (ports de secours inclus)."""
    ui_dir = validate_ui_bundle(HERE / "ui")
    print_ui_info(ui_dir)
    for port in (UI_PORT, 8768, 8770):
        try:
            handler = partial(QuietHandler, directory=str(ui_dir))
            server = ThreadingHTTPServer((HOST, port), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            UI_PORT_USED = port
            globals()["UI_PORT_USED"] = port
            print(f"       UI server started on port {port}")
            return server
        except OSError as error:
            print(f"       Port {port} indisponible ({error}), essai du suivant…")
    return None


# ─────────────────────────────────────────────
# Command Processing (shared by HTTP API and pywebview bridge)
# ─────────────────────────────────────────────

def _try_builtin_response(text, language=None):
    """Compatibility helper; canned replies must respect the requested language."""
    if language is None:
        language = kira_commands.languages.resolve_reply_language(text).language
    return kira_commands.builtin_reply(text, language)


def process_command(text, reply_language="auto", previous_language=None, interface_language="en", chat_only=False):
    """Native and HTTP use the same language-aware, non-retrying command path."""
    return kira_commands.process_command(
        backend, text, reply_language=reply_language, previous_language=previous_language,
        interface_language=interface_language, chat_only=chat_only,
    )


# ─────────────────────────────────────────────
# Python-JS Bridge API (for pywebview)
# ─────────────────────────────────────────────

class KiraAPI:
    """Python API exposed to JavaScript via pywebview."""
    
    def send_command(self, text, reply_language="auto", previous_language=None, interface_language="en"):
        return process_command(text, reply_language, previous_language, interface_language)
    
    def get_system_info(self):
        """Get system telemetry."""
        try:
            import psutil
            return {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": psutil.virtual_memory().percent,
                "gpu": "N/A"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_tasks(self):
        """Get pending tasks."""
        try:
            import kira_tasks
            tasks = kira_tasks.list_tasks(task_type="todo", completed=False)
            return {"tasks": tasks[:5]}
        except Exception as e:
            return {"tasks": [], "error": str(e)}
    
    def get_status(self):
        """Get KIRA status."""
        return {
            "online": True,
            "model": getattr(backend, "MODEL", "unknown"),
            "conversation_mode": getattr(backend, "_CONVERSATION_MODE", False)
        }


# ─────────────────────────────────────────────
# Main Application
# ─────────────────────────────────────────────

def main():
    """Main entry point."""
    
    if not WEBVIEW_AVAILABLE:
        print("\nError: pywebview is required to run KIRA as a native app.")
        print("Install it with: pip install pywebview")
        print("\nAlternatively, use launch_web.py to run in a browser.")
        sys.exit(1)
    
    print()
    print("=" * 60)
    print("              KIRA — NEURAL INTERFACE")
    print("=" * 60)
    print()
    
    # Start cache cleanup thread if caching is enabled
    if CACHE_ENABLED:
        print("[0/4] Starting cache cleanup thread...")
        start_cache_cleanup_thread(interval=300)  # Cleanup every 5 minutes
        print("       Cache cleanup active")
    
    if kira_api is None:
        print("[ERROR] kira_api module not available. Cannot start API server.")
        print("        Please ensure all dependencies are installed:")
        print("        pip install -r requirements.txt")
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    # 1. Set up the API backend
    print("[1/4] Initializing KIRA backend...")
    if backend is not None:
        kira_api.set_backend(backend)
        kira_api.set_command_handler(process_command)  # Register our command processor
        print("       Backend ready")
    else:
        print(f"       Backend unavailable: {BACKEND_ERROR}")
        print("       Chat and actions will not work, but UI will load")
    
    # 2. Start the API server (ports de secours si 8765 est occupé)
    print(f"[2/4] Starting API server on http://{HOST}:{API_PORT}")
    api_server = start_api_server()
    if api_server is not None:
        if wait_api_healthy():
            print("       API server healthy")
        else:
            print("       [WARNING] L'API ne répond pas encore à /health")
    
    # 3. Start the UI server
    print(f"[3/4] Starting UI server on http://{HOST}:{UI_PORT}")
    try:
        ui_server = start_ui_server()
        time.sleep(0.3)  # Give server time to start
        print("       UI server started")
    except Exception as e:
        print(f"       [ERROR] Failed to start UI server: {e}")
        print(f"       Close any older KIRA instance using port {UI_PORT} and check the complete ui/ folder.")
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    # 4. Create native window
    print("[4/4] Creating native window...")
    time.sleep(0.5)
    
    # Create the API bridge
    api = KiraAPI()
    
    # Create the window (sur le port UI réellement utilisé)
    window = webview.create_window(
        WINDOW_TITLE,
        f"http://{HOST}:{globals().get('UI_PORT_USED', UI_PORT)}",
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(1000, 700),
        js_api=api,
        text_select=True
    )
    
    print()
    print("=" * 60)
    print("  KIRA is running!")
    print()
    print("  The native window should now be open.")
    print("  Close the window to exit KIRA.")
    print("=" * 60)
    print()
    
    # Start the webview event loop
    # pywebview defaults to private mode; localStorage would otherwise disappear
    # on exit, including language, voice and lip-sync preferences.
    profile = webview_profile_directory()
    profile.mkdir(parents=True, exist_ok=True)
    webview.start(debug=False, private_mode=False, storage_path=str(profile))
    
    # Cleanup when window is closed
    print("\n[KIRA] Shutting down...")
    kira_api.stop_server(api_server)
    ui_server.shutdown()
    print("[KIRA] Goodbye.")


if __name__ == "__main__":
    main()
