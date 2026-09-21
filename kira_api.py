"""
KIRA Web API Bridge — Lightweight HTTP server for the web UI.

Provides a REST API so the HTML/Three.js frontend can communicate
with the KIRA backend. Resource-efficient: uses Python's built-in
http.server with minimal overhead.
"""

import json
import logging
import os
import sys
import threading
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# Will be set by main_window or kira_voice_agent
_backend = None
_events_callback = None
_command_handler = None

DEFAULT_PORT = 8765
DEFAULT_HOST = "0.0.0.0"


def set_backend(module):
    """Set the KIRA backend module for API access."""
    global _backend
    _backend = module


def set_events_callback(callback):
    """Set callback for getting recent events."""
    global _events_callback
    _events_callback = callback


def set_command_handler(handler):
    """Set a custom command handler function.
    
    The handler receives (text: str) and should return a dict like:
    {"action": "chat", "response": "Hello!"}
    or {"error": "something went wrong"}
    """
    global _command_handler
    _command_handler = handler


class KiraAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for KIRA API."""

    def log_message(self, format, *args):
        """Suppress default logging to keep output clean."""
        logger.debug(format, *args)

    def _send_json(self, data, status=200):
        """Send a JSON response."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self):
        """Allow CORS for local development."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/api/status":
            self._handle_status()
        elif path == "/api/config":
            self._handle_config()
        elif path == "/api/history":
            self._handle_history(params)
        elif path == "/api/memories":
            self._handle_memories(params)
        elif path == "/api/tasks":
            self._handle_tasks(params)
        elif path == "/api/system":
            self._handle_system()
        elif path == "/api/plugins":
            self._handle_plugins()
        elif path == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}

        if path == "/api/command":
            self._handle_command(data)
        elif path == "/api/chat":
            self._handle_chat(data)
        elif path == "/api/task":
            self._handle_add_task(data)
        elif path == "/api/task/complete":
            self._handle_complete_task(data)
        elif path == "/api/task/delete":
            self._handle_delete_task(data)
        elif path == "/api/remember":
            self._handle_remember(data)
        elif path == "/api/tts":
            self._handle_tts(data)
        elif path == "/api/web/search":
            self._handle_web_search(data)
        elif path == "/api/web/fetch":
            self._handle_web_fetch(data)
        else:
            self._send_json({"error": "Not found"}, 404)

    # ─────────────────────────────────────────
    # GET Handlers
    # ─────────────────────────────────────────

    def _handle_status(self):
        """Return current system status."""
        status = {
            "online": True,
            "model": getattr(_backend, "MODEL", "unknown") if _backend else "unknown",
            "conversation_mode": getattr(_backend, "_CONVERSATION_MODE", False) if _backend else False,
            "version": "V8",
        }
        self._send_json(status)

    def _handle_config(self):
        """Return the current configuration."""
        config = getattr(_backend, "CONFIG", {}) if _backend else {}
        # Don't expose sensitive data
        safe_config = {
            "model": config.get("model", ""),
            "conversation_mode": config.get("conversation_mode", False),
            "chat_history_limit": config.get("chat_history_limit", 12),
            "preferred_address": config.get("preferred_address", "sir"),
        }
        self._send_json(safe_config)

    def _handle_history(self, params):
        """Return conversation history."""
        limit = int(params.get("limit", [20])[0])
        try:
            import kira_memory
            messages = kira_memory.load_recent_messages(limit=limit)
            self._send_json({"messages": messages})
        except Exception as e:
            self._send_json({"messages": [], "error": str(e)})

    def _handle_memories(self, params):
        """Return stored memories."""
        category = params.get("category", [None])[0]
        try:
            import kira_memory
            memories = kira_memory.load_memories(category=category)
            self._send_json({"memories": memories})
        except Exception as e:
            self._send_json({"memories": [], "error": str(e)})

    def _handle_tasks(self, params):
        """Return tasks list."""
        try:
            import kira_tasks
            task_type = params.get("type", [None])[0]
            completed_param = params.get("completed", [None])[0]
            completed = None
            if completed_param is not None:
                completed = completed_param.lower() in ("true", "1", "yes")
            tasks = kira_tasks.list_tasks(task_type=task_type, completed=completed)
            self._send_json({"tasks": tasks})
        except Exception as e:
            self._send_json({"tasks": [], "error": str(e)})

    def _handle_system(self):
        """Return system telemetry."""
        try:
            import psutil
            data = {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_used_gb": round(psutil.virtual_memory().used / (1024**3), 1),
                "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
                "disk_percent": psutil.disk_usage("/").percent,
            }
            # GPU info (Windows)
            try:
                import subprocess
                result = subprocess.run(
                    ["wmic", "path", "win32_VideoController", "get", "name"],
                    capture_output=True, text=True, timeout=5,
                )
                lines = [l.strip() for l in result.stdout.splitlines() if l.strip() and "Name" not in l]
                data["gpu"] = lines[0] if lines else "Unknown"
            except Exception:
                data["gpu"] = "N/A"
            self._send_json(data)
        except Exception as e:
            self._send_json({"error": str(e)})

    def _handle_plugins(self):
        """Return loaded plugins."""
        try:
            import kira_plugins
            plugins = kira_plugins.list_plugins()
            self._send_json({"plugins": plugins})
        except Exception:
            self._send_json({"plugins": []})

    # ─────────────────────────────────────────
    # POST Handlers
    # ─────────────────────────────────────────

    def _handle_command(self, data):
        """Process a voice/text command."""
        text = str(data.get("text", "")).strip()
        if not text:
            self._send_json({"error": "No text provided"}, 400)
            return

        # Use custom command handler if registered (from main_window.py)
        if _command_handler is not None:
            try:
                result = _command_handler(text)
                self._send_json(result)
                return
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
                return

        # Fallback: use backend directly
        if _backend is None:
            self._send_json({"error": "Backend not available"}, 503)
            return

        try:
            cleaned = _backend.normalize_command(text)
            if not cleaned:
                self._send_json({"response": "", "action": "none"})
                return

            result = _backend.parse_simple_command(cleaned)
            if result is None:
                answer = _backend.ask_chat(cleaned)
                self._send_json({"response": answer, "action": "chat"})
                return

            action = result.get("action", "none")
            if action != "none":
                success = _backend.execute_action(result)
                self._send_json({
                    "action": action,
                    "success": success,
                    "details": _backend.describe_action(result),
                })
            else:
                answer = _backend.ask_chat(cleaned)
                self._send_json({"response": answer, "action": "chat"})

        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_chat(self, data):
        """Send a chat message and get a response."""
        text = str(data.get("text", "")).strip()
        if not text:
            self._send_json({"error": "No text provided"}, 400)
            return

        if _backend is None:
            self._send_json({"error": "Backend not available"}, 503)
            return

        try:
            answer = _backend.ask_chat(text)
            self._send_json({"response": answer})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_add_task(self, data):
        """Add a new task."""
        try:
            import kira_tasks
            title = str(data.get("title", "")).strip()
            task_type = str(data.get("type", "todo")).strip()
            body = str(data.get("body", "")).strip()
            due_at = str(data.get("due_at", "")).strip()
            priority = int(data.get("priority", 0))

            if not title:
                self._send_json({"error": "Title required"}, 400)
                return

            task_id = kira_tasks.add_task(
                title=title, task_type=task_type,
                body=body, due_at=due_at, priority=priority,
            )
            self._send_json({"id": task_id, "success": True})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_complete_task(self, data):
        """Complete a task."""
        try:
            import kira_tasks
            task_id = str(data.get("id", "")).strip()
            if not task_id:
                self._send_json({"error": "Task ID required"}, 400)
                return
            success = kira_tasks.complete_task(task_id)
            self._send_json({"success": success})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_delete_task(self, data):
        """Delete a task."""
        try:
            import kira_tasks
            task_id = str(data.get("id", "")).strip()
            if not task_id:
                self._send_json({"error": "Task ID required"}, 400)
                return
            success = kira_tasks.delete_task(task_id)
            self._send_json({"success": success})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_remember(self, data):
        """Store a memory."""
        try:
            import kira_memory
            category = str(data.get("category", "user_preference")).strip()
            key = str(data.get("key", "")).strip()
            value = str(data.get("value", "")).strip()

            if not key or not value:
                self._send_json({"error": "Key and value required"}, 400)
                return

            success = kira_memory.save_memory(category, key, value)
            self._send_json({"success": success})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_tts(self, data):
        """Generate text-to-speech audio using neural voices."""
        try:
            import kira_tts
            
            text = str(data.get("text", "")).strip()
            voice = data.get("voice", None)  # Optional voice name
            
            if not text:
                self._send_json({"error": "Text required"}, 400)
                return
            
            # Generate audio file
            audio_path = kira_tts.generate_speech(text, voice)
            
            if not audio_path:
                self._send_json({"error": "Failed to generate speech"}, 500)
                return
            
            # Read audio file and encode as base64
            with open(audio_path, "rb") as f:
                audio_data = f.read()
            
            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
            
            self._send_json({
                "success": True,
                "audio": audio_base64,
                "format": "mp3"
            })
            
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_web_search(self, data):
        """Search the web using DuckDuckGo."""
        try:
            import kira_web
            
            query = str(data.get("query", "")).strip()
            num_results = int(data.get("num_results", 5))
            
            if not query:
                self._send_json({"error": "Query required"}, 400)
                return
            
            results = kira_web.search_web(query, num_results)
            self._send_json({"success": True, "results": results})
            
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_web_fetch(self, data):
        """Fetch and extract content from a web page."""
        try:
            import kira_web
            
            url = str(data.get("url", "")).strip()
            max_length = int(data.get("max_length", 3000))
            
            if not url:
                self._send_json({"error": "URL required"}, 400)
                return
            
            result = kira_web.fetch_webpage(url, max_length)
            self._send_json(result)
            
        except Exception as e:
            self._send_json({"error": str(e)}, 500)


def start_server(host=DEFAULT_HOST, port=DEFAULT_PORT, daemon=True):
    """Start the API server in a background thread."""
    server = HTTPServer((host, port), KiraAPIHandler)
    server.timeout = 1

    thread = threading.Thread(target=_run_server, args=(server,), daemon=daemon)
    thread.start()

    logger.info("KIRA API server started on %s:%d", host, port)
    return server


def _run_server(server):
    """Run the server loop."""
    try:
        server.serve_forever(poll_interval=1)
    except Exception:
        pass


def stop_server(server):
    """Stop the API server."""
    try:
        server.shutdown()
    except Exception:
        pass
