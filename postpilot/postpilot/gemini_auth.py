"""Connexion au compte Google de l'utilisateur (e-mail) — OAuth officiel.

Plus AUCUNE clé API à coller : PostPilot ouvre la page de connexion
Google, l'utilisateur choisit son e-mail et autorise l'application ; les
jetons restent sur le disque (data/gemini/) et sont rafraîchis seuls.

Préparation UNIQUE (guide pas-à-pas affiché dans l'application) :
1. Google Cloud (console.cloud.google.com) → activer l'API
   « Generative Language API » ;
2. écran de consentement (type Externe) + votre e-mail en test user ;
3. Credentials → Créer un client OAuth → Application de bureau →
   télécharger le fichier JSON ;
4. déposer ce fichier (client_secret*.json) dans PostPilot.

NB : la génération d'images Gemini exige la facturation active sur le
projet Google — règle Google, identique pour toute connexion.
"""
from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

from . import config, store


class GeminiError(RuntimeError):
    """Gemini impossible pour l'instant (pas connecté, facturation,
    quota…). L'agent signale alors clairement et réessaie plus tard."""


# scopes OAuth : accès API Gemini + affichage de l'e-mail de connexion
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
]
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_lock = threading.RLock()          # réentrant : status() est appelé dedans
_state = {"phase": "idle", "message": ""}   # idle | opening | error


def client_file() -> Path:
    return config.GEMINI_DIR / "client_secret.json"


def token_file() -> Path:
    return config.GEMINI_DIR / "token.json"


def _short(exc) -> str:
    return str(exc).strip().splitlines()[0][:170] if str(exc).strip() \
        else exc.__class__.__name__


# ── fichier client_secret.json déposé par l'utilisateur ──────────────────
def save_client_secret(data: bytes) -> tuple[bool, str]:
    """Valide et enregistre le fichier « client_secret » de Google Cloud."""
    try:
        info = json.loads(data.decode("utf-8"))
    except Exception:
        return False, ("Fichier illisible : déposez le fichier JSON "
                       "téléchargé depuis Google Cloud → Credentials.")
    bloc = info.get("installed") or info.get("web") or {}
    if not isinstance(bloc, dict) or not bloc.get("client_id"):
        return False, ("Fichier incorrect : il faut le fichier « "
                       "client_secret_….json » d'un client OAuth de type "
                       "« Application de bureau » (Google Cloud → "
                       "Credentials → Créer des identifiants → Client OAuth).")
    config.GEMINI_DIR.mkdir(parents=True, exist_ok=True)
    client_file().write_text(json.dumps(info, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    project = (bloc.get("project_id") or "").strip()
    if project:
        store.save_settings({"gemini_project": project})
    msg = ("Fichier Google enregistré"
           + (f" (projet : {project})" if project else "")
           + " — cliquez sur « Connecter mon compte Google ».")
    store.log(msg, source="réglages")
    return True, msg


def project_id() -> str:
    return (store.settings().get("gemini_project") or "").strip()


def connected() -> bool:
    return token_file().exists()


def status() -> dict:
    with _lock:
        phase, message = _state["phase"], _state["message"]
    is_connected = connected()
    return {
        "configured": client_file().exists(),
        "connected": is_connected,
        "email": (store.settings().get("gemini_email") or "").strip()
                 if is_connected else "",
        "phase": "connected" if is_connected and phase != "opening" else phase,
        "message": message,
        "project": project_id(),
    }


# ── jetons ────────────────────────────────────────────────────────────────
def credentials():
    """Jetons OAuth valides (rafraîchis automatiquement).

    Lève `GeminiError` avec un message clair si la connexion est absente
    ou expirée — aucun repli silencieux.
    """
    tf = token_file()
    if not tf.exists():
        raise GeminiError("Compte Google non connecté — ouvrez « Connexion "
                          "Gemini » dans PostPilot et cliquez sur « Connecter "
                          "mon compte Google ».")
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(tf), SCOPES)
    except Exception as exc:
        raise GeminiError(f"Connexion Google illisible ({_short(exc)}) — "
                          "reconnectez votre compte depuis PostPilot.") from exc
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        except Exception as exc:
            raise GeminiError(f"Connexion Google expirée ({_short(exc)}) — "
                              "recliquez sur « Connecter mon compte Google »."
                              ) from exc
        try:
            tf.write_text(creds.to_json(), encoding="utf-8")
        except OSError:
            pass                            # vivra tant que le process tourne
        return creds
    raise GeminiError("Connexion Google incomplète — recliquez sur "
                      "« Connecter mon compte Google ».")


# ── connexion (une fenêtre Google s'ouvre, l'utilisateur choisit son mail)
def connect_start() -> dict:
    with _lock:
        if _state["phase"] == "opening":
            st = status()
            st.update(ok=True,
                      message="Connexion déjà en cours — une fenêtre Google "
                              "devrait être ouverte.")
            return st
        if not client_file().exists():
            st = status()
            st.update(ok=False,
                      message="Fichier Google manquant : suivez le guide "
                              "« Première connexion ? » ci-dessous, puis "
                              "déposez votre fichier client_secret.json.")
            return st
        _state.update(phase="opening",
                      message="Fenêtre Google ouverte : choisissez votre "
                              "e-mail…")
    threading.Thread(target=_connect_worker, daemon=True).start()
    st = status()
    st.update(ok=True,
              message="Une fenêtre Google vient de s'ouvrir : connectez-vous "
                      "avec votre e-mail, autorisez PostPilot, puis revenez "
                      "ici — la liaison se termine toute seule.")
    return st


def _connect_worker() -> None:
    """Fil de la fenêtre de connexion (bloquant pendant l'authentification)."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(client_file()),
                                                         SCOPES)
        creds = flow.run_local_server(
            port=0, open_browser=True, access_type="offline",
            prompt="consent",
            authorization_prompt_message=(
                "\n  => PostPilot ouvre la page de connexion Google.\n"
                "  Choisissez votre e-mail puis autorisez l'application.\n\n"
                "  {url}"),
            success_message="✔ Compte connecté ! Vous pouvez fermer cette "
                            "page et revenir dans PostPilot.")
        config.GEMINI_DIR.mkdir(parents=True, exist_ok=True)
        token_file().write_text(creds.to_json(), encoding="utf-8")
        email = _fetch_email(creds)
        if email:
            store.save_settings({"gemini_email": email})
        with _lock:
            _state.update(phase="idle", message="")
        store.log(f"✅ Compte Google connecté"
                  f"{f' ({email})' if email else ''} — les photos Gemini "
                  f"sont actives.", source="gemini")
    except Exception as exc:
        msg = _short(exc)
        store.log(f"Connexion Google impossible : {msg}",
                  level="warn", source="gemini")
        with _lock:
            _state.update(phase="error", message=msg)


def _fetch_email(creds) -> str:
    try:
        req = urllib.request.Request(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {creds.token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return (json.loads(resp.read().decode("utf-8"))
                    .get("email") or "")
    except Exception:
        return ""


def disconnect() -> dict:
    try:
        token_file().unlink(missing_ok=True)
    except OSError:
        pass
    store.save_settings({"gemini_email": ""})
    with _lock:
        _state.update(phase="idle", message="")
    store.log("Compte Google déconnecté.", source="gemini")
    return {"ok": True,
            "message": "Compte Google déconnecté — reconnectez-vous quand "
                       "vous voulez."}
