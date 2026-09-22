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
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial

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
WINDOW_TITLE = "KIRA — Neural Interface"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900


# ─────────────────────────────────────────────
# HTTP Server for UI files
# ─────────────────────────────────────────────

class QuietHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves UI files with minimal logging."""
    
    def log_message(self, format, *args):
        pass  # Suppress access logs


def start_ui_server():
    """Start HTTP server for UI files on UI_PORT."""
    ui_dir = HERE / "ui"
    handler = partial(QuietHandler, directory=str(ui_dir))
    server = HTTPServer((HOST, UI_PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ─────────────────────────────────────────────
# Command Processing (shared by HTTP API and pywebview bridge)
# ─────────────────────────────────────────────

def _try_builtin_response(text):
    """Handle common greetings and questions without needing Ollama."""
    lower = text.strip().lower()
    
    greetings = {
        "hello", "hi", "hey", "good morning", "good afternoon",
        "good evening", "salut", "bonjour", "مرحبا", "hey kira",
        "hello kira", "hi kira",
    }
    
    if lower in greetings:
        # JARVIS-style greetings
        import random
        greetings_list = [
            "Good day, sir.",
            "Welcome back, sir.",
            "At your service, sir.",
            "Good to see you, sir.",
            "Hello, sir. All systems are operational."
        ]
        return random.choice(greetings_list)
    
    if lower in {"who are you", "what are you", "what is kira"}:
        return "I'm KIRA, sir - your personal AI assistant, modeled after JARVIS. I manage your systems, search the web, learn continuously, and anticipate your needs. Think of me as your digital butler and strategic advisor."
    
    if lower in {"what can you do", "help", "commands"}:
        return (
            "I'm equipped to handle quite a lot, sir. I control your computer systems - applications, files, media. "
            "I search the web and learn from it, building knowledge over time. I manage tasks and reminders, "
            "analyze your screen, and I'm always ready to assist with whatever you need. Shall I demonstrate something specific?"
        )
    
    if lower in {"what time is it", "time", "current time"}:
        from datetime import datetime
        current_time = datetime.now().strftime('%H:%M')
        return f"The time is {current_time}, sir."
    
    if lower in {"what is the date", "today's date", "date", "what day is it"}:
        from datetime import datetime
        current_date = datetime.now().strftime('%A, %B %d, %Y')
        return f"Today is {current_date}, sir."
    
    if lower in {"thank you", "thanks", "merci"}:
        # JARVIS-style acknowledgments
        import random
        thanks_list = [
            "You're quite welcome, sir.",
            "My pleasure, sir.",
            "Always at your service.",
            "Happy to be of assistance.",
            "Of course, sir."
        ]
        return random.choice(thanks_list)
    
    if lower in {"goodbye", "bye", "see you", "exit", "quit"}:
        # JARVIS-style farewells
        import random
        farewell_list = [
            "Goodbye, sir. I'll be here when you return.",
            "Until next time, sir.",
            "Take care, sir. I'll keep things running.",
            "Farewell, sir.",
            "Good day, sir."
        ]
        return random.choice(farewell_list)
        
        # Check if it's a web search request
        search_keywords = ["search for", "search", "look up", "find", "google", "what is", "who is", "where is", "when did", "how to", "latest", "news about", "current", "recent"]
        if any(keyword in lower for keyword in search_keywords):
            # Extract the search query
            query = text
            for prefix in ["search for", "search", "look up", "find", "google"]:
                if lower.startswith(prefix):
                    query = text[len(prefix):].strip()
                    break
            
            print(f"[KIRA] Web search requested: {query}")
            try:
                import kira_web
                return kira_web.search_and_summarize(query)
            except Exception as e:
                return f"I tried to search the web but encountered an error: {str(e)}"
        
        # Check if it's a learn/research request (search and store in memory)
        learn_keywords = ["learn about", "research", "study", "memorize", "remember this", "teach yourself"]
        if any(keyword in lower for keyword in learn_keywords):
            # Extract the topic
            query = text
            for prefix in ["learn about", "research", "study", "memorize", "teach yourself about"]:
                if lower.startswith(prefix):
                    query = text[len(prefix):].strip()
                    break
            
            print(f"[KIRA] Learn and memorize requested: {query}")
            try:
                import kira_web
                return kira_web.search_and_learn(query)
            except Exception as e:
                return f"I tried to learn about that but encountered an error: {str(e)}"
        
        # Check if it's a URL to learn from
        if lower.startswith("http://") or lower.startswith("https://") or "www." in lower:
            # It's a URL - learn from it
            url = text
            if not url.startswith("http"):
                url = "https://" + url
            
            print(f"[KIRA] Learning from URL: {url}")
            try:
                import kira_web
                return kira_web.learn_from_url(url)
            except Exception as e:
                return f"I tried to learn from that URL but encountered an error: {str(e)}"
        
        return None


def process_command(text):
    """Process a command — used by both HTTP API and pywebview bridge."""
    if backend is None:
        return {"error": f"Backend not available: {BACKEND_ERROR}"}
    
    # Check cache first (skip for commands that should always execute)
    if CACHE_ENABLED:
        cache_key = f"cmd:{hash(text)}"
        cached_result = command_cache.get(cache_key)
        if cached_result is not None:
            print(f"[KIRA] Cache hit for command: {text[:50]}", flush=True)
            return cached_result
    
    try:
        print(f"[KIRA] Processing: {text}", flush=True)
        cleaned = backend.normalize_command(text)
        if not cleaned:
            return {"action": "none", "response": ""}
        
        # Try built-in responses first (no Ollama needed)
        builtin = _try_builtin_response(cleaned)
        if builtin:
            print(f"[KIRA] Built-in: {builtin[:60]}", flush=True)
            result = {"action": "chat", "response": builtin}
            # Cache built-in responses
            if CACHE_ENABLED:
                command_cache.set(cache_key, result, ttl=300)  # 5 min TTL
            return result
        
        # Try command parsing
        result = backend.parse_simple_command(cleaned)
        if result is not None:
            action = result.get("action", "none")
            if action != "none":
                success = backend.execute_action(result)
                try:
                    reply = backend.build_reply(
                        backend.detect_language(cleaned),
                        action,
                        str(result.get("target", result.get("query", "")))
                    )
                except Exception:
                    reply = f"Done: {action}"
                print(f"[KIRA] Action: {action} -> {success}", flush=True)
                result = {"action": action, "success": success, "response": reply}
                # Don't cache action executions (they change state)
                return result
        
        # Fall back to Ollama chat
        print("[KIRA] Asking Ollama...", flush=True)
        try:
            answer = backend.ask_chat(cleaned)
            if answer:
                print(f"[KIRA] Ollama: {answer[:80]}...", flush=True)
                result = {"action": "chat", "response": answer}
                # Cache Ollama responses
                if CACHE_ENABLED:
                    command_cache.set(cache_key, result, ttl=300)  # 5 min TTL
                return result
            else:
                return {"action": "chat", "response": "I received your message but could not generate a response. Is Ollama running?"}
        except Exception as chat_error:
            print(f"[KIRA] Ollama error: {chat_error}", flush=True)
            return {
                "action": "chat",
                "response": f"I couldn't reach the AI engine. Make sure Ollama is running with: ollama serve\n\nError: {chat_error}"
            }
    except Exception as e:
        print(f"[KIRA] Error: {e}", flush=True)
        return {"error": str(e)}


# ─────────────────────────────────────────────
# Python-JS Bridge API (for pywebview)
# ─────────────────────────────────────────────

class KiraAPI:
    """Python API exposed to JavaScript via pywebview."""
    
    def send_command(self, text):
        return process_command(text)
    
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
    
    # 2. Start the API server
    print(f"[2/4] Starting API server on http://{HOST}:{API_PORT}")
    try:
        api_server = kira_api.start_server(host=HOST, port=API_PORT, daemon=True)
        time.sleep(0.5)  # Give server time to start
        print("       API server started")
    except Exception as e:
        print(f"       [ERROR] Failed to start API server: {e}")
        api_server = None
    
    # 3. Start the UI server
    print(f"[3/4] Starting UI server on http://{HOST}:{UI_PORT}")
    try:
        ui_server = start_ui_server()
        time.sleep(0.3)  # Give server time to start
        print("       UI server started")
    except Exception as e:
        print(f"       [ERROR] Failed to start UI server: {e}")
        print(f"       Port {UI_PORT} may be in use. Try closing other apps.")
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    # 4. Create native window
    print("[4/4] Creating native window...")
    time.sleep(0.5)
    
    # Create the API bridge
    api = KiraAPI()
    
    # Create the window
    window = webview.create_window(
        WINDOW_TITLE,
        f"http://{HOST}:{UI_PORT}",
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
    webview.start(debug=False)
    
    # Cleanup when window is closed
    print("\n[KIRA] Shutting down...")
    kira_api.stop_server(api_server)
    ui_server.shutdown()
    print("[KIRA] Goodbye.")


if __name__ == "__main__":
    main()
