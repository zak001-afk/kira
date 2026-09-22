"""KIRA's web interface server: the browser talks to the real agent.

This serves ``ui/`` (the Three.js neural-interface) and exposes a small JSON
API that routes straight into KIRA's own command pipeline — the same one the
desktop UI and CLI use:

    parse_simple_command → chat question → think_about → confirmation
    → execute_action → reflect (learn_from)

Design notes
------------
* **Stdlib only** — ``http.server`` with a threading server, no frameworks.
* **Graceful degradation** — if the Windows backend cannot be imported (no
  pyautogui/TTS on this machine), the server still serves the interface and
  reports ``online: false`` with a reason instead of dying.
* **Simulation mode** (``--simulate``) — a clearly-labelled canned responder
  so the interface can be demonstrated without the full desktop stack.
* **Local by default** — binds ``127.0.0.1``. Use ``--host 0.0.0.0`` to reach
  it from a phone on your LAN (see the README for the caveat).
* **Proactive alerts reach the browser** — the system watchdog is started
  here with the alert callback queued for the page, so battery/CPU warnings
  appear in the conversation instead of being spoken into the void.

Voice: the server does **not** call KIRA's Windows TTS for web replies. The
browser speaks them with the Web Speech API instead, which works on any
platform and keeps the two interfaces from talking over each other. The
microphone button still uses KIRA's own offline recognition on the server.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import queue
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"
DEFAULT_PORT = 8788
DEFAULT_HOST = "127.0.0.1"

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

STATIC_EXTENSIONS = {
    ".html", ".js", ".mjs", ".css", ".json", ".map", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2", ".ttf", ".txt",
}

# extensionless files that browsers are allowed to fetch (third-party notices)
STATIC_NAMES = {"LICENSE", "LICENSE.txt", "NOTICE", "NOTICE.txt"}

MAX_BODY_BYTES = 64 * 1024

# How long a failed command keeps the HUD in its FAULT state.
ERROR_LINGER = 6.0


# ── simulation (used by --simulate and by tests) ─────────────────────────────

SIMULATED = {
    "hello": "Hello sir. I am ready for your orders.",
    "systems check": (
        "All systems nominal, sir. 12 minutes on duty, 24 operations handled "
        "with a 96% success rate. I currently hold 5 learned skills and "
        "3 remembered facts about you. Local models responding normally."
    ),
    "system info": "CPU at 24%, memory at 41%, battery at 87% and charging.",
    "what did you learn": "I have learned 5 commands so far, sir.",
}


class KiraService:
    """Backend-facing half of the web UI: routing, telemetry, no HTTP."""

    def __init__(self, simulate: bool = False, ui_dir: "Path | None" = None):
        self.ui_dir = Path(ui_dir) if ui_dir else UI_DIR
        self.simulate = bool(simulate)
        self.backend = None
        self.reason = ""
        self.state = "READY"
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._pending = None          # command awaiting confirmation
        self._error_until = 0.0       # keep the HUD in FAULT until this time
        self._proactive: "queue.Queue" = queue.Queue()
        self._history: list = []
        self._watchdog = None
        self._load_backend()

    # ── setup ────────────────────────────────────────────────────────────

    def _load_backend(self):
        # --simulate is a pure demo: never touch the real agent (or its deps)
        if self.simulate:
            self.backend = None
            self.reason = ""
            return
        try:
            import kira_voice_agent  # noqa: F401  (import side effects matter)

            self.backend = kira_voice_agent
        except Exception as exc:  # missing deps, wrong platform, broken install
            self.backend = None
            self.reason = f"{type(exc).__name__}: {exc}"

    @property
    def online(self) -> bool:
        return self.backend is not None or self.simulate

    @property
    def mode(self) -> str:
        if self.simulate:
            return "simulation"
        return "live" if self.backend is not None else "offline"

    @property
    def version(self) -> str:
        if self.simulate:
            return "sim"
        if self.backend is not None:
            return str(getattr(self.backend, "VERSION", "?"))
        return "sim"

    def start_background(self) -> None:
        """Start KIRA's watchdog so alerts land in the web conversation."""
        if self.backend is None or self.simulate:
            return
        try:
            config = self.backend.CONFIG.get("monitor", {})
            watch = getattr(self.backend, "kira_monitor", None)
            sampler = getattr(self.backend, "_sample_suit_telemetry", None)
            if watch is None or sampler is None:
                return
            language = str(
                (self.backend.USER_MEMORY or {}).get("language", "en") or "en"
            )
            self._watchdog = watch.start(
                sampler=sampler,
                on_alert=self.push_proactive,
                config=config,
                language=language,
            )
        except Exception:
            self._watchdog = None

    # ── conversation plumbing ────────────────────────────────────────────

    def _record(self, role: str, text: str, kind: str = "message") -> dict:
        entry = {
            "role": role,
            "text": text,
            "kind": kind,
            "time": time.strftime("%H:%M"),
            "stamp": time.time(),
        }
        with self._lock:
            self._history.append(entry)
            del self._history[:-200]
        return entry

    def push_proactive(self, text: str) -> None:
        """Queue an unprompted line (watchdog alert, reminder) for the page."""
        text = str(text or "").strip()
        if not text:
            return
        self._record("kira", text, "proactive")
        self._proactive.put(text)

    def drain_proactive(self) -> list:
        drained = []
        while True:
            try:
                drained.append(self._proactive.get_nowait())
            except queue.Empty:
                break
        return drained

    def history(self, limit: int = 30) -> list:
        with self._lock:
            return list(self._history)[-max(1, int(limit)):]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    # ── commands ─────────────────────────────────────────────────────────

    def handle_command(self, text: str, confirm: bool = False,
                       cancel: bool = False) -> dict:
        """Route one command exactly like the CLI and desktop UI do."""
        text = str(text or "").strip()

        # Answering the question: "cancel" disarms it for good, "confirm" runs
        # it. The swap is locked so two clicks cannot execute it twice.
        if cancel:
            with self._lock:
                pending, self._pending = self._pending, None
            if pending is None:
                return {"reply": "", "kind": "empty", "state": self.state}
            reply = "Cancelled, sir."
            self._record("kira", reply, "cancelled")
            self.state = "READY"
            return {"reply": reply, "kind": "cancelled", "state": "READY",
                    "mode": self.mode}

        pending = None
        if confirm:
            with self._lock:
                pending, self._pending = self._pending, None
            if pending is not None:
                text = pending["text"]

        if not text:
            return {"reply": "", "kind": "empty", "state": self.state}

        if pending is None:
            # A new order abandons whatever question was waiting: without
            # this, ignoring a confirmation and later clicking CONFIRM would
            # run a command the user had moved on from.
            with self._lock:
                self._pending = None
            self._record("you", text)

        self.state = "EXECUTING" if pending is not None else "THINKING"
        try:
            if pending is not None:
                result = self._execute(pending)
            elif self.simulate:
                result = self._simulate(text)
            elif self.backend is None:
                result = {
                    "reply": (
                        "I can't reach my local brain right now, sir — "
                        f"{self.reason}"
                    ),
                    "kind": "error",
                }
            else:
                result = self._route(text)
        except Exception as exc:
            traceback.print_exc()
            result = {
                "reply": f"Something went wrong handling that, sir: {exc}",
                "kind": "error",
            }

        reply = str(result.get("reply") or "")
        kind = result.get("kind", "reply")
        if reply:
            self._record("kira", reply, kind)

        if kind == "error":
            # the HUD shows FAULT while this lasts, then returns to standby
            self.state = "ERROR"
            self._error_until = time.time() + ERROR_LINGER
        else:
            self.state = str(result.get("state") or "READY")

        payload = dict(result)
        payload.setdefault("reply", reply)
        payload["mode"] = self.mode
        return payload

    def _route(self, text: str) -> dict:
        backend = self.backend
        cleaned = backend.normalize_command(text)
        if not cleaned:
            return {"reply": "", "kind": "empty"}

        # the locked lab gates everything until it is unlocked
        gate = backend.lab_gate(cleaned)
        if gate is not None:
            return {"reply": gate, "kind": "security"}

        result = backend.parse_simple_command(cleaned)
        planned_by = "parser"
        thought = None

        if result is None and backend.is_chat_question(cleaned):
            return {"reply": backend.ask_chat(cleaned), "kind": "chat"}

        if result is None:
            thought = backend.think_about(cleaned)
            result = thought.action
            planned_by = thought.source

        action = (result or {}).get("action", "none")

        # Chat-session controls never reach execute_action on the desktop
        # either (main_window handles them in its own router) — without this
        # the browser would answer "I could not do that" to all of them.
        control = self._control_reply(action, thought)
        if control is not None:
            return control

        if action == "none":
            return {"reply": backend.ask_chat(cleaned), "kind": "chat"}

        if backend.requires_confirmation(action):
            # The browser cannot answer KIRA's spoken prompt, so the question
            # goes to the page. This applies to plans the model made as well:
            # the whitelist contains sensitive actions (search, click, lock),
            # and the desktop confirms those whichever layer planned them.
            thought_text = getattr(thought, "text", "") if thought else ""
            with self._lock:
                self._pending = {
                    "text": cleaned,
                    "action": result,
                    "source": planned_by,
                    "thought": thought_text,
                }
            return {
                "reply": backend.describe_action(result),
                "kind": "confirm",
                "needs_confirmation": True,
                "action_name": action,
                "state": "CONFIRM",
            }

        return self._execute(
            {"text": cleaned, "action": result, "source": planned_by},
            thought=thought,
        )

    def _control_reply(self, action: str, thought) -> "dict | None":
        """Reply to the session controls the desktop handles outside execute."""
        backend = self.backend
        if action == "conversation_on":
            backend._CONVERSATION_MODE = True
            return {"reply": "Conversation mode is on.", "kind": "action",
                    "action": action, "ok": True, "state": "LISTENING"}
        if action == "conversation_off":
            backend._CONVERSATION_MODE = False
            return {"reply": "Conversation mode is off.", "kind": "action",
                    "action": action, "ok": True}
        if action == "chat_reset":
            backend.reset_chat()
            return {"reply": "New conversation started.", "kind": "action",
                    "action": action, "ok": True}
        if action == "mode_info":
            return {"reply": "Unified mode is active.", "kind": "action",
                    "action": action, "ok": True}
        if action == "exit":
            # the desktop quits here; a browser tab must not kill the server
            return {"reply": "Goodbye sir. I'll be here when you come back.",
                    "kind": "action", "action": action, "ok": True}
        return None

    def _execute(self, pending: dict, thought=None) -> dict:
        backend = self.backend
        result = pending["action"]
        source = pending.get("source", "parser")
        action = (result or {}).get("action", "none")
        language = backend.detect_language(pending["text"])

        success = backend.execute_action(result)
        promotion = None
        if source in {"llm", "memory"}:
            backend._LAST_COMMAND = pending["text"]
            backend._LAST_ACTION = result
            promotion = backend.learn_from(
                pending["text"], result, source, bool(success), language=language
            )
        if success:
            backend.kira_learning.capture(result)
            backend.kira_undo.record(pending["text"], result)

        # An action that returns a string speaks for itself (time, date,
        # information, calculations, reminders…). An *empty* string is a
        # failure, not a silent success — the CLI reads it the same way.
        if isinstance(success, str) and success:
            reply = success
        elif not success:
            reply = backend.build_reply(language, "none")
        else:
            target = ""
            if action in {"open_app", "open_url", "open_folder", "press"}:
                target = str(result.get("target", ""))
            elif action == "search":
                target = str(result.get("query", ""))
            reply = backend.build_reply(language, action, target)

        if promotion:
            reply = f"{reply} {promotion}".strip()

        payload = {
            "reply": reply,
            "kind": "action",
            "action": action,
            "ok": bool(success),
        }
        # the thought may come from the live pass or, after a confirmation,
        # from the question that was waiting for an answer
        thought_text = getattr(thought, "text", "") if thought is not None else ""
        thought_text = thought_text or str(pending.get("thought") or "")
        if thought_text:
            payload["thought"] = thought_text
        return payload

    def _simulate(self, text: str) -> dict:
        lowered = text.lower().strip()
        state = "READY"
        if lowered in {"exit", "quit", "goodbye"}:
            return {"reply": "Goodbye sir.", "kind": "action", "action": "exit"}
        for key, reply in SIMULATED.items():
            if key in lowered:
                return {"reply": reply, "kind": "action", "action": "message"}
        for trigger, action in (
            ("open", "open_app"), ("search", "search"), ("volume", "volume_up"),
            ("type ", "type"), ("screenshot", "screenshot"), ("mute", "mute"),
        ):
            if trigger in lowered:
                return {
                    "reply": f"(simulation) I would {trigger.strip()} for you, sir.",
                    "kind": "action",
                    "action": action,
                    "state": state,
                }
        return {
            "reply": (
                "(simulation) I hear you, sir: \"" + text + "\". Start the server "
                "without --simulate on your own machine and I'll really do it."
            ),
            "kind": "chat",
        }

    # ── voice input ──────────────────────────────────────────────────────

    def listen(self, timeout: int = 6) -> dict:
        if self.simulate:
            return {"text": "systems check", "simulated": True}
        if self.backend is None:
            return {"text": "", "error": self.reason}
        try:
            heard = self.backend.listen_for_command(timeout=timeout, phrase_timeout=4)
        except Exception as exc:
            return {"text": "", "error": f"{type(exc).__name__}: {exc}"}
        return {"text": heard or ""}

    # ── telemetry ────────────────────────────────────────────────────────

    def telemetry(self) -> dict:
        # a FAILED command lingers as ERROR so the HUD can show FAULT
        if self.state == "ERROR" and time.time() >= self._error_until:
            self.state = "READY"

        data = {
            "online": self.online,
            "mode": self.mode,
            "reason": self.reason,
            "state": self.state,
            "version": self.version,
            "model": "—",
            "cpu": None,
            "memory": None,
            "disk": None,
            "battery": None,
            "skills": None,
            "episodes": None,
            "memory_db": "—",
            "uptime": int(time.time() - self.started_at),
            "queue": self.drain_proactive(),
        }

        if self.backend is not None:
            data["model"] = str(getattr(self.backend, "MODEL", "—"))
            try:
                memory = self.backend.kira_memory
                data["skills"] = memory.learnings_summary()["count"]
                data["episodes"] = memory.episode_counts()["total"]
                facts = memory.load_memories()
                data["memory_db"] = f"{len(facts)} facts"
            except Exception:
                pass

        try:  # psutil is optional; the panel shows "—" without it
            import psutil

            data["cpu"] = round(float(psutil.cpu_percent(interval=None)), 1)
            data["memory"] = round(float(psutil.virtual_memory().percent), 1)
            try:
                usage = psutil.disk_usage(os.path.abspath(os.sep))
                data["disk"] = round(usage.percent, 1)
            except Exception:
                pass
            battery = psutil.sensors_battery()
            if battery is not None:
                data["battery"] = {
                    "percent": round(float(battery.percent), 1),
                    "plugged": bool(battery.power_plugged),
                }
        except Exception:
            pass

        return data


# ── HTTP layer ───────────────────────────────────────────────────────────────


class KiraRequestHandler(BaseHTTPRequestHandler):
    """JSON API + static files. Never validates Host, so previews work."""

    server_version = "KiraWeb"
    protocol_version = "HTTP/1.1"

    # injected by the server
    service: KiraService

    # ── helpers ──────────────────────────────────────────────────────────

    def log_message(self, fmt, *args):  # keep the console readable
        return

    def _send(self, status: int, body: bytes, content_type: str,
              extra: "dict | None" = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Deliberately NO Access-Control-Allow-Origin. The interface is served
        # from this origin, so it needs none — and a wildcard would let any
        # website you visit drive KIRA through your browser.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        # never send X-Frame-Options: the UI is embedded in preview panes
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # the browser navigated away / cancelled a poll — not our problem
            self.close_connection = True

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message, "status": status}, status)

    def _read_json(self) -> dict:
        """Parse a JSON object body, or {} if there is nothing usable.

        Two rules matter for safety, not tidiness:

        * The body is always drained (or the connection is closed), otherwise
          what is left in the socket is read as the *next* request on a
          keep-alive connection.
        * A JSON content type is required. ``application/json`` is not a
          CORS-"simple" type, so browsers preflight it — which means a foreign
          page cannot blind-POST commands here with a form/text body.
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return {}
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            self.close_connection = True  # refuse to read it, do not desync
            return {}
        try:
            raw = self.rfile.read(length)
        except (BrokenPipeError, ConnectionResetError, OSError):
            self.close_connection = True
            return {}

        content_type = (self.headers.get("Content-Type") or "").lower()
        if "json" not in content_type:
            return {}

        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # ── static files ─────────────────────────────────────────────────────

    def _serve_static(self, path: str) -> None:
        relative = path.lstrip("/") or "index.html"
        if relative.endswith("/"):
            relative += "index.html"
        candidate = (self.service.ui_dir / relative).resolve()
        root = self.service.ui_dir.resolve()
        try:
            inside = candidate == root or root in candidate.parents
        except (OSError, ValueError):
            inside = False
        if not inside or not candidate.is_file():
            self._error(404, "not found")
            return
        if (
            candidate.suffix.lower() not in STATIC_EXTENSIONS
            and candidate.name not in STATIC_NAMES
        ):
            self._error(403, "file type not served")
            return
        content_type = mimetypes.guess_type(str(candidate))[0]
        if not content_type:
            content_type = "text/plain" if candidate.name in STATIC_NAMES else "application/octet-stream"
        if content_type.startswith("text/") or content_type.endswith("javascript"):
            content_type += "; charset=utf-8"
        self._send(200, candidate.read_bytes(), content_type)

    # ── routing ──────────────────────────────────────────────────────────

    def do_OPTIONS(self):  # noqa: N802 (http.server naming)
        self._send(204, b"", "text/plain")

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            self._json(self.service.telemetry())
            return
        if path == "/api/history":
            limit = 30
            if "?" in self.path:
                for part in self.path.split("?", 1)[1].split("&"):
                    if part.startswith("limit="):
                        try:
                            limit = int(part.split("=", 1)[1])
                        except ValueError:
                            limit = 30
            self._json({"messages": self.service.history(limit)})
            return
        if path == "/api/health":
            self._json(
                {
                    "ok": True,
                    "online": self.service.online,
                    "mode": self.service.mode,
                    "reason": self.service.reason,
                    "version": self.service.version,
                }
            )
            return
        if path.startswith("/api/"):
            self._error(404, "unknown endpoint")
            return
        self._serve_static(path)

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        payload = self._read_json()
        if path == "/api/command":
            if payload.get("cancel"):
                result = self.service.handle_command("", cancel=True)
            elif payload.get("confirm"):
                result = self.service.handle_command("", confirm=True)
            else:
                result = self.service.handle_command(payload.get("text", ""))
            self._json(result)
            return
        if path == "/api/listen":
            self._json(self.service.listen())
            return
        if path == "/api/reset":
            self.service.clear_history()
            self._json({"ok": True})
            return
        self._error(404, "unknown endpoint")


class KiraWebServer(ThreadingHTTPServer):
    """Threading server: a slow command never blocks telemetry polling."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service: KiraService):
        self.service = service
        handler = type(
            "BoundKiraHandler", (KiraRequestHandler,), {"service": service}
        )
        super().__init__(address, handler)


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                  simulate: bool = False, ui_dir=None) -> KiraWebServer:
    service = KiraService(simulate=simulate, ui_dir=ui_dir)
    return KiraWebServer((host, int(port)), service)


def local_addresses(port: int, host: str = DEFAULT_HOST) -> list:
    """Best-effort list of URLs this server is *actually* reachable at.

    Only addresses the bind covers are returned: advertising LAN URLs for a
    loopback-only server sends people to a URL that cannot connect.
    """
    urls = [f"http://127.0.0.1:{port}"]
    if host in {"127.0.0.1", "localhost", "::1"}:
        return urls
    try:
        import socket

        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            address = info[4][0]
            if ":" in address or address.startswith("127."):
                continue
            url = f"http://{address}:{port}"
            if url not in urls:
                urls.append(url)
    except Exception:
        pass
    return urls


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve KIRA's neural interface in a browser."
    )
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="bind address (use 0.0.0.0 to allow your LAN)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--simulate", action="store_true",
                        help="run a labelled demo responder instead of the agent")
    parser.add_argument("--open", action="store_true", help="open a browser")
    parser.add_argument("--no-watchdog", action="store_true",
                        help="do not start the proactive system watchdog")
    args = parser.parse_args(argv)

    if not (UI_DIR / "index.html").is_file():
        print(f"UI files are missing from {UI_DIR}", file=sys.stderr)
        return 2

    try:
        server = create_server(args.host, args.port, simulate=args.simulate)
    except OSError as exc:
        print(f"Could not bind {args.host}:{args.port} — {exc}", file=sys.stderr)
        return 1

    service = server.service
    banner = [
        "=" * 62,
        "KIRA // NEURAL INTERFACE",
        "=" * 62,
        f"mode      : {service.mode}",
        f"version   : {service.version}",
    ]
    if service.backend is None and not service.simulate:
        banner += [
            f"backend   : unavailable ({service.reason})",
            "            the interface will load, commands will explain why",
        ]
    if not args.no_watchdog:
        service.start_background()
    banner += [
        f"open      : {url}"
        for url in local_addresses(server.server_address[1], args.host)
    ]
    banner += ["press CTRL+C to stop", "=" * 62]
    # flushed on purpose: users launch this from a shortcut with blocked stdout
    print("\n".join(banner), flush=True)

    if args.open:
        threading.Thread(
            target=lambda: webbrowser.open(f"http://127.0.0.1:{server.server_address[1]}"),
            daemon=True,
        ).start()

    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\nKIRA: web interface stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
