"""Atlas en ligne de commande : une question -> un seul objet JSON sur stdout.

Pont utilisé par KIRA (outil ``atlas_research``) pour déléguer sa recherche à
l'agent Atlas **sans ouvrir l'interface** — le serveur web n'est pas nécessaire :

    E:\\research-agent\\.venv\\Scripts\\python.exe atlas_cli.py "question"

Sortie : une dernière ligne JSON :
    {"ok": true, "answer": "...", "sources": [...], "interpretation": "...",
     "pages": 3, "elapsed": 14.2}
Les journaux (ex. clés cloud réutilisées) peuvent précéder sur stdout ; le
consommateur lit la dernière ligne commençant par « { ».
"""
from __future__ import annotations

import argparse
import json
import sys
import time

# UTF-8 AVANT tout import Atlas : les journaux de configuration imprimés au
# chargement des modules sortiraient sinon en cp1252 (é -> 0xe9) et casseraient
# le décodage du consommateur (KIRA).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from atlas.agent import research_events  # noqa: E402
from atlas.config import load_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas — recherche → JSON")
    parser.add_argument("question", help="question à researcher")
    parser.add_argument("--max-sources", type=int, default=8,
                        help="nombre maximal de sources renvoyées (défaut 8)")
    parser.add_argument("--lang", default="", metavar="CODE",
                        help="langue imposée pour la réponse (fr, en, ar…) — "
                             "la question peut être dans une autre langue")
    args = parser.parse_args()

    question = (args.question or "").strip()
    if not question:
        print(json.dumps({"ok": False, "error": "question vide",
                          "error_code": "empty_question"},
                         ensure_ascii=False))
        return 2

    cfg = load_config()
    t0 = time.time()
    parts: list[str] = []
    sources: list[dict] = []
    interpretation = ""
    pages = 0
    error = ""

    for event in research_events(cfg, question, language=(args.lang or "").strip()):
        kind = event.get("type")
        if kind == "token":
            parts.append(event.get("text", ""))
        elif kind == "sources":
            sources = event.get("items") or sources
        elif kind == "understood":
            interpretation = event.get("text") or ""
        elif kind == "done":
            pages = int(event.get("pages") or 0)
        elif kind == "error":
            error = str(event.get("message") or "erreur inconnue")

    payload: dict = {
        "ok": not error,
        "answer": "".join(parts).strip(),
        "sources": sources[: args.max_sources],
        "interpretation": interpretation,
        "pages": pages,
        "elapsed": round(time.time() - t0, 1),
    }
    if error:
        payload["error"] = error
        payload["error_code"] = "atlas_failed"
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if not error else 1


if __name__ == "__main__":
    raise SystemExit(main())
