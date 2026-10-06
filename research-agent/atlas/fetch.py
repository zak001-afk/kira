"""Lecture des pages web : récupération HTML + extraction du texte principal."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from lxml import html as LH

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

_DROP = "//script|//style|//nav|//footer|//header|//aside|//form|//noscript|//svg|//iframe"
_TEXT_NODES = "//p//text()|//h2//text()|//h3//text()|//h4//text()|//li//text()|//blockquote//text()|//td//text()"


def extract_text(html_str: str) -> str:
    """Texte propre d'une page HTML (navigation, scripts et pieds retirés)."""
    try:
        doc = LH.fromstring(html_str)
    except Exception:
        return ""
    for bad in doc.xpath(_DROP):
        try:
            bad.drop_tree()
        except Exception:
            pass
    parts = [t.strip() for t in doc.xpath(_TEXT_NODES) if len(t.strip()) > 40]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def fetch_page(url: str, timeout: float = 10.0) -> str:
    """Texte d'une page, ou chaîne vide si la page bloque/échoue."""
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers=HEADERS)
        if resp.status_code >= 400:
            return ""
        ctype = resp.headers.get("content-type", "")
        if ctype and "html" not in ctype and "text/" not in ctype:
            return ""
        return extract_text(resp.text)
    except Exception:
        return ""


def fetch_pages(results: list[dict], max_pages: int = 4, page_chars: int = 1600,
                workers: int = 6, budget: float = 3.0) -> list[dict]:
    """Lit les meilleures pages en parallèle, dans l'ordre des résultats.

    Plafonné à `budget` secondes (ou 5 pages lues) : une page bloquée ne fait
    plus attendre toute la synthèse — on répond avec ce qu'on a déjà et on se
    rabattra sur les extraits de recherche pour le reste.
    Une page bloquée ou trop pauvre (< 200 caractères) est conservée sans
    contenu : on se rabattra sur son extrait de recherche.
    """
    targets = results[:max_pages]
    if not targets:
        return []
    texts: dict[str, str] = {}
    pool = ThreadPoolExecutor(max_workers=min(workers, max(1, len(targets))))
    try:
        futures = {pool.submit(fetch_page, item["url"]): item["url"]
                   for item in targets}
        want = min(5, len(targets))
        try:
            for fut in as_completed(futures, timeout=budget):
                url = futures[fut]
                try:
                    text = fut.result()
                except Exception:
                    text = ""
                texts[url] = text[:page_chars] if len(text) >= 200 else ""
                if sum(1 for value in texts.values() if value) >= want:
                    break  # assez de matière : ne pas attendre les lentes
        except TimeoutError:
            pass  # budget dépassée : on répond avec ce qui a déjà été lu
    finally:
        # Les fetch en cours continuent en arrière-plan ; rien ne les attend.
        pool.shutdown(wait=False, cancel_futures=True)

    pages = []
    for item in targets:
        pages.append({**item, "text": texts.get(item["url"], "")})
    return pages
