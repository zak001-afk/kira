"""Point d'entrée bureau — lance Atlas dans une fenêtre native (pywebview).

Utilisé par le raccourci « E:\\Raccourci-agent\\Atlas.lnk », sur le même
modèle que launch_desktop.py de KIRA :

- pas de console : stdout/stderr sont ajoutés à atlas_launch.log ;
- le serveur Atlas tourne dans un thread de second plan ;
- la fenêtre native EST l'application : la fermer arrête Atlas ;
- le mode navigateur reste disponible avec : python run.py
"""
from __future__ import annotations

import builtins
import datetime
import os
import socket
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HOST = "127.0.0.1"
PORT = 8787

# ── Journal à la place de la console (processus pythonw sans fenêtre) ──────
_log = open(
    os.path.join(ROOT, "atlas_launch.log"),
    "a",
    encoding="utf-8",
    errors="replace",
)


class _LogWriter:
    def __init__(self, original):
        self._original = original

    def write(self, data):
        try:
            _log.write(data)
            _log.flush()
        except Exception:
            pass
        try:
            return self._original.write(data)
        except Exception:
            return 0

    def flush(self):
        try:
            _log.flush()
        except Exception:
            pass
        try:
            return self._original.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._original, name)


_log.write(
    "\n===== Atlas desktop launch %s =====\n"
    % datetime.datetime.now().isoformat(timespec="seconds")
)
_log.flush()

sys.stdout = _LogWriter(sys.stdout)
sys.stderr = _LogWriter(sys.stderr)


def _no_input(prompt=""):
    """Pas de console : ne jamais bloquer sur une invite invisible."""
    print(prompt)
    return ""


builtins.input = _no_input


def _port_alive(host: str = HOST, port: int = PORT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _start_server() -> None:
    from atlas.config import load_config
    from atlas.server import serve

    serve(load_config(), host=HOST, port=PORT)


def main() -> None:
    import webview  # import tardif : le journal est déjà en place

    if _port_alive():
        print(f"Serveur Atlas déjà actif sur {HOST}:{PORT} — réutilisation.")
    else:
        threading.Thread(
            target=_start_server, daemon=True, name="atlas-server"
        ).start()
        for _ in range(100):  # attendre au plus 10 s que le serveur réponde
            if _port_alive():
                break
            time.sleep(0.1)
        else:
            raise SystemExit(
                "le serveur Atlas n'a pas démarré (voir atlas_launch.log)"
            )

    url = f"http://{HOST}:{PORT}"
    webview.create_window(
        "Atlas — Agent de recherche IA",
        url,
        width=1280,
        height=860,
        min_size=(900, 600),
        text_select=True,
    )
    print(f"Fenêtre native Atlas ouverte sur {url}")
    webview.start(debug=False, private_mode=False)
    print("Fenêtre fermée — Atlas s'arrête.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        _log.write("\n[Atlas] launcher terminé avec une erreur — voir ci-dessus.\n")
        _log.flush()
        raise SystemExit(1)
