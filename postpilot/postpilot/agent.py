"""Orchestrateur SOCIA AI : connexion des comptes et exécution des tâches.

C'est la couche « agent » : ce que l'interface et le planificateur appellent.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import browser, commands, config, store
from .platforms import get as platform_module


# ── Liens enregistrés (pages & groupes) ──────────────────────────────────
def _normalize_link(url: str) -> str:
    """Nettoie un lien : https, sans query/fragment, sans « / » final.

    Deux saisies identiques à part « ?fbclid=… » ou « #… » doivent donc
    donner le MÊME lien en base (pas de doublon).
    """
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    path = parts.path.rstrip("/")
    return urlunsplit(("https", host + port, path, "", ""))


def _is_facebook_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return (host == "facebook.com" or host.endswith(".facebook.com")
            or host == "fb.com" or host.endswith(".fb.com"))


def add_link(url: str, platform: str = "facebook") -> dict:
    """Ajoute un lien (page / groupe) à la base de l'utilisateur."""
    if not (url or "").strip():
        return {"ok": False, "message": "Aucun lien saisi"}
    if platform not in config.PLATFORMS:
        return {"ok": False, "message": f"Plateforme inconnue : {platform}"}
    link = _normalize_link(url)
    if store.is_blacklisted(link):
        return {"ok": False,
                "message": "Ce lien est en liste noire — retirez-le de la "
                           "liste noire pour le réutiliser"}
    if platform == "facebook" and not _is_facebook_url(link):
        host = urlsplit(link).hostname or link
        return {"ok": False,
                "message": f"Ce n'est pas un lien Facebook : {host} — attendu "
                           "https://www.facebook.com/groups/… ou "
                           "https://www.facebook.com/page"}
    item, created = store.add_link(link, platform)
    return {"ok": True, "link": item, "links": store.links(),
            "message": ("Lien ajouté à la base — ouvrez la flèche pour le cocher"
                        if created else "Ce lien était déjà dans la base"),
            "created": created}


def delete_link(link_id: str) -> dict:
    ok = store.remove_link(link_id or "")
    return {"ok": ok,
            "message": "Lien supprimé de la liste" if ok else "Lien introuvable",
            "links": store.links()}


def select_links(ids: list[str]) -> dict:
    items = store.set_link_selection([str(i) for i in (ids or [])])
    n = sum(1 for i in items if i.get("selected"))
    return {"ok": True, "links": items,
            "message": f"{n} cible(s) cochée(s) sur {len(items)}"}


def selected_link_urls(platform: str = "facebook") -> list[str]:
    return [i.get("url") for i in store.selected_links(platform) if i.get("url")]


def _detect_platform(url: str) -> str | None:
    """facebook / instagram / tiktok selon l'hôte, sinon None."""
    host = (urlsplit(url).hostname or "").lower()
    if (host == "facebook.com" or host.endswith(".facebook.com")
            or host == "fb.com" or host.endswith(".fb.com")):
        return "facebook"
    if host == "instagram.com" or host.endswith(".instagram.com"):
        return "instagram"
    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        return "tiktok"
    return None


def import_links_file(filename: str, data: bytes) -> dict:
    """Importe les liens d'un fichier Excel CHOISI par l'utilisateur.

    - lecture seule du classeur (jamais réécrit) ;
    - sans limite de nombre : tous les liens du fichier sont lus ;
    - dédoublonnage contre la liste existante (www/, m.facebook.com,
      « / » final ignorés) → seuls les liens MANQUANTS sont copiés ;
    - la liste est enregistrée définitivement sur le disque.
    """
    from . import xlsx
    from .targets import filter_new_links

    if not data:
        return {"ok": False, "message": "Aucun fichier reçu"}
    try:
        found = xlsx.extract_links_from_bytes(data, filename)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}

    # classement par plateforme + écartement des hôtes inconnus
    by_platform: dict[str, list[str]] = {}
    unknown = 0
    for raw in found:
        url = _normalize_link(raw)
        plat = _detect_platform(url)
        if plat is None:
            unknown += 1
            continue
        by_platform.setdefault(plat, []).append(url)

    if not by_platform:
        return {"ok": False,
                "message": "Aucun lien reconnu dans ce fichier "
                           "(Facebook / Instagram / TikTok attendu)"}

    existing = [i.get("url") for i in store.links()]
    added: list[dict] = []
    dupes = 0
    banned = 0
    for plat, urls in by_platform.items():
        # dédoublonnage façon humain : www./m./barre finale ne comptent pas
        new_urls = filter_new_links(urls, existing)
        # liste noire : jamais réimportés, même depuis un nouveau fichier
        kept = [u for u in new_urls if not store.is_blacklisted(u)]
        banned += len(new_urls) - len(kept)
        items, exact_dupes = store.add_links_bulk(kept, plat)
        added += items
        dupes += exact_dupes + (len(urls) - len(new_urls))
        existing += [i["url"] for i in items]

    total = len(store.links())
    msg = (f"Fichier importé : {len(added)} lien(s) ajouté(s), "
           f"{dupes} doublon(s) déjà en liste"
           + (f", {unknown} ignoré(s) (hôte inconnu)" if unknown else "")
           + (f", {banned} ignoré(s) (liste noire)" if banned else "")
           + f" — liste enregistrée ({total} lien(s)).")
    store.log(msg, source="cibles")
    return {"ok": True, "message": msg, "added": len(added),
            "duplicates": dupes, "links": store.links()}


# ── Import automatique des groupes & pages Facebook ───────────────────────
_import_lock = threading.Lock()
_importing = False


def importing() -> bool:
    return _importing


def start_import() -> dict:
    """Ajoute à la liste les groupes & pages Facebook manquants.

    Le fichier Excel (E:\\groupe fb\\…) sert UNIQUEMENT de référence :
    il est lu, jamais modifié. Sont ignorés les liens déjà dans le fichier
    ou déjà dans la liste de l'interface — le reste est ajouté à la liste.
    """
    global _importing
    with _import_lock:
        if _importing:
            return {"ok": False,
                    "message": "Un import est déjà en cours — patientez."}
        _importing = True

    def _run() -> None:
        global _importing
        try:
            from . import xlsx
            from .targets import extract_fb_targets, filter_new_links

            file_links = xlsx.read_links()
            reference = file_links + [i.get("url") for i in store.links()]
            t_start = time.time()
            store.log(f"Import Facebook : {len(file_links)} lien(s) dans votre "
                      f"fichier Excel (lecture seule), {len(store.links())} déjà "
                      f"dans la liste — je n'ajoute que les manquants.",
                      source="cibles")

            def _grab(page, url: str, kind: str, label: str) -> list[str]:
                """Repli : navigation complète (lent) si le fetch échoue."""
                store.log(f"Import Facebook : lecture de {label}…",
                          source="cibles")
                page.goto(url, wait_until="domcontentloaded")
                deadline = time.time() + 5
                hrefs: list[str] = []
                while True:
                    try:
                        hrefs = page.eval_on_selector_all(
                            "a[href]", "els => els.map(e => e.href)")
                    except Exception:
                        hrefs = []
                    # assez de cibles trouvées (ou délai dépassé) → on sort
                    if len(extract_fb_targets(hrefs, kind=kind)) >= 5 \
                            or time.time() >= deadline:
                        return hrefs
                    page.wait_for_timeout(150)

            # Rapide : deux téléchargements en parallèle DANS la page ouverte.
            # (Facebook renvoie parfois un HTML sans liens → repli navigation.)
            _LISTS_JS = """async () => {
                const urls = ["https://www.facebook.com/groups/",
                    "https://www.facebook.com/pages/?category=managed"];
                const rs = await Promise.allSettled(urls.map(u =>
                    fetch(u, {credentials: "include"})
                        .then(r => r.text())));
                const out = [];
                for (const s of rs) {
                    if (s.status !== "fulfilled") continue;
                    const doc = new DOMParser().parseFromString(
                        s.value, "text/html");
                    out.push(...[...doc.querySelectorAll("a[href]")]
                        .map(a => a.href));
                }
                return out;
            }"""

            def _work(page):
                if "facebook.com" not in (page.url or ""):
                    page.goto("https://www.facebook.com/",
                              wait_until="domcontentloaded")
                try:
                    hrefs = page.evaluate(_LISTS_JS)
                except Exception:
                    hrefs = []
                hrefs = [h for h in (hrefs or [])
                         if isinstance(h, str) and h.startswith("http")]
                # repli : les listes ne sont pas dans le HTML fetché
                if len(extract_fb_targets(hrefs, kind="groups")) < 3:
                    hrefs = _grab(page, "https://www.facebook.com/groups/",
                                  "groups", "vos groupes")
                    if "/login" in (page.url or ""):
                        return []
                    hrefs += _grab(page,
                                   "https://www.facebook.com/pages/"
                                   "?category=managed",
                                   "pages", "vos pages")
                return hrefs

            hrefs = browser.with_page("facebook", _work) or []
            elapsed = time.time() - t_start
            found = extract_fb_targets(hrefs)
            new = [u for u in filter_new_links(found, reference)
                   if not store.is_blacklisted(u)]   # fichier ET liste, hors bannis
            for url in new:
                store.add_link(url, "facebook")
            if not found:
                store.log("Import Facebook : rien trouvé — connectez-vous à "
                          "Facebook dans la fenêtre, puis relancez l'import.",
                          level="warn", source="cibles")
            elif new:
                store.log(f"Import Facebook terminé en {elapsed:.0f}s : "
                          f"{len(new)} ajouté(s) à votre liste "
                          f"({len(found) - len(new)} déjà connus).",
                          source="cibles")
            else:
                store.log(f"Import Facebook : {len(found)} lien(s) vu(s), "
                          f"0 nouveau — votre liste est à jour.", source="cibles")
        except Exception as exc:
            store.log(f"Import Facebook impossible : {exc}", level="error",
                      source="cibles")
        finally:
            _importing = False

    threading.Thread(target=_run, daemon=True, name="socia-import").start()
    return {"ok": True, "message": "Import lancé — les liens manquants vont "
                                   "apparaître dans la liste des liens."}


def _normalize_when(value) -> str | None:
    """Date/heure de début ou de fin → 'YYYY-MM-DDTHH:MM:SS' (heure locale).

    Accepte la sortie d'un champ ``datetime-local`` (``YYYY-MM-DDTHH:MM``).
    Lève ``ValueError`` si la valeur est illisible.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    if len(raw) == 16:                       # sans secondes
        raw += ":00"
    dt.datetime.fromisoformat(raw)           # validation
    return raw


# ── Comptes ────────────────────────────────────────────────────────────────
def register_account(platform: str, profile_url: str, label: str = "",
                     visible: bool = False) -> dict:
    """L'utilisateur donne l'adresse de son profil → enregistrement + fenêtre.

    ``visible=True`` : l'utilisateur va se connecter lui-même → fenêtre
    visible à l'écran. Sinon la fenêtre s'ouvre en arrière-plan et se suit
    dans l'aperçu intégré de l'interface (pas de pop-up).
    """
    if platform not in config.PLATFORMS:
        return {"ok": False, "message": f"Plateforme inconnue : {platform}"}
    url = (profile_url or "").strip()
    if not url:
        return {"ok": False, "message": "Adresse de profil vide"}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    store.upsert_account(platform, url, label=label, status="pending")
    if visible:
        store.log(f"Ouverture de la fenêtre {config.PLATFORM_LABELS[platform]} — "
                  f"connectez-vous Y VOUS-MÊME dans cette fenêtre, la session "
                  f"reste enregistrée sur le disque E:.", source="comptes")
    else:
        store.log(f"{config.PLATFORM_LABELS[platform]} s'ouvre en arrière-plan — "
                  f"suivez-le dans l'aperçu de l'interface.", source="comptes")

    # ouvre la fenêtre en arrière-plan : l'API répond tout de suite au clic,
    # l'utilisateur voit l'aperçu apparaître une seconde plus tard.
    def _open() -> None:
        try:
            browser.open_window_now(platform, url, visible=visible)
        except Exception as exc:
            store.log(f"Ouverture de la fenêtre impossible : {exc}", level="error",
                      source="comptes")

    threading.Thread(target=_open, daemon=True,
                     name=f"socia-open-{platform}").start()
    if visible:
        return {"ok": True,
                "message": f"Fenêtre {config.PLATFORM_LABELS[platform]} ouverte — "
                           f"connectez-vous-y vous-même, la session reste enregistrée"}
    return {"ok": True,
            "message": f"{config.PLATFORM_LABELS[platform]} ouvert dans l'aperçu "
                       f"de l'interface (sans fenêtre qui s'affiche)"}


def verify_account(platform: str) -> dict:
    """Vérifie que la session navigateur est bien connectée."""
    mod = platform_module(platform)
    if mod is None:
        return {"ok": False, "message": f"Plateforme inconnue : {platform}"}
    accounts = {a.get("platform"): a for a in store.accounts()}
    account = accounts.get(platform)
    if account is None:
        return {"ok": False, "message": "Aucun profil enregistré pour cette plateforme"}
    result = mod.check_login(account) or {"ok": False, "message": "résultat vide"}
    store.set_account_status(platform, "connected" if result.get("ok") else "error")
    store.log(f"Session {config.PLATFORM_LABELS.get(platform, platform)} : "
              + ("connectée ✔ — prêt à publier" if result.get("ok")
                 else "non connectée ✖ — reconnectez-vous dans la fenêtre"),
              source="comptes")
    return result


def forget_account(platform: str) -> dict:
    store.remove_account(platform)
    browser.close_window(platform)
    return {"ok": True, "message": f"Compte {platform} oublié (session fermée)"}


# ── Tâches ─────────────────────────────────────────────────────────────────
def create_task_from_command(text: str, extra: dict | None = None) -> dict:
    """Crée une tâche à partir d'une phrase française + compléments du formulaire."""
    parsed = commands.parse_command(text)
    extra = dict(extra or {})
    content = extra.get("content") or parsed.get("content") or ""
    platform = extra.get("platform") or parsed.get("platform")
    target = extra.get("target") or parsed.get("target") or "profile"
    # Décision utilisateur : les liens cochés dans la base priment ; s'il n'y
    # en a pas, la publication se fait sur mon compte / profil.
    if platform and selected_link_urls(platform):
        target = "links"
    elif target == "groups" and not (extra.get("group_url") or "").strip():
        # le champ « URL d'un groupe » a été retiré de l'interface
        target = "profile"

    # ── période de publication : début / fin (date + heure) ──
    try:
        start_at = _normalize_when(extra.get("start_at"))
        end_at = _normalize_when(extra.get("end_at"))
    except ValueError:
        return {"ok": False, "task": {}, "parsed": parsed,
                "message": "Date ou heure de début / de fin illisible"}
    if start_at and end_at and end_at <= start_at:
        return {"ok": False, "task": {}, "parsed": parsed,
                "message": "La fin doit être APRÈS le début de la période"}

    # ── fréquence : de 1 minute à 24 heures ──
    interval = extra.get("interval_seconds") or parsed.get("interval_seconds")
    if interval:
        interval = int(interval)
        if interval < 60:
            return {"ok": False, "task": {}, "parsed": parsed,
                    "message": "Fréquence minimale : 1 minute"}
        if interval > 86400:
            return {"ok": False, "task": {}, "parsed": parsed,
                    "message": "Fréquence maximale : 24 heures (1440 minutes)"}
    task = {
        "platform": platform,
        "kind": extra.get("kind") or parsed.get("kind") or "post",
        "target": target,
        "group_url": extra.get("group_url") or "",
        "media": extra.get("media") or parsed.get("media") or "",
        "content": content,
        "interval_seconds": interval,
        "start_at": start_at,
        "end_at": end_at,
        "command": text,
    }
    # ── quota : N liens max par exécution (0 = tous) ──
    try:
        max_targets = int(extra.get("max_targets") or 0)
    except (TypeError, ValueError):
        max_targets = 0
    if max_targets < 0 or max_targets > 1000:
        return {"ok": False, "task": {}, "parsed": parsed,
                "message": "Quota de liens par exécution : de 0 (tous) à 1000"}
    task["max_targets"] = max_targets
    task["pretty_photo"] = bool(extra.get("pretty_photo"))
    # ── photos Gemini validées par l'utilisateur (galerie « ✨ Générer »)
    photos = extra.get("photos") or []
    if not isinstance(photos, list):
        photos = []
    task["photos"] = [Path(p).name for p in photos
                      if isinstance(p, str) and p.strip()][:32]
    task["summary"] = _summarize(task)
    if not task["platform"] or not task["interval_seconds"] or not task["content"]:
        missing = []
        if not task["platform"]:
            missing.append("plateforme (Facebook / Instagram / TikTok)")
        if not task["interval_seconds"]:
            missing.append("fréquence (ex. « toutes les 1 heure »)")
        if not task["content"]:
            missing.append("contenu du post")
        return {"ok": False, "task": task, "parsed": parsed,
                "message": "Il me manque : " + ", ".join(missing)}
    task["summary"] = _summarize(task)
    created = store.add_task(task)
    return {"ok": True, "task": created, "parsed": parsed,
            "message": f"Tâche enregistrée : {created['summary']}"}


def blacklist_link_error(url: str) -> dict:
    """Poubelle d'un lien en difficulté : retiré des erreurs + mis en liste
    noire (+ décoché des cibles pour ne plus être republié par erreur).

    Un futur import Excel (ou ajout manuel) de ce lien sera refusé.
    """
    url = (url or "").strip()
    if not url:
        return {"ok": False, "message": "Lien vide",
                "link_errors": store.link_errors(),
                "blacklist": store.blacklist()}
    store.forget_link_error(url)
    store.add_blacklist(url)
    # décocher le lien s'il est encore dans la base (plus de republication)
    items = store.links()
    changed = False
    for it in items:
        if it.get("url") == url and it.get("selected"):
            it["selected"] = False
            changed = True
    if changed:
        store.save_links(items)
    return {"ok": True,
            "message": f"Lien mis en liste noire — il ne sera plus réimporté "
                       f"ni republié : {url[:60]}",
            "link_errors": store.link_errors(),
            "blacklist": store.blacklist()}


def unblacklist(url: str) -> dict:
    url = (url or "").strip()
    ok = store.remove_blacklist(url)
    return {"ok": ok,
            "message": ("Lien retiré de la liste noire — il pourra être "
                        "réimporté" if ok else "Lien introuvable dans la liste"),
            "blacklist": store.blacklist()}


def update_task_fields(task_id: str, fields: dict) -> dict:
    """Modifie une tâche EXISTANTE (même lancée) : contenu, fréquence,
    période, média. Le résumé est recalculé et la prochaine échéance
    repart sur la nouvelle fréquence.
    """
    current = next((t for t in store.tasks() if t.get("id") == task_id), None)
    if current is None:
        return {"ok": False, "message": "Tâche introuvable"}
    patch: dict = {}
    if "content" in fields:
        content = (fields.get("content") or "").strip()
        if not content:
            return {"ok": False, "message": "Le contenu ne peut pas être vide"}
        patch["content"] = content
    if "interval_minutes" in fields and fields.get("interval_minutes") not in (None, ""):
        try:
            minutes = int(fields["interval_minutes"])
        except (TypeError, ValueError):
            return {"ok": False, "message": "Fréquence illisible (minutes)"}
        if minutes < 1 or minutes > 1440:
            return {"ok": False,
                    "message": "La fréquence va de 1 à 1440 minutes (24 h maximum)"}
        patch["interval_seconds"] = minutes * 60
    if "max_targets" in fields:
        try:
            mt = int(fields.get("max_targets") or 0)
        except (TypeError, ValueError):
            return {"ok": False, "message": "Quota de liens illisible"}
        if mt < 0 or mt > 1000:
            return {"ok": False,
                    "message": "Le quota va de 0 (tous) à 1000 liens"}
        patch["max_targets"] = mt
    if "pretty_photo" in fields:
        patch["pretty_photo"] = bool(fields.get("pretty_photo"))
    for key in ("start_at", "end_at", "media"):
        if key in fields:
            patch[key] = (fields.get(key) or "").strip()
    if "media" in patch and patch["media"] != (current.get("media") or ""):
        # nouveau média → les photos Gemini de l'ancien ne conviennent plus
        patch["photos"] = []
        patch["photo_cursor"] = 0
    if "photos" in fields and isinstance(fields.get("photos"), list):
        patch["photos"] = [Path(p).name for p in fields["photos"]
                           if isinstance(p, str) and p.strip()][:32]
        patch["photo_cursor"] = 0
    if "start_at" in patch or "end_at" in patch:
        try:
            start_at = _normalize_when(patch.get("start_at", current.get("start_at") or "") or "")
            end_at = _normalize_when(patch.get("end_at", current.get("end_at") or "") or "")
        except ValueError:
            return {"ok": False, "message": "Date ou heure de début / de fin illisible"}
        if start_at and end_at and end_at <= start_at:
            return {"ok": False, "message": "La fin doit être APRÈS le début de la période"}
        patch["start_at"] = start_at
        patch["end_at"] = end_at
    if not patch:
        return {"ok": False, "message": "Rien à modifier"}
    merged = dict(current)
    merged.update(patch)
    patch["summary"] = _summarize(merged)
    updated = store.update_task(task_id, **patch)
    return {"ok": True, "task": updated,
            "message": f"Tâche modifiée : {patch['summary']}"}


def _summarize(task: dict) -> str:
    plat = config.PLATFORM_LABELS.get(task.get("platform", ""), "?")
    if task.get("target") == "links":
        n = len(selected_link_urls(task.get("platform") or "facebook"))
        where = f"{n} lien(s) coché(s) (pages & groupes)" if n else "aucun lien coché"
        q = int(task.get("max_targets") or 0)
        if q and (not n or n > q):
            where = f"{q} liens/exécution parmi {n or '?'} cochés (rotation)"
        elif q:
            where = f"{q} liens cochés par exécution (rotation)"
    elif task.get("target") == "groups":
        where = "mes groupes Facebook"
    else:
        where = f"mon compte {plat}"
    freq = commands.human_interval(int(task.get("interval_seconds") or 0))
    kind = {"post": "post", "video": "vidéo", "story": "story"}.get(
        task.get("kind", "post"), "post")
    body = (task.get("content") or "").strip()
    excerpt = (body[:40] + "…") if len(body) > 40 else body
    photos_n = len(task.get("photos") or [])
    with_photo = (f" + {photos_n} photo(s) Gemini" if photos_n
                  else " + photo présentable" if task.get("pretty_photo")
                  else (" + photo" if task.get("media") else ""))
    return f"Publier « {excerpt} »{with_photo} {freq} sur {where}"


def run_task(task: dict) -> dict:
    """Exécute une tâche : vérifie le compte puis publie via la plateforme."""
    platform = task.get("platform")
    mod = platform_module(platform)
    if mod is None:
        return {"ok": False, "message": f"Plateforme inconnue : {platform}"}

    account = next((a for a in store.accounts()
                    if a.get("platform") == platform), None)
    if account is None:
        return {"ok": False,
                "message": f"Aucun compte {config.PLATFORM_LABELS.get(platform, platform)} "
                           f"enregistré — ajoutez d'abord votre profil"}

    # enrichit la tâche avec l'URL du profil de l'utilisateur
    task = dict(task)
    task.setdefault("profile_url", account.get("profile_url"))

    # ── cibles : les liens cochés dans la base (pages & groupes) ──
    if task.get("target") == "links":
        urls = selected_link_urls(platform)
        if not urls:
            return {"ok": False,
                    "message": "Aucune cible cochée — cliquez sur la flèche à côté "
                               "du champ lien (section Facebook) et cochez vos "
                               "pages / groupes"}
        # ── quota : ne publier que N liens par exécution, en ROTATION ──
        # (400 groupes cochés + quota 10 → chaque exécution prend les 10
        #  suivants, puis le tour recommence : tous les groupes sont couverts
        #  sans jamais faire une campagne monstre.)
        limit = int(task.get("max_targets") or 0)
        if 0 < limit < len(urls):
            start = int(task.get("target_cursor") or 0) % len(urls)
            picked = [urls[(start + i) % len(urls)] for i in range(limit)]
            if task.get("id"):
                store.update_task(task["id"],
                                  target_cursor=(start + limit) % len(urls))
            store.log(f"Quota : {limit} lien(s) sur {len(urls)} cochés — "
                      f"lot {start + 1}→{start + limit} (rotation à chaque "
                      "exécution).", source="programmation")
            urls = picked
        task["link_urls"] = urls
    elif task.get("target") == "groups" and not (task.get("group_url") or "").strip():
        # « partage dans mes groupes » sans URL : on utilise les liens cochés
        urls = selected_link_urls(platform)
        if urls:
            task["target"] = "links"
            task["link_urls"] = urls

    # On ne fait PAS de vérification préalable : l'utilisateur se connecte
    # lui-même dans la fenêtre visible, on publie directement. Si la session
    # n'est pas valide, la plateforme le signalera clairement.
    result = mod.publish(task) or {"ok": False, "message": "aucun résultat"}
    store.set_account_status(
        platform, "connected" if result.get("ok") else account.get("status", "pending"))
    return result


# ── État global (pour l'interface) ─────────────────────────────────────────
def global_state() -> dict:
    from . import scheduler as scheduler_mod  # import tardif (évite circulaire)
    return {
        "accounts": store.accounts(),
        "links": store.links(),
        "windows": browser.windows_status(),
        "browser": browser.diagnose(),
        "platforms": [
            {"id": p, "label": config.PLATFORM_LABELS[p],
             "connected": any(a.get("platform") == p and a.get("status") == "connected"
                              for a in store.accounts())}
            for p in config.PLATFORMS
        ],
    }
