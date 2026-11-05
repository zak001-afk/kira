"""Instagram — connexion + publication (post photo/vidéo, story).

Instagram exige un fichier média (photo/vidéo) : un post « texte seul »
n'existe pas sur cette plateforme, l'agent le signale alors clairement.
"""
from __future__ import annotations

from pathlib import Path

from .. import browser, config, store
from . import base


def check_login(account: dict) -> dict:
    url = account.get("profile_url") or config.HOME_URLS["instagram"]

    def _work(page):
        page.goto(url, wait_until="domcontentloaded")
        base.wait_stable(page, 2500)
        if base.looks_logged_out(page):
            store.log("Instagram : non connecté — connectez-vous dans la fenêtre "
                      "ouverte puis relancez la vérification.", level="warn",
                      source="instagram")
            return {"ok": False, "message": "Non connecté (fenêtre de login ouverte)"}
        return {"ok": True, "message": "Connecté à Instagram"}

    try:
        return browser.with_page("instagram", _work)
    except Exception as exc:
        return {"ok": False, "message": f"Erreur Instagram : {exc}"}


def _resolve_media(task: dict) -> Path | None:
    media = task.get("media") or ""
    if not media:
        return None
    p = Path(media)
    if not p.is_absolute():
        p = config.MEDIA / media
    return p if p.exists() else None


def publish(task: dict) -> dict:
    kind = task.get("kind", "post")
    media = _resolve_media(task)
    content = (task.get("content") or "").strip()
    if media is None:
        return {"ok": False,
                "message": "Instagram nécessite une image/vidéo — "
                           "indiquez un fichier média dans la tâche"}

    def _work(page):
        if task.get("id") and store.is_cancelled(task.get("id")):
            return {"ok": False, "message": "Arrêté par l'utilisateur"}
        page.goto(config.HOME_URLS["instagram"], wait_until="domcontentloaded")
        base.wait_stable(page, 2500)
        if base.looks_logged_out(page):
            return {"ok": False, "message": "Instagram non connecté"}

        # bouton « nouvelle publication » (＋)
        opened = base.click_first(page, [
            'svg[aria-label="Nouvelle publication"]',
            'a[href="/create/select/"]',
            'a[aria-label*="Nouvelle" i]',
            'nav a[href*="/create/"]',
        ], timeout=6000)
        if not opened:
            page.goto("https://www.instagram.com/create/select/",
                      wait_until="domcontentloaded")
            base.wait_stable(page, 2500)

        # story = déposer le média dans la zone « story »
        input_file = base.first(page, [
            'input[type="file"]',
            'div[role="dialog"] input[type="file"]',
        ], timeout=6000)
        if input_file is None:
            return {"ok": False, "message": "Sélecteur de fichier introuvable"}
        try:
            input_file.set_input_files(str(media))
        except Exception as exc:
            return {"ok": False, "message": f"Envoi du média impossible : {exc}"}
        base.wait_stable(page, 4000)

        # Aperçu → Suivant → Suivant → Partager
        for _ in range(2):
            base.click_first(page, [
                'button:has-text("Suivant")',
                'div[role="button"]:has-text("Suivant")',
                'button:has-text("Next")',
            ], timeout=8000)
            base.wait_stable(page, 2000)

        if content:
            base.type_into(page, [
                'textarea[aria-label*="escription" i]',
                'textarea[aria-label*="caption" i]',
                'div[contenteditable="true"][role="textbox"]',
            ], content, timeout=6000)
            base.wait_stable(page, 800)

        if kind == "story":
            # story : publication directe depuis l'éditeur
            base.click_first(page, [
                'button:has-text("Partager")',
                'div[role="button"]:has-text("Partager")',
                'button:has-text("Share")',
            ], timeout=8000)
        else:
            clicked = base.click_first(page, [
                'button:has-text("Partager")',
                'div[role="button"]:has-text("Partager")',
                'button:has-text("Share")',
            ], timeout=8000)
            if not clicked:
                return {"ok": False, "message": "Bouton « Partager » introuvable"}

        base.wait_stable(page, 4000)
        browser.screenshot(page, "instagram-derniere-publication")
        return {"ok": True, "message": f"Publication Instagram ({kind}) envoyée"}

    try:
        return browser.with_page("instagram", _work, timeout=600.0)
    except Exception as exc:
        return {"ok": False, "message": f"Erreur Instagram : {exc}"}
