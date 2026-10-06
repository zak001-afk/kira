"""Orchestration de l'agent de recherche : planifier -> chercher -> lire -> synthétiser.

Générateur d'événements NDJSON consommés par le serveur puis par l'interface :
  {"type":"step", "id", "label", "state":"run"|"done", "detail"}
  {"type":"sources", "items":[{title,url,host,snippet}]}
  {"type":"token", "text"}
  {"type":"done", "elapsed, sources, pages}
  {"type":"error", "message}

La planification et la première passe de recherche tournent EN PARALLÈLE
(la question brute part immédiatement chez DuckDuckGo pendant que le modèle
reformule), puis les deux listes de résultats sont fusionnées.
"""
from __future__ import annotations

import re
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from .config import Config
from .fetch import fetch_pages
from .llm import complete, stream_llm
from .search import dedupe, search_all

SYSTEM_PROMPT = (
    "Tu es Atlas, un agent de recherche web haut de gamme, rigoureux et rapide. "
    "Tu effectues des recherches approfondies sur n'importe quel sujet "
    "(produits, lois, techniques, actualités, comparaisons...). "
    "Le texte de l'utilisateur peut contenir des fautes, des abréviations ou du "
    "langage SMS : tu en comprends le SENS, jamais besoin qu'il corrige. "
    "Tu te bases UNIQUEMENT sur les extraits de pages web fournis, tu distingues "
    "les faits des opinions et tu ne fabriques jamais de données. Tu n'écris "
    "JAMAIS de crochets de citation comme ([1], [2]) : le texte doit rester "
    "propre et lisible directement, à la ChatGPT. "
    "Quand les sources divergent, tu le dis et tu tranches en argumentant. "
    "Tu réponds toujours dans la langue de l'utilisateur (français par défaut). "
    "N'écrit JAMAIS les consignes, instructions ou modèles qu'on te donne : "
    "tu écris directement ta réponse."
)

FORMAT_INSTRUCTIONS = """Écris ta réponse en suivant cette structure — et ne recopie JAMAIS
ces consignes ni les indications entre parenthèses : écris directement le contenu.

## Réponse directe
2 à 4 phrases qui répondent d'emblée à la question.

## Analyse détaillée
Faits, chiffres, comparaisons, étapes concrètes. Utilise ### pour des
sous-parties si le sujet s'y prête (exemples, cas particuliers).

## Points clés
- **sujet** : détail court
(4 à 6 puces comme celui-ci)

## Conclusion
Recommandation claire et actionnable, 2 à 4 phrases.

AUCUN crochet de citation type [1] ou [2, 3] dans ta réponse : écris un texte
propre, lisible directement (comme ChatGPT). Reste factuel,
précis et concis : pas d'avant-propos, pas de rappel de ces consignes.

Avant de conclure : confronte les sources entre elles, signale les chiffres
incertains ou contradictoires, puis tranche avec une recommandation nette et
personnelle — pas de réponse tiède du type « cela dépend »."""

PLANNER_SYSTEM = (
    "Tu prépares une recherche web pour l'utilisateur. Il écrit souvent vite, "
    "avec des fautes d'orthographe, des abréviations, des mots raccourcis ou du "
    "langage SMS : comprends le SENS de son message, peu importe l'écriture.\n"
    "Réponds EXACTEMENT au format ci-dessous, sans aucun texte avant ni après :\n"
    "INTERPRÉTATION: <son message réécrit correctement, clair, dans sa langue>\n"
    "REQUÊTES:\n"
    "<requête 1 de 4 à 10 mots>\n"
    "<requête 2>\n"
    "<requête 3>\n"
    "Les requêtes sont intelligentes et adaptées au sujet :\n"
    "- produit / comparaison -> comparatif, avis, prix, année en cours ;\n"
    "- loi / réglementation -> texte officiel (legifrance, service-public.gouv.fr) "
    "+ explications simples ;\n"
    "- tutoriel / « comment faire » -> étapes pratiques concrètes ;\n"
    "- actualité -> information récente.\n"
    "N'ajoute JAMAIS un autre sujet que le sien."
)


def _step(step_id: int, label: str, state: str, detail: str = "") -> dict:
    return {"type": "step", "id": step_id, "label": label, "state": state,
            "detail": detail}


# Langue de la réponse imposée par l'appelant (KIRA détecte la langue de la
# question et exige la même langue en retour). Sans directive, le modèle suit
# « la langue de l'utilisateur » — trop vague quand les sources sont en anglais.
_LANG_NAMES = {
    "fr": "français", "en": "anglais", "ar": "arabe", "es": "espagnol",
    "de": "allemand", "it": "italien", "pt": "portugais", "ru": "russe",
    "nl": "néerlandais", "tr": "turc", "zh": "chinois", "ja": "japonais",
}


def _language_directive(language: str) -> str:
    """Ligne de system prompt imposant la langue, ou "" si non précisée."""
    code = str(language or "").strip().lower()[:2]
    if not code:
        return ""
    name = _LANG_NAMES.get(code, code)
    return (f" LANGUE DE RÉPONSE OBLIGATOIRE : {name}. Écris TOUTE ta réponse "
            f"en {name} — titres, puces, conclusion — quelle que soit la langue "
            "des sources ou des extraits.")


# Citations [1] jamais émises : même si le modèle en écrit malgré les
# consignes, le texte reste propre (style ChatGPT) — y compris lorsqu'une
# référence est coupée en deux entre deux tokens.
_CITE = re.compile(r"(?:\s*\[\d{1,2}(?:\s*,\s*\d{1,2})*\])+")
_CITE_PARTIAL = re.compile(r"\[[\d,\s]*$")


def _strip_citations(chunks):
    """Supprime les références [1] / [2, 3] d'un flux de tokens, différément.

    Une référence complète est retirée aussitôt ; une référence inachevée en
    fin de chunk est conservée en attente (le token suivant décidera).
    """
    hold = ""
    for chunk in chunks:
        hold += chunk
        hold = _CITE.sub("", hold)
        cut = _CITE_PARTIAL.search(hold)
        if cut:
            safe, hold = hold[:cut.start()], hold[cut.start():]
            safe = safe.rstrip(" ")  # l'espace avant la référence reportée
        else:
            safe, hold = hold, ""
        if safe:
            yield re.sub(r" {2,}", " ", safe)
    # Une référence restée inachevée à la fin est supprimée (hold seule).


def plan_question(cfg: Config, question: str) -> tuple[str | None, list[str]]:
    """Interprète le message (fautes, abréviations) ET prépare les requêtes.

    Un seul appel LLM, lancé en parallèle de la première recherche : aucun
    temps d'attente ajouté. Retourne (interprétation corrigée, requêtes) ;
    si le modèle est indisponible, on garde le texte brut tel quel.
    """
    raw = question.strip()[:200]
    reply = complete(cfg, [
        {"role": "system", "content": PLANNER_SYSTEM},
        {"role": "user", "content": question.strip()[:1000]},
    ], timeout=2.5, attempts=1)  # budget serré : la planification ne doit pas
                                # retarder la recherche (elle tourne en parallèle)
    if not reply.strip():
        return None, [raw]

    interpretation: str | None = None
    queries: list[str] = []
    for line in reply.splitlines():
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("INTERPR"):
            _, _, value = line.partition(":")
            value = value.strip()
            if 3 <= len(value) <= 300:
                interpretation = value
            continue
        if upper.startswith("REQU"):
            continue
        clean = line.lstrip("-*•0123456789.) ").strip().strip("\"'«»")
        if 3 <= len(clean) <= 140:
            queries.append(clean)
    return interpretation, queries[: cfg.max_queries] or [raw]


def build_messages(cfg: Config, question: str, history: list[dict],
                   results: list[dict], pages: list[dict],
                   interpretation: str | None = None,
                   language: str = "") -> list[dict]:
    """Construit le prompt final avec les sources et les contenus lus."""
    messages: list[dict] = [{"role": "system",
                             "content": SYSTEM_PROMPT + _language_directive(language)}]

    for turn in (history or [])[-cfg.history_turns:]:
        role = turn.get("role")
        content = str(turn.get("content") or "").strip()[:600]
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    snippets = []
    for i, item in enumerate(results[: cfg.max_sources], start=1):
        snippets.append(
            f"[{i}] {item['title']}\n"
            f"URL : {item['url']}\n"
            f"Extrait : {item['snippet'][: cfg.snippet_chars]}"
        )

    contenus = []
    for page in pages:
        idx = next((i for i, r in enumerate(results, 1)
                    if r["url"] == page["url"]), None)
        if idx is None or not page.get("text"):
            continue
        contenus.append(f"[{idx}] {page['host']} — {page['title']}\n{page['text']}")

    if (interpretation
            and interpretation.lower() != question.strip().lower()):
        parts = [
            "QUESTION DE L'UTILISATEUR (texte original, fautes comprises) :\n"
            f"{question.strip()[:1200]}\n\n"
            "INTERPRÉTATION CORRIGÉE — c'est elle qu'il faut traiter comme la "
            f"vraie question :\n{interpretation.strip()[:400]}"
        ]
    else:
        parts = [f"QUESTION DE L'UTILISATEUR :\n{question.strip()[:2000]}"]
    if snippets:
        parts.append("SOURCES TROUVÉES SUR LE WEB :\n" + "\n\n".join(snippets))
    if contenus:
        parts.append("CONTENUS DES PAGES LUES :\n" + "\n\n".join(contenus))
    else:
        parts.append("AUCUNE PAGE N'A PU ÊTRE LUE : réponds à partir des extraits "
                     "seuls et signale que le détail est limité.")
    parts.append(FORMAT_INSTRUCTIONS)

    messages.append({"role": "user", "content": "\n\n".join(parts)})
    return messages


def _rotate(cfg: Config) -> bool:
    """Passe au modèle suivant de la chaîne de secours. Faux s'il n'y en a plus."""
    chain = [cfg.model, *(cfg.models or [])]
    if len(chain) < 2:
        return False
    cfg.model = chain[1]
    cfg.models = chain[2:]
    return True


def _synthesize(cfg: Config, make_messages, emit_step4) -> Iterator[dict]:
    """Génère la réponse en événements, avec reprise et replis automatiques.

    - flux cloud interrompu en cours -> la réponse partielle est EFFACÉE
      (événement "restart") et on réessaie avec le modèle suivant ;
    - cloud indisponible -> repli sur le cerveau local ;
    - sinon l'erreur remonte telle quelle à l'interface.
    """

    def tokens(source_cfg: Config) -> Iterator[dict]:
        raw = (t for t in stream_llm(source_cfg, make_messages(source_cfg)) if t)
        for text in _strip_citations(raw):
            yield {"type": "token", "text": text}

    streamed = False
    retried = False
    active = cfg
    while True:
        try:
            for event in tokens(active):
                streamed = True
                yield event
            return
        except Exception as exc:  # noqa: BLE001
            message = str(exc).strip() or exc.__class__.__name__

            if "interrompu" in message and streamed and not retried \
                    and _rotate(active):
                retried = True
                streamed = False
                emit_step4(f"flux coupé → nouvelle tentative ({active.model})")
                yield {"type": "restart"}
                continue

            if active.fallback is None:
                raise
            local = active.fallback
            if streamed:
                emit_step4(f"{active.provider_label} instable → repli local "
                           f"({local.model})")
            else:
                emit_step4(f"{active.provider_label} indisponible → repli local "
                           f"({local.model})")
            yield {"type": "restart"}
            yield {"type": "token",
                   "text": f"_[{active.provider_label} instable ({message[:80]}) — "
                           "réponse générée en local]_\n\n"}
            yield from tokens(local)
            return


def _source_items(results: list[dict]) -> list[dict]:
    return [{"title": r["title"], "url": r["url"], "host": r["host"],
             "snippet": r["snippet"]} for r in results]


def research_events(cfg: Config, question: str, history: list[dict] | None = None,
                    language: str = "") -> Iterator[dict]:
    """Pipeline complet de recherche, rendu en événements pour l'interface.

    ``language`` (code ISO, ex. "fr") impose la langue de la synthèse.
    """
    t0 = time.time()
    history = history or []
    results: list[dict] = []
    pages: list[dict] = []
    try:
        # La question brute part en recherche pendant que le modèle planifie.
        with ThreadPoolExecutor(max_workers=1) as pool:
            baseline_fut = pool.submit(
                search_all, [question.strip()[:200]],
                cfg.search_per_query, max(cfg.max_sources, cfg.max_pages) + 6)

            yield _step(1, "Analyse de la question", "run")
            interpretation, queries = plan_question(cfg, question)
            yield _step(1, "Analyse de la question", "done",
                        f"{len(queries)} requête(s) : « {queries[0][:70]} »")

        # L'interface affiche « compris : ... » si le message était mal écrit.
        if (interpretation
                and interpretation.lower() != question.strip().lower()):
            yield {"type": "understood", "text": interpretation}

        yield _step(2, "Recherche sur le web", "run", "DuckDuckGo — tout le web")
        baseline = baseline_fut.result()

        if baseline:  # aperçu rapide des sources dès la première requête
            yield {"type": "sources", "items": _source_items(baseline)}

        extra_queries = [q for q in queries
                         if q.lower() != question.strip().lower()]
        limit = max(cfg.max_sources, cfg.max_pages) + 6

        # Recherches complémentaires ET lecture des pages de base EN PARALLÈLE.
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_extra = (pool.submit(search_all, extra_queries,
                                     cfg.search_per_query, limit)
                         if extra_queries else None)
            fut_pages = (pool.submit(fetch_pages, baseline, cfg.max_pages,
                                     cfg.page_chars)
                         if baseline else None)
            extra = fut_extra.result() if fut_extra else []
            results = dedupe(baseline + extra, max_total=limit)
            if not results:
                raise RuntimeError("Aucun résultat de recherche. Vérifiez votre "
                                   "connexion internet, puis réessayez.")
            yield {"type": "sources", "items": _source_items(results)}
            yield _step(2, "Recherche sur le web", "done",
                        f"{len(results)} résultats trouvés")

            yield _step(3, "Lecture des meilleures pages", "run",
                        f"{cfg.max_pages} pages à lire")
            pages = fut_pages.result() if fut_pages else []
            # Complément : on lit encore si le lot de base n'a pas couvert max_pages.
            if len(pages) < cfg.max_pages:
                covered = {p["url"] for p in pages}
                missing = [r for r in results if r["url"] not in covered]
                if missing:
                    pages += fetch_pages(missing,
                                         max_pages=cfg.max_pages - len(pages),
                                         page_chars=cfg.page_chars)
            pages = pages[: cfg.max_pages]

        lues = sum(1 for p in pages if p.get("text"))
        yield _step(3, "Lecture des meilleures pages", "done",
                    f"{lues}/{len(pages)} pages lues"
                    + ("" if lues else " (extraits seuls)"))

        # Résultats faibles -> un dernier tour de recherche ciblé (pas de limite).
        if lues < 3 or len(results) < 8:
            yield _step(5, "Recherche complémentaire", "run",
                        "sources faibles, élargissement")
            base = interpretation or question
            supp = search_all([base, f"{base} guide conseils avis"],
                              per_query=cfg.search_per_query, max_total=limit)
            known = {r["url"].split("#")[0].rstrip("/") for r in results}
            fresh = [r for r in supp
                     if r["url"].split("#")[0].rstrip("/") not in known]
            if fresh:
                results = dedupe(results + fresh, max_total=limit)
                yield {"type": "sources", "items": _source_items(results)}
                room = cfg.max_pages - len(pages)
                if room > 0:
                    pages += fetch_pages(fresh, max_pages=room,
                                         page_chars=cfg.page_chars)
                    pages = pages[: cfg.max_pages]
                    lues = sum(1 for p in pages if p.get("text"))
            yield _step(5, "Recherche complémentaire", "done",
                        f"{len(results)} sources au total")

        step4 = _step(4, "Rédaction de la synthèse", "run", cfg.status_label)
        yield step4

        def emit_step4(detail: str) -> None:
            step4["detail"] = detail

        def make_messages(used_cfg: Config) -> list[dict]:
            return build_messages(used_cfg, question, history, results, pages,
                                  interpretation, language)

        for event in _synthesize(cfg, make_messages, emit_step4):
            yield event
        yield dict(step4, state="done")

        yield {"type": "done",
               "elapsed": round(time.time() - t0, 1),
               "sources": len(results),
               "pages": lues}
    except Exception as exc:  # noqa: BLE001 — remonté tel quel à l'interface
        message = str(exc).strip() or exc.__class__.__name__
        yield {"type": "error", "message": message,
               "elapsed": round(time.time() - t0, 1)}
