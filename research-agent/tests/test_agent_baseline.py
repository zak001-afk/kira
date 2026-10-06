"""Test de régression — étape 2 et `baseline` doivent s'exécuter TOUJOURS.

Bug corrigé : `baseline = baseline_fut.result()` et l'étape « Recherche sur le
web » étaient indentés dans le `if interpretation ...` (bloc « compris »).
Résultat : dès que l'interprétation était identique à la question (texte déjà
correct), `baseline` n'était jamais assigné et le pipeline plantait avec
« cannot access local variable 'baseline' ... ».

Exécution (sans réseau ni LLM, les sorties sont simulées) :

    python tests/test_agent_baseline.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import atlas.agent as A  # noqa: E402
from atlas.config import load_config  # noqa: E402

QUESTION = "bonjour accueil aide en ligne"


def _fake_results(n: int = 10) -> list[dict]:
    return [
        {"title": f"T{i}", "url": f"https://ex{i}.org/a",
         "host": f"ex{i}.org", "snippet": "s"}
        for i in range(n)
    ]


# Sorties simulées : le test ne touche ni le réseau ni Gemini.
A.search_all = lambda qs, per_query=1, max_total=10: _fake_results(
    min(max_total, 10))
A.fetch_pages = lambda results, max_pages=1, page_chars=1: [
    {"url": r["url"], "text": "texte"} for r in results[:max_pages]]
A._synthesize = lambda cfg, make_messages, emit_step4: iter(
    [{"type": "token", "text": "ok"}])

CFG = load_config()


def run(label: str, interpretation: str) -> None:
    A.plan_question = lambda cfg, q: (interpretation, [QUESTION])
    events = list(A.research_events(CFG, QUESTION))
    errors = [e for e in events if e["type"] == "error"]
    assert not errors, f"{label} : ÉCHEC — {errors[0]['message']}"
    steps = {(e["id"], e["state"]) for e in events if e["type"] == "step"}
    assert (2, "run") in steps, f"{label} : étape 2 « run » absente"
    assert (2, "done") in steps, f"{label} : étape 2 « done » absente"
    assert "sources" in (e["type"] for e in events), f"{label} : pas de sources"
    assert "done" in (e["type"] for e in events), f"{label} : pas de fin « done »"
    print(f"OK — {label} : étape 2 présente, sources, done, 0 erreur")


def main() -> None:
    # Les trois cas ci-dessous tombaient dans le bug (branchement « compris »).
    run("interprétation identique à la question", QUESTION)
    run("interprétation vide", "")
    run("interprétation différente (bloc compris)", "Comment aller à l'accueil ?")
    print("TOUS LES TESTS PASSENT")


if __name__ == "__main__":
    main()
