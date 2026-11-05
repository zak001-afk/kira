"""TikTok — connexion + publication de vidéo (ou story)."""
from __future__ import annotations

from pathlib import Path

from .. import browser, config, store
from . import base


def check_login(account: dict) -> dict:
    url = account.get("profile_url") or config.HOME_URLS["tiktok"]

    def _work(page):
        page.goto(url, wait_until="domcontentloaded")
        base.wait_stable(page, 2500)
        if base.looks_logged_out(page):
            store.log("TikTok : non connecté — connectez-vous dans la fenêtre "
                      "ouverte puis relancez la vérification.", level="warn",
                      source="tiktok")
            return {"ok": False, "message": "Non connecté (fenêtre de login ouverte)"}
        return {"ok": True, "message": "Connecté à TikTok"}

    try:
        return browser.with_page("tiktok", _work)
    except Exception as exc:
        return {"ok": False, "message": f"Erreur TikTok : {exc}"}


def _resolve_media(task: dict) -> Path | None:
    media = task.get("media") or ""
    if not media:
        return None
    p = Path(media)
    if not p.is_absolute():
        p = config.MEDIA / media
    return p if p.exists() else None


def publish(task: dict) -> dict:
    media = _resolve_media(task)
    content = (task.get("content") or "").strip()
    if media is None:
        return {"ok": False,
                "message": "TikTok nécessite un fichier vidéo — indiquez un "
                           "fichier média dans la tâche"}

    def _work(page):
        if task.get("id") and store.is_cancelled(task.get("id")):
            return {"ok": False, "message": "Arrêté par l'utilisateur"}
        page.goto("https://www.tiktok.com/upload?lang=fr", wait_until="domcontentloaded")
        base.wait_stable(page, 3000)
        if base.looks_logged_out(page):
            return {"ok": False, "message": "TikTok non connecté"}

        input_file = base.first(page, [
            'input[type="file"]',
            'input[accept*="video"]',
        ], timeout=8000)
        if input_file is None:
            # parfois une iframe / nouveau design
            for frame in page.frames:
                cand = frame.locator('input[type="file"]').first
                try:
                    if cand.count() > 0:
                        input_file = cand
                        break
                except Exception:
                    continue
        if input_file is None:
            return {"ok": False, "message": "Sélecteur de fichier vidéo introuvable"}
        try:
            input_file.set_input_files(str(media))
        except Exception as exc:
            return {"ok": False, "message": f"Envoi de la vidéo impossible : {exc}"}

        # attendre la fin du traitement
        for _ in range(30):
            base.wait_stable(page, 2000)
            if base.first(page, [
                'button:has-text("Publier")',
                'div[data-e2e="upload-post"]',
                'button[data-e2e="post_publish"]',
            ], timeout=1500):
                break

        if content:
            base.type_into(page, [
                'div[data-e2e="post-desc"]',
                'div[contenteditable="true"][role="textbox"]',
                'textarea[placeholder*="escription" i]',
            ], content, timeout=6000)
            base.wait_stable(page, 600)

        clicked = base.click_first(page, [
            'button:has-text("Publier")',
            'button[data-e2e="post_publish"]',
            'div[data-e2e="upload-post"]',
        ], timeout=10000)
        if not clicked:
            browser.screenshot(page, "tiktok-echec-publication")
            return {"ok": False, "message": "Bouton « Publier » introuvable sur TikTok"}

        base.wait_stable(page, 5000)
        browser.screenshot(page, "tiktok-derniere-publication")
        return {"ok": True, "message": "Vidéo publiée sur TikTok"}

    try:
        # le traitement de la vidéo côté TikTok peut durer plusieurs minutes
        return browser.with_page("tiktok", _work, timeout=900.0)
    except Exception as exc:
        return {"ok": False, "message": f"Erreur TikTok : {exc}"}
