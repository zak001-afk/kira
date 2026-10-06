"""Recherche web via DuckDuckGo — sans clé API, tout le web."""
from __future__ import annotations

import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import urlparse

from ddgs import DDGS

_AD_MARKERS = ("bing.com/aclick", "duckduckgo.com/l/", "googleadservices",
               "google.com/aclk", "/sponsored/")

# Backends DuckDuckGo dans l'ordre : si l'un est saturé ("No results found"),
# on passe au suivant — protège contre les rate-limits lors d'usages intensifs.
_BACKENDS: tuple[str | None, ...] = (None, "lite", "html")
# Backend qui a fonctionné en dernier : on le teste en premier ensuite
# (évite de reperdre ~2,5 s sur un backend déjà saturé à chaque requête).
_preferred_backend: str | None = None


def _is_ad(url: str) -> bool:
    low = url.lower()
    return any(marker in low for marker in _AD_MARKERS)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _ddgs_one(backend: str | None, query: str, max_results: int,
              region: str) -> list[dict]:
    """Un appel DuckDuckGo sur un backend donné, pubs filtrées."""
    try:
        kwargs = {"backend": backend} if backend else {}
        raw = DDGS().text(query, region=region, max_results=max_results,
                          safesearch="moderate", **kwargs)
    except Exception:
        raw = []
    out: list[dict] = []
    for item in raw or []:
        url = (item.get("href") or item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")) or _is_ad(url):
            continue
        out.append({
            "url": url,
            "title": _clean(item.get("title", "")),
            "snippet": _clean(item.get("body") or item.get("snippet") or ""),
            "host": _host(url),
            "query": query,
        })
    return out


def search_one(query: str, max_results: int = 8, region: str = "fr-fr",
               budget: float = 6.0) -> list[dict]:
    """Une requête DuckDuckGo -> liste de {url, title, snippet, host}.

    Les backends partent EN PARALLÈLE et on prend le premier qui répond
    (en cas d'égalité, l'ordre de préférence est respecté) : un backend saturé
    ne fait plus attendre les autres — plafond global de `budget` secondes.
    """
    global _preferred_backend
    order: list[str | None] = list(_BACKENDS)
    if _preferred_backend in order:
        order.remove(_preferred_backend)
        order.insert(0, _preferred_backend)

    pool = ThreadPoolExecutor(max_workers=len(order))
    try:
        futures = {pool.submit(_ddgs_one, backend, query, max_results, region): backend
                   for backend in order}
        deadline = time.time() + budget
        pending = set(futures)
        while pending:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            done, pending = wait(pending, timeout=remaining,
                                 return_when=FIRST_COMPLETED)
            # Parmi ceux qui ont répondu, priorité à l'ordre préféré.
            for fut in sorted(done, key=lambda f: order.index(futures[f])):
                out = fut.result()
                if out:
                    _preferred_backend = futures[fut]
                    return out
        return []
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def dedupe(items: list[dict], max_total: int = 14, per_host: int = 2) -> list[dict]:
    """Supprime les doublons d'URL, limite à `per_host` résultats par domaine."""
    out: list[dict] = []
    seen: set[str] = set()
    hosts: dict[str, int] = {}
    for item in items:
        key = item["url"].split("#")[0].rstrip("/")
        host = item.get("host") or _host(item["url"])
        if key in seen or hosts.get(host, 0) >= per_host:
            continue
        seen.add(key)
        hosts[host] = hosts.get(host, 0) + 1
        item["host"] = host
        out.append(item)
        if len(out) >= max_total:
            break
    return out


def search_all(queries: list[str], per_query: int = 8, max_total: int = 14,
               region: str = "fr-fr") -> list[dict]:
    """Exécute les requêtes en parallèle, filtre pubs et doublons.

    Repli séquentiel si le parallélisme est ratelimité par DuckDuckGo.
    """
    queries = [q.strip() for q in queries if q and q.strip()][:6]
    if not queries:
        return []

    with ThreadPoolExecutor(max_workers=min(3, len(queries))) as pool:
        batches = list(pool.map(lambda q: search_one(q, per_query, region), queries))

    results = dedupe([item for batch in batches for item in batch],
                     max_total=max_total)
    if not results:  # rate-limit éventuel : on retente séquentiellement
        for query in queries:
            results = dedupe(search_one(query, per_query, region), max_total=max_total)
            if results:
                break
            time.sleep(0.5)
    return results
