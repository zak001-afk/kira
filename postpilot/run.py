"""Point d'entrée de SOCIA AI : serveur + interface dans le navigateur.

    python run.py                 # serveur + ouvre l'interface
    python run.py --port 8790     # autre port
    python run.py --no-browser    # sans ouvrir le navigateur
"""
from __future__ import annotations

import argparse
import threading
import webbrowser

from postpilot import config, store
from postpilot.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="PostPilot — agent réseaux sociaux")
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--no-browser", action="store_true",
                        help="ne pas ouvrir l'interface automatiquement")
    args = parser.parse_args()

    config.ensure_dirs()
    store.log("PostPilot démarré (mode navigateur).", source="postpilot")

    url = f"http://{args.host}:{args.port}"
    print("=" * 62, flush=True)
    print("  PostPilot — agent autonome de réseaux sociaux", flush=True)
    print(f"  Interface : {url}", flush=True)
    print(f"  Données   : {config.DATA}", flush=True)
    print("  Comptes   : Facebook · Instagram · TikTok", flush=True)
    print("=" * 62, flush=True)

    if not args.no_browser:
        timer = threading.Timer(1.2, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()

    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
