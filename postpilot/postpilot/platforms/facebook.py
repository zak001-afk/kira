"""Facebook — vérification de connexion et publication (profil ou groupes).

Flux réel de l'interface Facebook (constaté sur le site, UI « Créer une
publication ») :

1. clic sur le déclencheur « Que voulez-vous dire ? » → boîte de dialogue ;
2. la saisie se fait UNIQUEMENT dans la textbox de ce dialogue — jamais dans
   un champ de commentaire (bug corrigé : l'ancien code prenait le premier
   ``contenteditable`` de la page, qui était un commentaire) ;
3. si la tâche fournit une photo/vidéo, elle est jointe via l'input ``file``
   du dialogue (« Photo/Vidéo ») ;
4. clic sur « Suivant » → écran « Paramètres de la publication » ;
5. clic sur « Publier » (sélecteur exact, jamais « Enregistrer »).

La cible peut être le profil, un groupe unique, OU la liste des liens
cochés par l'utilisateur dans l'interface (target = "links") : le même
post est alors enchaîné sur CHAQUE lien coché, page après page.

Les fenêtres restent visibles pendant toute l'opération : l'utilisateur
peut suivre chaque étape dans la fenêtre Facebook.
"""
from __future__ import annotations

import random
import re
import time
from pathlib import Path

from .. import browser, config, photo, store
from . import base

LOGIN_URL_HINT = "/login"

# pause anti-robot entre deux publications : ~10 s, VARIABLE (différente
# à chaque fois) pour ne pas avoir un rythme régulier de machine.
_PAUSE_MIN_S = 10          # base 10 s entre deux publications
_PAUSE_MAX_S = 13          # varie à chaque fois → non prévisible


def _human_pause() -> float:
    """Durée d'attente (secondes) avant la prochaine publication.

    Aléatoire et différente à chaque appel : bornée entre 10 s et 13 s,
    avec une valeur non arrondie (ex. 11,4 s) pour imiter un humain.
    """
    return round(random.uniform(_PAUSE_MIN_S, _PAUSE_MAX_S), 1)

# déclencheur du composeur sur le fil / le profil / un groupe / une page
_TRIGGER_RES = [
    re.compile(r"Que voulez-vous dire", re.I),
    re.compile(r"Exprimez-vous(?!.*(commentaire|comment))", re.I),  # JAMAIS les commentaires
    re.compile(r"Quoi de neuf", re.I),
    re.compile(r"Écrivez quelque chose", re.I),
]

# textbox DANS la boîte de dialogue de publication (jamais hors dialogue)
_DIALOG_BOX = 'div[role="dialog"] [contenteditable="true"][role="textbox"]'

# photo jointe déjà présente (ne pas la ré-joindre)
_ATTACHED = 'div[role="dialog"] [aria-label="Supprimer la pièce jointe de la publication"]'

# bouton Publier — JAMAIS « Enregistrer » (brouillon)
_PUB_SEL = [
    'div[role="dialog"] div[aria-label="Publier"][role="button"]',
    'div[role="dialog"] [aria-label="Publier"]',
    'div[role="dialog"] div[role="button"]:has-text("Publier")',
    '[aria-label="Publier"][role="button"]',
]

# popups promotionnels Facebook qui recouvrent l'écran de publication
# (constaté : « Ajoutez un bouton Appeler » apparaît sur « Paramètres de la
#  publication » et intercepte / bloque le clic « Publier »)
_PROMO_RX = re.compile(
    r"Ajoutez un bouton|Échangez directement avec les personnes|"
    r"Passer à la version|Découvrez |Essayer gratuitement",
    re.IGNORECASE)


# ── Connexion ──────────────────────────────────────────────────────────────
def check_login(account: dict) -> dict:
    """Ouvre la fenêtre Facebook sur le profil et vérifie la connexion."""
    url = account.get("profile_url") or config.HOME_URLS["facebook"]

    def _work(page):
        page.goto(url, wait_until="domcontentloaded")
        base.wait_stable(page, 2500)
        if base.looks_logged_out(page):
            store.log("Facebook : non connecté — connectez-vous dans la fenêtre "
                      "ouverte, puis relancez la vérification.", level="warn",
                      source="facebook")
            return {"ok": False, "message": "Non connecté (fenêtre de login ouverte)"}
        return {"ok": True, "message": "Connecté à Facebook"}

    try:
        return browser.with_page("facebook", _work)
    except Exception as exc:
        return {"ok": False, "message": f"Erreur Facebook : {exc}"}


# ── Publication ────────────────────────────────────────────────────────────
def _click_trigger(page) -> bool:
    """Clique sur le déclencheur du composeur (« Que voulez-vous dire ? »,
    « Exprimez-vous… », …) — 1re puis 2e occurrence.

    Jamais un champ de commentaire : les motifs « Exprimez-vous… » des
    commentaires (« Exprimez-vous dans les commentaires ») sont écartés par
    la regex d'exclusion, et le repli ne vise que le composeur principal.
    """
    for rx in _TRIGGER_RES:
        locs = page.get_by_role("button").filter(has_text=rx)
        for i in (0, 1):                       # 1re OU 2e occurrence
            try:
                if locs.count() <= i:
                    break
                loc = locs.nth(i)
                if loc.is_visible(timeout=2000):
                    loc.click(timeout=8000)
                    return True
            except Exception:
                continue
    # repli : déclencheur marqué par aria-label (composeur principal only)
    if base.click_first(page, [
        'div[aria-label="Que voulez-vous dire ?"]',
        'div[aria-label*="Quoi de neuf" i]',
        'div[role="main"] div[role="button"]:has-text("Que voulez-vous dire")',
        'div[role="main"] div[role="button"]:has-text("Exprimez-vous")',
    ], timeout=5000):
        return True
    # repli GROUPE : le champ « Exprimez-vous… » est un div texte, pas un
    # bouton — on clique directement sur le texte (1re occurrence visible),
    # JAMAIS une mention de commentaire
    try:
        loc = page.get_by_text(
            re.compile(r"^Exprimez-vous(?!.*(commentaire|comment))", re.I)
        ).first
        if loc.is_visible(timeout=2000):
            loc.click(timeout=8000)
            return True
    except Exception:
        pass
    return False


# ── Repli : champ de partage EN LIGNE (groupe/page sans dialogue) ─────────
_INLINE_BOX = '[contenteditable="true"][role="textbox"]'

_JS_NOT_COMMENT = """el => {
  const bad = /commentaire|comment|répondre|reply/i;
  const own = el.getAttribute('aria-label') || '';
  if (bad.test(own)) return false;
  let a = el.closest('[aria-label]');
  if (a && bad.test(a.getAttribute('aria-label') || '')) return false;
  return true;
}"""


def _find_inline_box(page, timeout: int = 3500):
    """Champ « Exprimez-vous… » EN LIGNE (groupe, page, profil).

    Prend la 1re puis la 2e occurrence visible, en écartant JAMAIS tout
    champ de commentaire / réponse.
    """
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        try:
            locs = page.locator(_INLINE_BOX)
            n = min(locs.count(), 5)
        except Exception:
            n = 0
        for i in range(n):
            try:
                cand = locs.nth(i)
                if not cand.is_visible(timeout=400):
                    continue
                if not cand.evaluate(_JS_NOT_COMMENT):
                    continue                  # commentaire → on saute
                return cand
            except Exception:
                continue
        time.sleep(0.4)
    return None


def _wait_dialog_box(page, timeout: int = 8000):
    """Attend la textbox du dialogue de publication, puis la renvoie."""
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        loc = base.first(page, [_DIALOG_BOX], timeout=800)
        if loc is not None:
            return loc
        time.sleep(0.3)
    return None


def _resolve_media(task: dict) -> Path | None:
    """Chemin de la photo/vidéo de la tâche, ou None si aucune."""
    media = (task.get("media") or "").strip()
    if not media:
        return None
    p = Path(media)
    if not p.is_absolute():
        p = config.MEDIA / media
    return p if p.exists() else None


def _dismiss_promos(page) -> bool:
    """Ferme les popups promotionnels qui bloquent l'écran de publication.

    Ne agit QUE sur une boîte dont le texte correspond à un popup connu —
    le dialogue de publication (« Que voulez-vous dire ? ») n'est jamais
    touché. Ne clique que sur « Plus tard » ou la croix « Fermer » :
    jamais sur « Ajouter un bouton » ni sur « Publier ».
    """
    try:
        dialogs = page.locator('div[role="dialog"], div[role="alertdialog"]')
        n = dialogs.count()
    except Exception:
        return False
    closed = False
    for i in range(n):
        try:
            d = dialogs.nth(i)
            if not d.is_visible(timeout=400):
                continue
            txt = d.inner_text(timeout=700) or ""
        except Exception:
            continue
        if not _PROMO_RX.search(txt):
            continue
        if re.search(r"Que voulez-vous dire", txt, re.I):
            continue                       # notre composeur : on ne le ferme pas
        hit = False
        for sel in ('button:has-text("Plus tard")',
                    '[aria-label="Fermer"]',
                    '[aria-label="Close"]'):
            try:
                loc = d.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=600):
                    loc.click(timeout=3000)
                    hit = True
                    break
            except Exception:
                continue
        if not hit:
            try:
                page.keyboard.press("Escape")   # dernier recours
                hit = True
            except Exception:
                pass
        if hit:
            closed = True
            time.sleep(0.8)
    return closed


def _step(page, message: str) -> None:
    """Affiche l'étape en direct dans l'interface + met à jour son aperçu.

    N'importe quelle erreur ici est ignorée : l'étape ne doit JAMAIS faire
    échouer la publication.
    """
    try:
        store.log(message, source="facebook")
    except Exception:
        pass
    browser.store_frame("facebook", page)


def _publish_flow(page, content: str, media: Path | None) -> dict:
    """Composeur → texte → (photo) → Suivant → Publier. Toujours en dialogue."""

    # dialogue déjà ouvert ? sinon clic sur le déclencheur
    _dismiss_promos(page)
    box = _wait_dialog_box(page, timeout=1200)
    if box is None:
        # dialogue resté sur « Paramètres de la publication » → retour au
        # composeur (la textbox n'existe plus sur cet écran)
        base.click_first(page, ['div[role="dialog"] [aria-label="Retour"]'],
                         timeout=2000)
        box = _wait_dialog_box(page, timeout=4000)
    if box is None:
        if not _click_trigger(page):
            # repli : champ de partage en ligne « Exprimez-vous… »
            # (groupe / page / profil sans boîte de dialogue)
            box = _find_inline_box(page)
            if box is None:
                if base.looks_logged_out(page):
                    return {"ok": False,
                            "message": "Facebook non connecté — connectez-vous dans la "
                                       "fenêtre Facebook, puis relancez la tâche"}
                return {"ok": False,
                        "message": "Champ de partage introuvable (« Que voulez-vous "
                                   "dire ? » ou « Exprimez-vous… »)"}
        else:
            box = _wait_dialog_box(page, timeout=4000)
            if box is None:
                box = _find_inline_box(page)   # dialogue non ouvert → en ligne
    if box is None:
        return {"ok": False, "message": "Dialogue de publication non ouvert"}
    _step(page, "Dialogue de publication ouvert")

    # ── texte (uniquement dans le dialogue) ──
    _dismiss_promos(page)
    try:
        box.click(timeout=5000)
        # brouillon résiduel d'une exécution précédente : on vide d'abord
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        box.type(content, delay=10)
    except Exception as exc:
        return {"ok": False, "message": f"Saisie impossible : {exc}"}
    excerpt = content[:60].replace("\n", " ")
    _step(page, f"Texte saisi : « {excerpt}{'…' if len(content) > 60 else ''} »")

    # ── photo / vidéo si fournie ──
    if media is not None:
        already = base.first(page, [_ATTACHED], timeout=1500)
        if already is None:
            # NB : ce champ est MASQUÉ (display:none) — la visibilité ne doit
            # donc PAS être exigée, sinon introuvable à tort.
            file_in = None
            for sel in ('div[role="dialog"] input[type="file"]',
                        'input[type="file"][accept*="image"]',
                        'input[type="file"]'):
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        file_in = loc
                        break
                except Exception:
                    continue
            if file_in is None:
                return {"ok": False,
                        "message": "Champ « Photo/Vidéo » introuvable dans le dialogue"}
            try:
                file_in.set_input_files(str(media))
            except Exception as exc:
                return {"ok": False, "message": f"Joindre la photo impossible : {exc}"}
            # attendre l'aperçu de la pièce jointe
            deadline = time.time() + 15
            while time.time() < deadline:
                if base.first(page, [_ATTACHED], timeout=800) is not None:
                    break
                time.sleep(0.5)
            else:
                return {"ok": False,
                        "message": "La photo n'a pas été jointe (aperçu absent)"}
            _step(page, f"Photo jointe : {media.name}")
        base.wait_stable(page, 1500)

    # ── Suivant → écran « Paramètres de la publication » ──
    _dismiss_promos(page)
    has_suivant = base.first(page, [
        'div[role="dialog"] [aria-label="Suivant"]',
        'div[role="dialog"] button:has-text("Suivant")',
        'div[role="dialog"] div[role="button"]:has-text("Suivant")',
    ], timeout=2500)
    if has_suivant is not None:
        try:
            has_suivant.click(timeout=6000)
        except Exception:
            _dismiss_promos(page)          # popup interceptait le clic
            try:
                base.click_first(page, [
                    'div[role="dialog"] [aria-label="Suivant"]',
                    'div[role="dialog"] div[role="button"]:has-text("Suivant")',
                ], timeout=4000)
            except Exception:
                pass
        base.wait_stable(page, 1200)
        _step(page, "Clic « Suivant » → écran Paramètres de la publication")

    # ── Publier (sélecteur exact pour ne jamais viser « Enregistrer ») ──
    published = None
    for attempt in (0, 1):
        _dismiss_promos(page)              # popup au-dessus de l'écran ?
        published = base.first(page, _PUB_SEL, timeout=3500)
        if published is None:
            break
        try:
            published.click(timeout=6000)
            _step(page, "Clic « Publier » envoyé")
            break
        except Exception:
            if attempt:
                return {"ok": False,
                        "message": f"Clic « Publier » impossible (popup "
                                   "toujours presente ?)"}
            time.sleep(1.0)
    if published is None:
        if not has_suivant:
            return {"ok": False, "message": "Bouton « Publier » introuvable"}
        return {"ok": False,
                "message": "Bouton « Publier » introuvable sur l'écran de paramètres"}
    base.wait_stable(page, 1000)

    # contrôle : le dialogue de publication doit se fermer (publication
    # partie). Les popups (« Ajoutez un bouton Appeler ») peuvent apparaître
    # juste après le clic : on les ferme d'abord, on ne les confond pas avec
    # un échec.
    deadline = time.time() + 6
    while time.time() < deadline:
        _dismiss_promos(page)
        if base.first(page, ['div[role="dialog"] [aria-label="Publier"]'],
                      timeout=600) is None:
            browser.store_frame("facebook", page)
            return {"ok": True, "message": "Publication envoyée sur Facebook"}
        time.sleep(0.5)

    # dernier diagnostic : texte d'erreur Facebook éventuellement affiché
    detail = ""
    try:
        dlg = base.first(page, ['div[role="dialog"]'], timeout=800)
        if dlg is not None:
            detail = (dlg.inner_text(timeout=1000) or "").replace("\n", " ")[:120]
    except Exception:
        pass
    suffix = f" — message Facebook : {detail}" if detail else ""
    return {"ok": False,
            "message": "Le dialogue est toujours ouvert — vérifiez la fenêtre "
                       f"Facebook (erreur affichée ?){suffix}"}


# ── Story Facebook (type EXPLICITEMENT choisi dans l'interface) ──────────
# déclencheur « Ajouter à votre story » (fil / profil)
_STORY_ADD = [
    'div[aria-label="Ajouter à votre story"]',
    'div[role="button"]:has-text("Ajouter à votre story")',
    'div:has-text("Ajouter à votre story")',
]


def _publish_story(page, content: str, media: Path | None) -> dict:
    """Publie une STORY Facebook (flux distinct du post — jamais les deux).

    Une story exige une photo/vidéo : sans média, on refuse clairement plutôt
    que de se « rattraper » sur un post.
    """
    if media is None:
        return {"ok": False,
                "message": "Une story Facebook exige une photo ou une vidéo — "
                           "indiquez un fichier média dans la tâche"}
    _dismiss_promos(page)
    if not base.click_first(page, _STORY_ADD, timeout=8000):
        return {"ok": False,
                "message": "Bouton « Ajouter à votre story » introuvable — "
                           "ouvrez votre profil Facebook ou votre fil"}
    _step(page, "▶ Story : bouton « Ajouter à votre story » cliqué")
    base.wait_stable(page, 2500)

    # média de la story (le champ file du composeur de story)
    file_in = base.first(page, [
        'div[role="dialog"] input[type="file"]',
        'input[type="file"][accept*="image"]',
        'input[type="file"]',
    ], timeout=8000)
    if file_in is None:
        return {"ok": False, "message": "Champ photo de la story introuvable"}
    try:
        file_in.set_input_files(str(media))
    except Exception as exc:
        return {"ok": False, "message": f"Envoi du média impossible : {exc}"}
    base.wait_stable(page, 5000)
    _step(page, f"Story : média joint ({media.name})")

    # texte éventuel dans la story
    if content:
        box = base.first(page, [
            'div[role="dialog"] [contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"][role="textbox"]',
        ], timeout=5000)
        if box is not None:
            try:
                box.click(timeout=4000)
                box.type(content, delay=10)
                _step(page, "Story : texte saisi")
            except Exception:
                pass          # le texte est optionnel : la story part sans

    # Suivant puis Partager maintenant (design actuel de Facebook)
    base.click_first(page, [
        'div[role="dialog"] [aria-label="Suivant"]',
        'div[role="button"]:has-text("Suivant")',
        'button:has-text("Suivant")',
    ], timeout=8000)
    base.wait_stable(page, 3000)
    shared = base.click_first(page, [
        'div[role="button"]:has-text("Partager maintenant")',
        'div[aria-label="Partager maintenant"]',
        'div[role="button"]:has-text("Publier")',
        'div[role="dialog"] div[role="button"]:has-text("Partager")',
    ], timeout=8000)
    if not shared:
        return {"ok": False,
                "message": "Bouton « Partager maintenant » introuvable — "
                           "vérifiez la fenêtre Facebook"}
    _step(page, "✔ Story : « Partager maintenant » cliqué")
    base.wait_stable(page, 4000)
    browser.store_frame("facebook", page)
    return {"ok": True, "message": "Story Facebook envoyée"}


def _short(url: str) -> str:
    """https://www.facebook.com/groups/abc → facebook.com/groups/abc (court)."""
    u = re.sub(r"^https?://(www\.|m\.|web\.)?", "", (url or "").strip())
    return u if len(u) <= 48 else u[:45] + "…"


def _targets(task: dict, account: dict) -> list[str] | str:
    """URLs à publier (1 pour profil/groupe, N pour les liens cochés).

    Retourne une LISTE d'URLs, ou un MESSAGE d'erreur (str).
    """
    target = task.get("target", "profile")
    if target == "links":
        urls = [u for u in (task.get("link_urls") or []) if u]
        if not urls:
            return ("Aucune cible cochée — cliquez sur la flèche à côté du champ "
                    "lien (section Facebook) et cochez vos pages / groupes")
        return urls
    if target == "groups":
        group_url = (task.get("group_url") or "").strip()
        if not group_url:
            return "Aucune URL de groupe fournie (champ « groupe »)"
        return [group_url]
    # profil : le composeur du fil (le même que sur la page d'accueil)
    return [account.get("profile_url") or config.HOME_URLS["facebook"]]


def _campaign_budget(n_targets: int) -> float:
    """Budget total (secondes) d'une campagne : ~3 min par cible
    (publication + pause ~10-18 s), minimum 5 min.

    SANS cela, toute campagne de plus de 90 s mourait avec
    « opération navigateur trop longue (> 90s) ».
    """
    return max(300.0, max(0, n_targets) * 180.0)


def _sleep_cancelable(seconds: float, task_id: str) -> bool:
    """Attend `seconds`, par tranches de 0,5 s, en surveillant l'annulation.

    Retourne False si la tâche a été mise en pause / supprimée pendant
    l'attente (ex. la pause anti-robot) → l'appelant doit s'arrêter.
    """
    end = time.time() + max(0.0, seconds)
    while time.time() < end:
        if task_id and store.is_cancelled(task_id):
            return False
        time.sleep(min(0.5, end - time.time()))
    return True


def _aggregate(results: list[tuple[str, dict]], total: int,
               cancelled: bool = False) -> dict:
    """Résume la publication sur N liens (un seul lien → résultat inchangé)."""
    if total == 1 and not cancelled:
        return results[0][1]
    ok_urls = [u for u, r in results if r.get("ok")]
    if cancelled:
        return {"ok": False,
                "message": f"Arrêté par l'utilisateur : {len(ok_urls)}/{total} "
                           f"lien(s) publié(s) avant l'arrêt"}
    ok_urls = [u for u, r in results if r.get("ok")]
    ko = [(u, r) for u, r in results if not r.get("ok")]
    if not ko and len(results) == total:
        shown = ", ".join(_short(u) for u in ok_urls[:5])
        more = " …" if total > 5 else ""
        return {"ok": True,
                "message": f"Publication envoyée sur {len(ok_urls)} liens : "
                           f"{shown}{more}"}
    if not ok_urls:
        reason = results[0][1].get("message", "échec") if results else "échec"
        return {"ok": False,
                "message": f"{reason} (0/{total} lien publié)"}
    detail = "; ".join(f"{_short(u)} → {r.get('message')}" for u, r in ko[:3])
    return {"ok": False,
            "message": f"{len(ok_urls)}/{total} lien(s) publié(s) — l'agent a "
                       f"continué sans se bloquer. Échecs : {detail} "
                       f"(liste « Liens en difficulté » de l'interface)"}


def publish(task: dict) -> dict:
    content = (task.get("content") or "").strip()
    if not content:
        return {"ok": False, "message": "Aucun contenu à publier"}
    account = {"profile_url": task.get("profile_url") or ""}

    # ── Story : type EXPLICITEMENT choisi → flux story UNIQUEMENT ──
    if (task.get("kind") or "post") == "story":
        media = _resolve_media(task)
        if task.get("pretty_photo") and media is not None \
                and photo.is_image(media):
            # vérifié AVANT d'ouvrir la fenêtre : Gemini indisponible =
            # publication reportée à la prochaine exécution
            ok, why = photo.available(task)
            if not ok:
                return {"ok": False,
                        "message": f"Photos Gemini indisponibles ({why}) — "
                                   "publication reportée à la prochaine "
                                   "exécution."}

        def _story_work(page):
            if task.get("id") and store.is_cancelled(task.get("id")):
                return {"ok": False, "message": "Arrêté par l'utilisateur"}
            url = account.get("profile_url") or config.HOME_URLS["facebook"]
            _step(page, "▶ Story : ouverture de votre profil Facebook")
            page.goto(url, wait_until="domcontentloaded")
            base.wait_stable(page, 4000)
            browser.store_frame("facebook", page)
            if base.looks_logged_out(page):
                return {"ok": False,
                        "message": "Facebook non connecté — connectez-vous dans "
                                   "la fenêtre Facebook, puis relancez la tâche"}
            # photo Gemini : une photo de la liste validée (ou une nouvelle)
            # pour cette story — jamais d'image inventée en local
            media_i = media
            if task.get("pretty_photo") and media is not None \
                    and photo.is_image(media):
                try:
                    media_i = photo.take_task_photo(task, media)
                except photo.GeminiError as exc:
                    return {"ok": False,
                            "message": f"Publication reportée : {exc}"}
            res = _publish_story(page, content, media_i)
            browser.screenshot(page, "facebook-derniere-story")
            return res

        try:
            return browser.with_page("facebook", _story_work, timeout=600.0)
        except Exception as exc:
            return {"ok": False, "message": f"Erreur Facebook : {exc}"}

    # ── Post (type par défaut) : flux post UNIQUEMENT, jamais de story ──
    targets = _targets(task, account)
    if isinstance(targets, str):
        return {"ok": False, "message": targets}
    media = _resolve_media(task)
    if task.get("media") and media is None:
        store.log(f"Photo introuvable : {task['media']} — publication texte seule.",
                  level="warn", source="facebook")
    if task.get("pretty_photo") and media is not None and photo.is_image(media):
        # vérifié AVANT d'ouvrir la fenêtre : Gemini indisponible =
        # publication reportée à la prochaine exécution (aucun lien touché)
        ok, why = photo.available(task)
        if not ok:
            return {"ok": False,
                    "message": f"Photos Gemini indisponibles ({why}) — "
                               "publication reportée à la prochaine "
                               "exécution."}

    def _work(page):
        tid = task.get("id") or ""
        total = len(targets)
        cancelled = False
        if tid:
            store.update_task(tid, progress={"done": 0, "total": total})
        results: list[tuple[str, dict]] = []
        gemini_stop = ""            # Gemini devenu indisponible en route
        for i, url in enumerate(targets):
            # ── arrêt immédiat si pause / suppression pendant le travail ──
            if tid and store.is_cancelled(tid):
                cancelled = True
                store.log("⏹ Tâche arrêtée par l'utilisateur — on s'arrête "
                          "tout de suite, sans finir les liens restants.",
                          level="warn", source="facebook")
                break
            if i > 0:
                # pause ANTI-ROBOT variable entre chaque publication :
                # jamais régulière, toujours > 10 s, différente à chaque fois
                # (interruptible : pause/supprimer l'interrompt aussitôt)
                wait = _human_pause()
                _step(page, f"⏳ Pause humaine de {wait:.1f} s avant la cible "
                            f"suivante (anti-robot)")
                if not _sleep_cancelable(wait, tid):
                    cancelled = True
                    store.log("⏹ Tâche arrêtée par l'utilisateur pendant la "
                              "pause — on s'arrête tout de suite.",
                              level="warn", source="facebook")
                    break
            try:
                _step(page, f"▶ Ouverture de la cible : {_short(url)}")
                page.goto(url, wait_until="domcontentloaded")
                base.wait_stable(page, 3000 if i == 0 else 1000)
                browser.store_frame("facebook", page)
                if base.looks_logged_out(page):
                    browser.screenshot(page, "facebook-non-connecte")
                    results.append((url, {
                        "ok": False,
                        "message": "Facebook non connecté — connectez-vous dans la "
                                   "fenêtre Facebook, puis relancez la tâche"}))
                    break                    # inutile de continuer : rien ne passera
                # ── photo Gemini : une photo par poste (liste validée en
                # rotation, ou nouvelle génération) — sinon REPORT, jamais
                # d'image inventée localement
                media_i = media
                if task.get("pretty_photo") and media is not None \
                        and photo.is_image(media):
                    try:
                        media_i = photo.take_task_photo(task, media)
                    except photo.GeminiError as exc:
                        gemini_stop = str(exc)
                        break
                res = _publish_flow(page, content, media_i)
            except Exception as exc:
                # AUCUN blocage : on note l'erreur et on passe au lien suivant
                res = {"ok": False, "message": f"Erreur inattendue : {exc}"}
            results.append((url, res))
            try:
                browser.screenshot(page, "facebook-derniere-publication")
            except Exception:
                pass
            if res.get("ok"):
                store.forget_link_error(url)   # réussi → plus en difficulté
                _step(page, f"✔ Publié sur {url[-45:]}")
            else:
                # enregistré pour la section « Liens en difficulté » —
                # et ON PASSE AU LIEN SUIVANT, sans se bloquer
                store.add_link_error(url, res.get("message") or "erreur inconnue")
                store.log(f"Cible {_short(url)} en échec : {res.get('message')} — "
                          f"on passe à la suivante.", level="warn",
                          source="facebook")
            # ── compteur de la tâche : X/Y publiés (visible dans l'interface)
            if tid:
                done = sum(1 for _, r in results if r.get("ok"))
                store.update_task(tid, progress={"done": done, "total": total})
        if (not cancelled and len(results) == total and total
                and all(r.get("ok") for _, r in results)
                and task.get("target") == "links"
                and not int(task.get("max_targets") or 0)):
            # campagne terminée : compteur remis à 0 et tâche terminée
            # (elle ne repartira plus — l'utilisateur la réactivera si besoin)
            if tid:
                store.update_task(tid, enabled=False,
                                  progress={"done": 0, "total": 0})
            store.log(f"✔ Campagne terminée : {total}/{total} publié(s) — "
                      f"compteur remis à 0, tâche terminée.", source="facebook")
        if gemini_stop:
            # Gemini s'est barré en pleine route : on N'INVENTE rien, on
            # s'arrête et la reprise se fera à la prochaine exécution
            done_n = sum(1 for _, r in results if r.get("ok"))
            store.log(f"⏸ Publication interrompue : {gemini_stop} — "
                      f"{done_n}/{total} envoyé(s) avant l'arrêt ; repris à "
                      f"la prochaine exécution.", level="warn",
                      source="facebook")
            return {"ok": False,
                    "message": f"Publication interrompue : {gemini_stop} — "
                               f"{done_n}/{total} envoyé(s) avant l'arrêt ; "
                               f"reprise à la prochaine exécution."}
        return _aggregate(results, total, cancelled=cancelled)

    try:
        # fenêtre VISIBLE : l'utilisateur suit comment l'agent entre dans
        # les groupes et partage (demande explicite)
        return browser.with_page("facebook", _work, visible=True,
                                 timeout=_campaign_budget(len(targets)))
    except Exception as exc:
        return {"ok": False, "message": f"Erreur Facebook : {exc}"}
