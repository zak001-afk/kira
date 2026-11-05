"""Extraction des cibles Facebook (pages & groupes) depuis des liens bruts.

Fonction PURE (aucun navigateur) : utilisée par l'import automatique
(``agent.start_import``) pour remplir la liste des liens de l'interface
à partir de la fenêtre Facebook déjà connectée.

Règles :
- /groups/<slug>/…      → https://www.facebook.com/groups/<slug>/
- /pages/<cat>/<slug>/  → https://www.facebook.com/pages/<cat>/<slug>/
- /<slug>/ (page)       → https://www.facebook.com/<slug>/
Les liens « système » de Facebook (découverte, paramètres, marketplace…)
sont écartés : ce ne sont jamais des cibles de publication.
"""
from __future__ import annotations

from urllib.parse import urlsplit

# slugs système de Facebook — jamais des cibles de publication
_SYSTEM = {
    "discover", "search", "join", "joins", "create", "your_posts",
    "referral", "admin",
    "events", "videos", "photos", "topics", "feed", "pinned", "members",
    "badge",    "marketplace", "merch", "seller", "files", "live", "plus",
    "sold_groups", "group", "watch", "gaming", "friends",
    "menu", "bookmarks", "saved", "settings", "help", "login", "logout",
    "notifications", "messages", "ads", "crisis", "policies", "privacy",
    "terms", "jobs", "fundraisers", "commerce", "explore", "reel", "reels",
    "edit", "home", "me", "index", "profile.php", "page.php", "photo.php",
    "story.php", "permalink.php", "most_recent", "recent", "category", "ref",
    "sharer", "dialog", "plugins", "tr", "l", "u", "imingroup",
    "groupcommerce", "community", "img", "help", "recover", "checkpoint",
    "two_step", "swift_queue", "compression", "cookie", "safety",
    # pages systèmes vues sur la liste « vos pages » (ne JAMAIS les ramener)
    "photo", "photos", "video", "story", "stories", "people", "pg",
    "hashtag", "topic", "public", "app", "apps", "game", "games",
    "term", "deactivated", "avatar", "feed", "permalink", "posts",
    "comment", "comments", "messages", "inbox", "friends", "requests",
}

_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com",
          "web.facebook.com", "mbasic.facebook.com"}


def normalize_url(url: str) -> str:
    """Clé de comparaison : https, hôte sans www/m., sans query ni « / » final.

    Deux écritures du même lien (avec/sans www, avec/sans barre oblique
    finale, m.facebook.com) doivent donner la MÊME clé.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw.lstrip("/")
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    for prefix in ("www.", "m.", "web.", "mbasic."):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break
    return f"https://{host}{parts.path.rstrip('/')}"


def filter_new_links(found, existing) -> list[str]:
    """Garde uniquement les liens absents de ``existing`` (sans doublon).

    La comparaison ignore www/, barre finale, query — un lien déjà dans le
    fichier Excel n'est jamais ramené deux fois.
    """
    keys = {normalize_url(u) for u in (existing or []) if (u or "").strip()}
    out: list[str] = []
    for u in found or []:
        key = normalize_url(u)
        if not key or key in keys:
            continue
        keys.add(key)
        out.append(u)
    return out


def _page_slug(seg: str) -> bool:
    """Un segment unique est un nom de page ssi ce n'est pas un fichier."""
    low = seg.lower()
    return not low.endswith((".php", ".html", ".php5", ".asp", ".aspx"))


def extract_fb_targets(hrefs, kind: str = "all") -> list[str]:
    """Retourne les URLs de cibles Facebook normalisées, sans doublon.

    ``kind`` : ``"groups"`` (uniquement les groupes), ``"pages"``
    (uniquement les pages) ou ``"all"`` (les deux). L'ordre d'apparition
    est conservé ; chaque URL n'apparaît qu'une fois.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in hrefs or []:
        url = (raw or "").strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url.lstrip("/")
        parts = urlsplit(url)
        if (parts.hostname or "").lower() not in _HOSTS:
            continue
        segs = [s for s in parts.path.split("/") if s]
        if not segs:
            continue
        head = segs[0].lower()
        if head in _SYSTEM:
            continue
        norm = None
        if head == "groups":
            if kind in ("all", "groups") and len(segs) >= 2:
                slug = segs[1]
                if slug.lower() not in _SYSTEM:
                    norm = f"https://www.facebook.com/groups/{slug}/"
        elif head == "pages":
            if kind in ("all", "pages") and len(segs) >= 3:
                norm = f"https://www.facebook.com/pages/{segs[1]}/{segs[2]}/"
        elif len(segs) == 1 and kind in ("all", "pages"):
            if _page_slug(segs[0]):
                norm = f"https://www.facebook.com/{segs[0]}/"
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out
