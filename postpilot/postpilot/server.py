"""Serveur HTTP local de SOCIA AI (127.0.0.1:8790) — API + interface web."""
from __future__ import annotations

import json
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from . import agent, config, gemini_auth, store
from .scheduler import Scheduler, next_run_label

# moteur de publication : placé par run.py / launch_desktop.py
RUNNER = agent.run_task
_scheduler: Scheduler | None = None


def scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler(RUNNER)
    return _scheduler


def _tasks_view() -> list[dict]:
    out = []
    for t in store.tasks():
        t = dict(t)
        t["next_run"] = next_run_label(scheduler(), t)
        out.append(t)
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "SOCIA/1.0"

    # ── utilitaires ────────────────────────────────────────────────────
    def log_message(self, fmt, *args):      # pas de bruit console
        pass

    def _send(self, code: int, payload, content_type: str = "application/json",
              extra_headers: dict | None = None):
        body = (payload if isinstance(payload, bytes)
                else json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    # ── GET ─────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/" or path == "/index.html":
                return self._file(config.WEB / "index.html")
            if path.startswith("/assets/"):
                return self._file(config.WEB / "assets" / path[len("/assets/"):])
            # fichiers statiques de l'interface (style.css, app.js, …)
            name = path.lstrip("/")
            if name in ("style.css", "app.js") or name.endswith(
                    (".css", ".js", ".png", ".ico", ".svg", ".woff2")):
                if ".." not in name:
                    return self._file(config.WEB / name)

            if path == "/api/state":
                data = agent.global_state()
                data.update({
                    "tasks": _tasks_view(),
                    "journal": store.journal(120),
                    "scheduler": scheduler().status(),
                    "link_errors": store.link_errors(),
                    "blacklist": store.blacklist(),
                })
                return self._send(200, data)
            if path == "/api/journal":
                return self._send(200, {"journal": store.journal(200)})
            if path == "/api/accounts":
                return self._send(200, {"accounts": store.accounts()})
            if path == "/api/links":
                return self._send(200, {"links": store.links()})
            if path == "/api/link-errors":
                return self._send(200, {"link_errors": store.link_errors()})
            if path == "/api/blacklist/export":
                # la liste noire en fichier Excel téléchargé sur le PC
                from . import xlsx as xlsx_mod
                data = xlsx_mod.blacklist_export_xlsx(store.blacklist())
                return self._send(
                    200, data,
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet",
                    {"Content-Disposition": 'attachment; filename='
                                            '"postpilot-liens-bannis.xlsx"'})
            if path == "/api/media":
                return self._send(200, {"media": store.list_media()})
            if path == "/api/settings":
                # état de la connexion Gemini (compte Google, sans clé)
                from . import photo as photo_mod
                st = gemini_auth.status()
                st["model"] = photo_mod.GEMINI_MODEL
                return self._send(200, st)
            if path == "/api/gemini/status":
                return self._send(200, gemini_auth.status())
            if path == "/generated/":       # photos présentables (aperçu)
                return self._send(404, {"error": "nom de fichier manquant"})
            if path.startswith("/generated/"):
                name = path[len("/generated/"):]
                if ".." in name or "/" in name or "\\" in name:
                    return self._send(404, {"error": "nom invalide"})
                return self._file(config.GENERATED / name)
            if path == "/api/screen":
                from . import browser
                platform = (parse_qs(parsed.query).get("platform") or [""])[0] \
                    .strip().lower()
                fr = browser.frame(platform)
                if not fr:
                    return self._send(404, {"ok": False,
                                            "message": "fenêtre fermée"})
                return self._send(200, fr["img"], "image/jpeg",
                                  {"X-Screen-Ts": str(fr.get("ts", "")),
                                   "X-Screen-Url": fr.get("url", "")})
            if path == "/api/tasks":
                return self._send(200, {"tasks": _tasks_view()})
            if path == "/api/parse":
                from .commands import parse_command
                text = (parse_qs(parsed.query).get("q") or [""])[0]
                return self._send(200, parse_command(text))
            return self._send(404, {"error": "inconnu"})
        except Exception:
            store.log("Erreur serveur GET :\n" + traceback.format_exc(limit=3),
                      level="error", source="serveur")
            return self._send(500, {"error": "erreur interne"})

    def _file(self, path):
        try:
            data = path.read_bytes()
        except OSError:
            return self._send(404, {"error": "fichier introuvable"})
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return self._send(200, data, ctype)

    # ── POST ────────────────────────────────────────────────────────────
    def _upload_media(self):
        """POST brut (fichier binaire) — nom passé dans l'en-tête X-File-Name."""
        try:
            name = self.headers.get("X-File-Name") or ""
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length) if length > 0 else b""
            saved, err = store.save_media(name, data)
            if err:
                return self._send(400, {"ok": False, "message": err})
            return self._send(200, {"ok": True, "name": saved,
                                    "message": f"Média inséré : {saved}"})
        except Exception:
            store.log("Erreur serveur (envoi de média) :\n"
                      + traceback.format_exc(limit=3),
                      level="error", source="serveur")
            return self._send(500, {"ok": False, "message": "Écriture impossible"})

    def _upload_client_secret(self):
        """POST brut — fichier client_secret.json de Google (binaire)."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length) if length > 0 else b""
            if not data:
                return self._send(400, {"ok": False,
                                        "message": "Aucun fichier reçu"})
            ok, msg = gemini_auth.save_client_secret(data)
            return self._send(200 if ok else 400, {"ok": ok, "message": msg})
        except Exception:
            store.log("Erreur serveur (fichier Google) :\n"
                      + traceback.format_exc(limit=3),
                      level="error", source="serveur")
            return self._send(500, {"ok": False,
                                    "message": "Écriture impossible"})

    def _import_links_file(self):
        """POST brut (fichier Excel binaire) — nom dans X-File-Name."""
        try:
            name = unquote(self.headers.get("X-File-Name") or "")
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return self._send(400, {"ok": False,
                                        "message": "Aucun fichier reçu"})
            if length > 20 * 1024 * 1024:
                return self._send(400, {"ok": False,
                                        "message": "Fichier trop volumineux "
                                                   "(20 Mo maximum)"})
            data = self.rfile.read(length)
            res = agent.import_links_file(name, data)
            code = 200 if res.get("ok") else 400
            return self._send(code, res)
        except Exception:
            store.log("Erreur serveur (import de fichier Excel) :\n"
                      + traceback.format_exc(limit=3),
                      level="error", source="serveur")
            return self._send(500, {"ok": False,
                                    "message": "Import impossible"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/media":        # corps binaire : à traiter AVANT _json()
            return self._upload_media()
        if path == "/api/gemini/client-secret":   # fichier Google (binaire)
            return self._upload_client_secret()
        if path == "/api/links/import-file":   # idem : fichier Excel en binaire
            return self._import_links_file()
        body = self._json()
        try:
            if path == "/api/gemini/connect":
                # ouvre la fenêtre de connexion Google (e-mail) — sans clé
                return self._send(200, gemini_auth.connect_start())

            if path == "/api/gemini/disconnect":
                return self._send(200, gemini_auth.disconnect())

            if path == "/api/gemini/generate":
                # génère des photos Gemini à partir de la photo brute —
                # pour construire la liste VALIDÉE avant de lancer une tâche
                import time as _t
                from . import photo as photo_mod
                name = (body.get("media") or "").strip()
                src = config.MEDIA / name if name else None
                if not name or src is None or not src.exists():
                    return self._send(400, {"ok": False,
                                            "message": "Photo brute introuvable — "
                                                       "insérez-la d'abord (bouton +)"})
                if not photo_mod.is_image(src):
                    return self._send(400, {"ok": False,
                                            "message": "Ce fichier n'est pas une "
                                                       "image (photo brute attendue)"})
                try:
                    count = max(1, min(6, int(body.get("count") or 1)))
                except (TypeError, ValueError):
                    count = 1
                t0 = _t.time()
                try:
                    outs = photo_mod.generate(src, count=count)
                except photo_mod.GeminiError as exc:
                    store.log(f"Génération refusée : {exc}", level="warn",
                              source="photo")
                    return self._send(503, {"ok": False, "message": str(exc)})
                secs = round(_t.time() - t0, 1)
                store.log(f"✨ {len(outs)} photo(s) Gemini générée(s) en "
                          f"{secs} s pour « {name} ».", source="photo")
                return self._send(200, {
                    "ok": True, "model": photo_mod.GEMINI_MODEL,
                    "seconds": secs,
                    "photos": [{"name": p.name, "url": f"/generated/{p.name}"}
                               for p in outs],
                    "message": f"{len(outs)} photo(s) Gemini en {secs} s — "
                               "retirez celles que vous ne voulez pas (X), "
                               "puis lancez la tâche.",
                })
            if path == "/api/accounts":
                res = agent.register_account(
                    (body.get("platform") or "").strip().lower(),
                    body.get("profile_url") or "",
                    body.get("label") or "",
                    visible=True)          # l'utilisateur va s'y connecter
                return self._send(200, res)

            if path == "/api/accounts/verify":
                res = agent.verify_account((body.get("platform") or "").lower())
                return self._send(200, res)

            if path == "/api/accounts/forget":
                res = agent.forget_account((body.get("platform") or "").lower())
                return self._send(200, res)

            if path == "/api/links":
                res = agent.add_link(body.get("url") or "",
                                     (body.get("platform") or "facebook").lower())
                return self._send(200, res)

            if path == "/api/links/delete":
                res = agent.delete_link(body.get("id") or "")
                return self._send(200, res)

            if path == "/api/links/select":
                res = agent.select_links(body.get("ids") or [])
                return self._send(200, res)

            if path == "/api/links/import":
                res = agent.start_import()
                return self._send(200, res)

            if path == "/api/link-errors/clear":
                store.clear_link_errors()
                return self._send(200, {"ok": True,
                                        "message": "Liste vidée"})

            if path == "/api/link-errors/blacklist":
                # poubelle : erreur supprimée + lien mis en liste noire
                res = agent.blacklist_link_error(body.get("url") or "")
                return self._send(200, res)

            if path == "/api/blacklist/remove":
                res = agent.unblacklist(body.get("url") or "")
                return self._send(200, res)

            if path == "/api/tasks":
                res = agent.create_task_from_command(body.get("command") or "",
                                                     body)
                return self._send(200, res)

            if path == "/api/tasks/run":
                task = next((t for t in store.tasks()
                             if t.get("id") == body.get("id")), None)
                if task is None:
                    return self._send(404, {"ok": False, "message": "tâche inconnue"})
                scheduler().trigger(task)
                return self._send(200, {"ok": True,
                                        "message": "Exécution lancée (fenêtre visible)"})

            if path == "/api/tasks/update":
                res = agent.update_task_fields(body.get("id") or "", body)
                if res.get("ok"):
                    # la nouvelle fréquence s'applique dès maintenant
                    scheduler().reschedule(body.get("id") or "")
                code = 200 if res.get("ok") else 400
                return self._send(code, res)

            if path == "/api/tasks/toggle":
                task = next((t for t in store.tasks()
                             if t.get("id") == body.get("id")), None)
                if task is None:
                    return self._send(404, {"ok": False, "message": "tâche inconnue"})
                if task.get("enabled"):
                    # pause = arrêt IMMÉDIAT du travail en cours, sans finir
                    store.request_cancel(task["id"])
                    store.update_task(task["id"], enabled=False)
                    return self._send(200, {"ok": True,
                                            "message": "Tâche mise en pause — "
                                                     "travail en cours arrêté"})
                store.clear_cancel(task["id"])
                store.update_task(task["id"], enabled=True)
                scheduler().reschedule(task["id"])
                return self._send(200, {"ok": True,
                                        "message": "Tâche relancée"})

            if path == "/api/tasks/delete":
                # supprimer = arrêter le travail en cours tout de suite aussi
                store.request_cancel(body.get("id") or "")
                ok = store.remove_task(body.get("id") or "")
                return self._send(200, {"ok": ok, "message": "Tâche supprimée — "
                                        "travail en cours arrêté" if ok
                                        else "Tâche introuvable"})

            if path == "/api/window/open":
                platform = (body.get("platform") or "").lower()
                # l'utilisateur demande à VOIR la fenêtre (connexion) :
                # elle s'ouvre visible — sinon les ouvertures de l'agent sont
                # en arrière-plan et se suivent dans l'aperçu de l'interface
                visible = bool(body.get("visible"))
                # pas d'URL fournie → on ouvre sur la page d'accueil du réseau
                url = body.get("profile_url") or config.HOME_URLS.get(platform, "")
                res = agent.register_account(platform, url,
                                              body.get("label") or "",
                                              visible=visible)
                return self._send(200, res)

            if path == "/api/window/close":
                from . import browser
                ok = browser.close_window((body.get("platform") or "").lower())
                return self._send(200, {"ok": ok, "message": "Fenêtre fermée"})

            return self._send(404, {"error": "inconnu"})
        except Exception:
            store.log("Erreur serveur POST :\n" + traceback.format_exc(limit=3),
                      level="error", source="serveur")
            return self._send(500, {"error": "erreur interne"})


def serve(host: str = config.HOST, port: int = config.PORT, with_scheduler: bool = True):
    """Démarre le serveur (bloquant). Le planificateur tourne à côté."""
    config.ensure_dirs()
    if with_scheduler:
        scheduler().start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    store.log(f"SOCIA AI en écoute sur http://{host}:{port}", source="serveur")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler().stop()
        httpd.server_close()
