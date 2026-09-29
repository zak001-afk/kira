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
import kira_language
import kira_commands
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# Will be set by main_window or kira_voice_agent
_backend = None
_events_callback = None
_command_handler = None

# Previous network counters, used to compute live transfer rates.
_net_lock = threading.Lock()
_net_last = {"sent": None, "recv": None, "ts": None}

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
    
    The handler receives text and may accept reply_language, previous_language,
    interface_language and chat_only keyword arguments. Older text-only handlers
    remain supported and are never called twice. It should return a dict like:
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
        """Send a JSON response; a vanished client is not an error.

        Closing the window mid-request aborts the socket (WinError 10053 /
        ConnectionAbortedError). The work already ran and nobody is listening,
        so log one quiet line and return — never retry, never re-raise.
        """
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError) as error:
            logger.debug("Client disconnected before the response was sent: %s", error)

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

        if path == "/api/languages":
            self._send_json(kira_language.available_languages())
        elif path == "/api/status":
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
        elif path == "/api/ai":
            self._handle_ai_providers()
        elif path == "/api/agents":
            self._handle_agents()
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
        elif path == "/api/web/learn":
            self._handle_web_learn(data)
        elif path == "/api/web/search-learn":
            self._handle_web_search_learn(data)
        else:
            self._send_json({"error": "Not found"}, 404)

    # ─────────────────────────────────────────
    # GET Handlers
    # ─────────────────────────────────────────

    def _handle_status(self):
        """Return current system status."""
        status = {
            "online": True,
            "backend_available": _backend is not None or _command_handler is not None,
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

    _last_net_io = None
    _last_net_time = None

    def _handle_system(self):
        """Return system telemetry."""
        try:
            import time as _time

            import psutil
            import time as _time
            data = {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "cpu_cores": psutil.cpu_count(logical=True),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_used_gb": round(psutil.virtual_memory().used / (1024**3), 1),
                "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
                "disk_percent": psutil.disk_usage("/").percent,
                "uptime_h": round(max(0.0, _time.time() - psutil.boot_time()) / 3600, 1),
            }
            # Live network rates (bytes/s since the previous call)
            try:
                net = psutil.net_io_counters()
                now = _time.time()
                with _net_lock:
                    prev_sent = _net_last["sent"]
                    prev_recv = _net_last["recv"]
                    prev_ts = _net_last["ts"]
                    _net_last["sent"] = net.bytes_sent
                    _net_last["recv"] = net.bytes_recv
                    _net_last["ts"] = now
                if prev_sent is not None and prev_ts is not None and now > prev_ts:
                    dt = now - prev_ts
                    data["net_sent_kbps"] = round(max(0.0, (net.bytes_sent - prev_sent) / dt / 1024), 1)
                    data["net_recv_kbps"] = round(max(0.0, (net.bytes_recv - prev_recv) / dt / 1024), 1)
                else:
                    data["net_sent_kbps"] = 0.0
                    data["net_recv_kbps"] = 0.0
            except Exception:
                data["net_sent_kbps"] = 0.0
                data["net_recv_kbps"] = 0.0
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

    def _handle_agents(self):
        """Real specialist/tool registry state and recent activity.

        Metadata only: tool names, ok/elapsed/error codes and timestamps.
        Queries, titles and results are never stored in the activity feed.
        """
        try:
            import kira_agents
            self._send_json({"agents": kira_agents.agents_snapshot(),
                             "activity": kira_agents.recent_activity(30)})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_ai_providers(self):
        """Report AI provider availability. Booleans only — never key material."""
        try:
            import kira_ai
            self._send_json(kira_ai.availability())
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

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

    def _handle_command(self, data, chat_only=False):
        """Resolve language in the shared command path, for native and web alike."""
        text = str(data.get("text", "")).strip()
        if not text:
            self._send_json({"error": "No text provided"}, 400)
            return
        options = {"reply_language": data.get("reply_language", "auto"),
                   "previous_language": data.get("previous_language"),
                   "interface_language": data.get("interface_language", "en"),
                   "chat_only": chat_only}
        for key in ("reply_language", "previous_language", "interface_language"):
            if options[key] is not None and kira_language.normalize_language(options[key]) is None:
                self._send_json({"error": "Unsupported language preference", "error_code": "invalid_language"}, 400)
                return
        learning_reply = kira_commands.try_web_learning(text)
        if learning_reply is not None:
            self._send_json({"response": learning_reply, "action": "web_learn"})
            return
        if _command_handler is None and _backend is None:
            self._send_json({"error": "Backend not available", "error_code": "backend_unavailable"}, 503)
            return
        try:
            if _command_handler is not None:
                result = kira_commands.call_with_options(_command_handler, text, **options)
            else:
                result = kira_commands.process_command(_backend, text, **options)
            self._send_json(result, 422 if result.get("error_code") == "reply_language_unavailable" else 200)
        except Exception as error:
            self._send_json({"error": str(error)}, 500)

    def _handle_chat(self, data):
        self._handle_command(data, chat_only=True)

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
            
            language = data.get("language", "auto")
            if kira_language.normalize_language(language) is None:
                self._send_json({"error": "Unsupported speech language", "error_code": "invalid_language"}, 400)
                return
            selected_language = kira_language.speech_language(text, language)
            selected_voice = kira_tts.select_neural_voice(text, voice=voice, language=selected_language)
            if not selected_voice:
                self._send_json({"error": "No neural voice available for this language", "error_code": "voice_unavailable", "language": selected_language}, 422)
                return
            # The audio and word timing use exactly the same selected voice.
            audio_path = kira_tts.generate_speech(text, selected_voice, language=selected_language)
            
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
                "format": "mp3",
                "word_timings": kira_tts.get_word_timings(audio_path),
                "language": selected_language,
                "locale": kira_language.locale_for(selected_language),
                "voice": selected_voice,
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

    def _handle_web_learn(self, data):
        """Learn from a URL and store in memory."""
        try:
            import kira_web
            
            url = str(data.get("url", "")).strip()
            
            if not url:
                self._send_json({"error": "URL required"}, 400)
                return
            
            result = kira_web.learn_from_url(url)
            self._send_json({"success": True, "message": result})
            
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_web_search_learn(self, data):
        """Search the web and store results in memory."""
        try:
            import kira_web
            
            query = str(data.get("query", "")).strip()
            
            if not query:
                self._send_json({"error": "Query required"}, 400)
                return
            
            result = kira_web.search_and_learn(query)
            self._send_json({"success": True, "message": result})
            
        except Exception as e:
            self._send_json({"error": str(e)}, 500)


def start_server(host=DEFAULT_HOST, port=DEFAULT_PORT, daemon=True):
    """Start the API server in a background thread."""
    # Threading : une commande lente ne bloque plus les autres requêtes.
    server = ThreadingHTTPServer((host, port), KiraAPIHandler)
    server.daemon_threads = True
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
