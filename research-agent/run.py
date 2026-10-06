"""Point d'entrée d'Atlas : lance le serveur et ouvre l'interface.

    python run.py                # serveur + navigateur
    python run.py --port 9000    # autre port
    python run.py --no-browser   # sans ouvrir le navigateur
"""
from __future__ import annotations

import argparse
import threading
import webbrowser

from atlas.config import load_config
from atlas.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlas — agent de recherche web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true",
                        help="ne pas ouvrir le navigateur automatiquement")
    args = parser.parse_args()

    cfg = load_config()
    url = f"http://{args.host}:{args.port}"
    print("=" * 60, flush=True)
    print(f"  {cfg.name} — agent de recherche web", flush=True)
    print(f"  Cerveau : {cfg.status_label}", flush=True)
    print("  Recherche : DuckDuckGo (tout le web, sans clé API)", flush=True)
    print(f"  Interface : {url}", flush=True)
    print("=" * 60, flush=True)

    if not args.no_browser:
        timer = threading.Timer(1.2, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()

    serve(cfg, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
