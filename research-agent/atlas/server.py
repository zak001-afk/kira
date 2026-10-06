"""Serveur local d'Atlas : interface web + API de recherche en flux NDJSON.

Endpoints :
  GET  /                 -> interface de chat (web/)
  GET  /api/status       -> état du cerveau et du moteur de recherche
  POST /api/research     -> {message, history} -> flux NDJSON d'événements
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .agent import research_events
from .config import WEB_DIR, Config

_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
}
_MAX_BODY = 256 * 1024  # 256 Ko de requête suffisent largement


class AtlasHandler(BaseHTTPRequestHandler):
    cfg: Config  # injecté par serve()

    # -- utilitaires ------------------------------------------------------
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, rel: str) -> None:
        rel = rel.lstrip("/") or "index.html"
        target = (WEB_DIR / rel).resolve()
        try:
            target.relative_to(WEB_DIR.resolve())
        except ValueError:
            self._send_json({"error": "not found"}, 404)
            return
        if not target.is_file():
            # Toute route inconnue renvoie l'application (interface mono-page).
            target = WEB_DIR / "index.html"
        data = target.read_bytes()
        ctype = _TYPES.get(target.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # -- routes -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 (API http.server)
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            self._send_json({
                "ok": True,
                "name": self.cfg.name,
                "brain": self.cfg.status_label,
                "kind": self.cfg.kind,
                "search": "DuckDuckGo (sans clé API)",
                "max_pages": self.cfg.max_pages,
            })
        else:
            self._send_static(path)

    def do_POST(self) -> None:  # noqa: N802 (API http.server)
        path = self.path.split("?", 1)[0]
        if path != "/api/research":
            self._send_json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > _MAX_BODY:
                raise ValueError("requête vide ou trop volumineuse")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            message = str(payload.get("message") or "").strip()
            if not message:
                raise ValueError("message vide")
            history = payload.get("history") or []
            if not isinstance(history, list):
                history = []
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, 400)
            return

        # Flux NDJSON : chaque événement sur sa ligne, écrit au fil de l'eau.
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for event in research_events(self.cfg, message, history):
                line = json.dumps(event, ensure_ascii=False) + "\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return  # l'utilisateur a fermé l'onglet pendant la recherche

    def log_message(self, fmt: str, *args) -> None:
        if getattr(self.cfg, "verbose", False):
            super().log_message(fmt, *args)


def serve(cfg: Config, host: str = "127.0.0.1", port: int = 8787) -> None:
    """Démarre le serveur (boucle bloquante, Ctrl+C pour arrêter)."""
    handler = type("Handler", (AtlasHandler,), {"cfg": cfg})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    print(f"Atlas prêt sur http://{host}:{port}  (Ctrl+C pour arrêter)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt d'Atlas.")
    finally:
        httpd.server_close()
