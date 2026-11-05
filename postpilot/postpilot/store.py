"""Persistance JSON : comptes connectés, tâches programmées, journal.

Chaque fichier vit dans E:\\socia-ai\\data — rien n'est partagé avec KIRA.
"""
from __future__ import annotations

import datetime as dt
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from . import config

_lock = threading.RLock()


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# ── Journal ────────────────────────────────────────────────────────────────
def log(message: str, level: str = "info", source: str = "socia") -> dict:
    """Ajoute une ligne au journal (affiché dans l'interface)."""
    entry = {"ts": now_iso(), "level": level, "source": source, "message": message}
    with _lock:
        entries = config.load_json(config.JOURNAL_FILE, [])
        entries.append(entry)
        entries = entries[-800:]          # journal borné
        config.save_json(config.JOURNAL_FILE, entries)
    return entry


def journal(limit: int = 200) -> list[dict]:
    with _lock:
        return config.load_json(config.JOURNAL_FILE, [])[-limit:]


# ── Comptes ────────────────────────────────────────────────────────────────
def accounts() -> list[dict]:
    with _lock:
        return config.load_json(config.ACCOUNTS_FILE, [])


def save_accounts(items: list[dict]) -> None:
    with _lock:
        config.save_json(config.ACCOUNTS_FILE, items)


def account_for(platform: str) -> dict | None:
    for a in accounts():
        if a.get("platform") == platform and a.get("status") == "connected":
            return a
    return None


def upsert_account(platform: str, profile_url: str, label: str = "",
                   status: str = "pending") -> dict:
    """Enregistre / met à jour le compte d'une plateforme."""
    with _lock:
        items = config.load_json(config.ACCOUNTS_FILE, [])
        for it in items:
            if it.get("platform") == platform:
                it.update({"profile_url": profile_url, "status": status,
                           "updated_at": now_iso()})
                if label:
                    it["label"] = label
                config.save_json(config.ACCOUNTS_FILE, items)
                log(f"Compte {platform} mis à jour : {profile_url}", source="comptes")
                return it
        item = {
            "id": uuid.uuid4().hex[:8],
            "platform": platform,
            "profile_url": profile_url,
            "label": label or profile_url,
            "status": status,             # pending | connected | error
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        items.append(item)
        config.save_json(config.ACCOUNTS_FILE, items)
        log(f"Nouveau compte {platform} : {profile_url}", source="comptes")
        return item


def set_account_status(platform: str, status: str, label: str = "") -> None:
    with _lock:
        items = config.load_json(config.ACCOUNTS_FILE, [])
        for it in items:
            if it.get("platform") == platform:
                it["status"] = status
                it["updated_at"] = now_iso()
                if label:
                    it["label"] = label
        config.save_json(config.ACCOUNTS_FILE, items)


def remove_account(platform: str) -> bool:
    with _lock:
        items = config.load_json(config.ACCOUNTS_FILE, [])
        kept = [i for i in items if i.get("platform") != platform]
        changed = len(kept) != len(items)
        config.save_json(config.ACCOUNTS_FILE, kept)
        if changed:
            log(f"Compte {platform} déconnecté/supprimé.", source="comptes")
        return changed


# ── Médias (photos & vidéos insérés depuis l'interface) ──────────────────────
MEDIA_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif", ".heic", ".heif",
    ".mp4", ".mov", ".webm", ".mkv", ".avi", ".wmv", ".flv", ".3gp", ".m4v",
}


def save_media(filename: str, data: bytes) -> tuple[str | None, str | None]:
    """Écrit un fichier choisi par l'utilisateur dans data/media.

    Retourne ``(nom_enregistré, None)`` ou ``(None, message d'erreur)``.
    Le nom est réduit à son dernier segment (aucun chemin) et son extension
    doit être une image ou une vidéo connue.
    """
    name = Path((filename or "").replace("\\", "/")).name.strip()
    name = re.sub(r"[^\w. ()\-]+", "_", name, flags=re.UNICODE).strip(". ")
    if not name:
        return None, "Nom de fichier vide"
    ext = Path(name).suffix.lower()
    if ext not in MEDIA_EXTS:
        return None, (f"Format non pris en charge : {ext or '(sans extension)'} — "
                      "images (jpg, png, gif, webp, heic…) ou vidéos "
                      "(mp4, mov, avi, webm…)")
    if not data:
        return None, "Fichier vide"
    target = config.MEDIA / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    log(f"Média inséré : {name} ({len(data) // 1024} ko)", source="médias")
    return name, None


def list_media() -> list[dict]:
    """Médias présents dans data/media (nom, taille)."""
    out = []
    try:
        for p in sorted(config.MEDIA.iterdir()):
            if p.is_file() and p.suffix.lower() in MEDIA_EXTS:
                out.append({"name": p.name, "size": p.stat().st_size})
    except OSError:
        pass
    return out


# ── Liens enregistrés (pages & groupes) ─────────────────────────────────────
def links(platform: str | None = None) -> list[dict]:
    """Liens enregistrés dans la base (optionnellement filtrés par réseau)."""
    with _lock:
        items = config.load_json(config.LINKS_FILE, [])
    if platform:
        return [i for i in items if i.get("platform") == platform]
    return items


def save_links(items: list[dict]) -> None:
    with _lock:
        config.save_json(config.LINKS_FILE, items)


def add_link(url: str, platform: str = "facebook") -> tuple[dict, bool]:
    """Ajoute un lien à la base. Retourne (lien, True si réellement ajouté).

    Un lien déjà présent (même URL normalisée) n'est pas dupliqué : on
    retourne l'existant avec False.
    """
    with _lock:
        items = config.load_json(config.LINKS_FILE, [])
        for it in items:
            if it.get("platform") == platform and it.get("url") == url:
                return it, False
        item = {
            "id": uuid.uuid4().hex[:8],
            "platform": platform,
            "url": url,
            "selected": False,          # l'utilisateur coche lui-même ses cibles
            "created_at": now_iso(),
        }
        items.append(item)
        config.save_json(config.LINKS_FILE, items)
    log(f"Lien ajouté à la base : {url}", source="cibles")
    return item, True


def add_links_bulk(urls: list[str], platform: str = "facebook") -> tuple[list[dict], int]:
    """Ajoute plusieurs liens en UNE seule écriture (import de fichier Excel).

    Sans limite de nombre : 10 ou 10 000 liens passent par la même
    écriture atomique. Retourne (liens ajoutés, nb de doublons ignorés).
    """
    with _lock:
        items = config.load_json(config.LINKS_FILE, [])
        known = {it.get("url") for it in items if it.get("platform") == platform}
        added: list[dict] = []
        dupes = 0
        for url in urls:
            if url in known:
                dupes += 1
                continue
            known.add(url)
            item = {
                "id": uuid.uuid4().hex[:8],
                "platform": platform,
                "url": url,
                "selected": False,
                "created_at": now_iso(),
            }
            items.append(item)
            added.append(item)
        if added:
            config.save_json(config.LINKS_FILE, items)
    if added:
        log(f"{len(added)} lien(s) ajouté(s) à la base "
            f"({dupes} doublon(s) ignoré(s)).", source="cibles")
    return added, dupes


def remove_link(link_id: str) -> bool:
    """Supprime un lien de la liste (bouton X)."""
    with _lock:
        items = config.load_json(config.LINKS_FILE, [])
        kept = [i for i in items if i.get("id") != link_id]
        changed = len(kept) != len(items)
        if changed:
            config.save_json(config.LINKS_FILE, kept)
    if changed:
        url = next((i.get("url") for i in items if i.get("id") == link_id), "")
        log(f"Lien supprimé de la liste : {url}", source="cibles")
    return changed


def set_link_selection(ids: list[str]) -> list[dict]:
    """Recoche / décoque les liens (la liste cochée = les cibles de publication)."""
    wanted = set(ids)
    with _lock:
        items = config.load_json(config.LINKS_FILE, [])
        for it in items:
            it["selected"] = it.get("id") in wanted
        config.save_json(config.LINKS_FILE, items)
    return items


def selected_links(platform: str = "facebook") -> list[dict]:
    return [i for i in links(platform) if i.get("selected")]


# ── Liens en difficulté / erreur (l'agent ne se bloque JAMAIS) ─────────────
def link_errors() -> list[dict]:
    """Liens sur lesquels la dernière publication a échoué (url, message, ts).

    Persistés sur le disque : la liste reste visible même après un
    redémarrage. Un lien qui réussit ensuite en est retiré.
    """
    with _lock:
        return config.load_json(config.LINK_ERRORS_FILE, [])


def add_link_error(url: str, message: str) -> dict:
    """Enregistre / met à jour la difficulté d'un lien (upsert par URL)."""
    entry = {"url": url, "message": (message or "erreur inconnue")[:300],
             "ts": now_iso()}
    with _lock:
        items = [i for i in config.load_json(config.LINK_ERRORS_FILE, [])
                 if i.get("url") != url]
        items.append(entry)
        items = items[-300:]              # liste bornée
        config.save_json(config.LINK_ERRORS_FILE, items)
    return entry


def forget_link_error(url: str) -> bool:
    """Retire un lien de la liste des difficultés (il a fini par réussir)."""
    with _lock:
        items = config.load_json(config.LINK_ERRORS_FILE, [])
        kept = [i for i in items if i.get("url") != url]
        changed = len(kept) != len(items)
        if changed:
            config.save_json(config.LINK_ERRORS_FILE, kept)
    return changed


def clear_link_errors() -> bool:
    with _lock:
        changed = bool(config.load_json(config.LINK_ERRORS_FILE, []))
        if changed:
            config.save_json(config.LINK_ERRORS_FILE, [])
    return changed


# ── Liste noire de liens (bannis : jamais réimportés, jamais republiés) ──
def blacklist() -> list[dict]:
    """Liens bannis par l'utilisateur (url, ts) — persistés sur le disque."""
    with _lock:
        return config.load_json(config.BLACKLIST_FILE, [])


def is_blacklisted(url: str) -> bool:
    with _lock:
        return any(i.get("url") == url
                   for i in config.load_json(config.BLACKLIST_FILE, []))


def add_blacklist(url: str) -> bool:
    """Bannit un lien. Retourne True si réellement ajouté."""
    with _lock:
        items = [i for i in config.load_json(config.BLACKLIST_FILE, [])
                 if i.get("url") != url]
        added = len(items) == len(config.load_json(config.BLACKLIST_FILE, []))
        items.append({"url": url, "ts": now_iso()})
        items = items[-1000:]
        config.save_json(config.BLACKLIST_FILE, items)
    if added:
        log(f"Lien mis en liste noire : {url}", source="cibles")
    return added


def remove_blacklist(url: str) -> bool:
    """Retire un lien de la liste noire (il pourra être réimporté)."""
    with _lock:
        items = config.load_json(config.BLACKLIST_FILE, [])
        kept = [i for i in items if i.get("url") != url]
        changed = len(kept) != len(items)
        if changed:
            config.save_json(config.BLACKLIST_FILE, kept)
    if changed:
        log(f"Lien retiré de la liste noire : {url}", source="cibles")
    return changed


# ── Annulation d'une tâche en cours (pause / supprimer = arrêt immédiat) ─
# ── Réglages (clé Gemini, modèle d'image, …) ─────────────────────────────
def settings() -> dict:
    with _lock:
        data = config.load_json(config.SETTINGS_FILE, {})
    # ensure_dirs initialise tous les fichiers en « [] » : un ancien
    # settings.json peut contenir une liste — on tolère pour ne pas casser
    return data if isinstance(data, dict) else {}


def save_settings(values: dict) -> dict:
    """Fusionne `values` dans les réglages persistés (settings.json)."""
    with _lock:
        cur = config.load_json(config.SETTINGS_FILE, {})
        if not isinstance(cur, dict):
            cur = {}
        cur.update(values)
        config.save_json(config.SETTINGS_FILE, cur)
        return cur


# ── Annulation d'une tâche en cours (pause / supprimer = arrêt immédiat) ──
_cancelled: set[str] = set()


def request_cancel(task_id: str) -> None:
    """Demande l'arrêt immédiat du travail en cours de cette tâche."""
    if task_id:
        with _lock:
            _cancelled.add(task_id)


def clear_cancel(task_id: str) -> None:
    if task_id:
        with _lock:
            _cancelled.discard(task_id)


def is_cancelled(task_id: str) -> bool:
    with _lock:
        return bool(task_id) and task_id in _cancelled


# ── Tâches programmées ─────────────────────────────────────────────────────
def tasks() -> list[dict]:
    with _lock:
        return config.load_json(config.TASKS_FILE, [])


def save_tasks(items: list[dict]) -> None:
    with _lock:
        config.save_json(config.TASKS_FILE, items)


def add_task(task: dict) -> dict:
    task = dict(task)
    task.setdefault("id", uuid.uuid4().hex[:8])
    task.setdefault("enabled", True)
    task.setdefault("created_at", now_iso())
    task.setdefault("runs", 0)
    task.setdefault("last_run_at", None)
    task.setdefault("last_status", None)
    with _lock:
        items = config.load_json(config.TASKS_FILE, [])
        items.append(task)
        config.save_json(config.TASKS_FILE, items)
    log(f"Tâche créée : {task.get('summary') or task.get('content', '')[:60]}",
        source="programmation")
    return task


def update_task(task_id: str, **fields: Any) -> dict | None:
    with _lock:
        items = config.load_json(config.TASKS_FILE, [])
        for it in items:
            if it.get("id") == task_id:
                it.update(fields)
                config.save_json(config.TASKS_FILE, items)
                return it
    return None


def remove_task(task_id: str) -> bool:
    with _lock:
        items = config.load_json(config.TASKS_FILE, [])
        kept = [i for i in items if i.get("id") != task_id]
        changed = len(kept) != len(items)
        config.save_json(config.TASKS_FILE, kept)
        if changed:
            log(f"Tâche {task_id} supprimée.", source="programmation")
        return changed
