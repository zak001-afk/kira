"""Lancement bureau de PostPilot — fenêtre native (pywebview), sans console.

Sur le même modèle que launch_desktop.py de KIRA / Atlas :

- stdout/stderr dirigés vers postpilot_launch.log (processus pythonw sans console) ;
- le serveur PostPilot tourne dans un thread de second plan ;
- la fenêtre native EST l'application : la fermer arrête PostPilot ;
- les fenêtres des réseaux (Chrome) restent des fenêtres à part, visibles.
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
PORT = 8790

_log = open(os.path.join(ROOT, "postpilot_launch.log"), "a",
            encoding="utf-8", errors="replace")


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


_log.write("\n===== PostPilot desktop launch %s =====\n"
           % datetime.datetime.now().isoformat(timespec="seconds"))
_log.flush()
sys.stdout = _LogWriter(sys.stdout)
sys.stderr = _LogWriter(sys.stderr)


def _no_input(prompt=""):
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
    from postpilot.server import serve
    serve(host=HOST, port=PORT)


def main() -> None:
    import webview  # import tardif : le journal est déjà en place

    if _port_alive():
        print(f"Serveur PostPilot déjà actif sur {HOST}:{PORT} — réutilisation.")
    else:
        threading.Thread(target=_start_server, daemon=True,
                         name="socia-server").start()
        for _ in range(100):
            if _port_alive():
                break
            time.sleep(0.1)
        else:
            raise SystemExit(
                "le serveur PostPilot n'a pas démarré (voir postpilot_launch.log)"
            )

    url = f"http://{HOST}:{PORT}"
    webview.create_window(
        "PostPilot — Agent de réseaux sociaux",
        url,
        width=1340,
        height=900,
        min_size=(960, 640),
        text_select=True,
    )
    print(f"Fenêtre native PostPilot ouverte sur {url}")
    webview.start(debug=False, private_mode=False)
    print("Fenêtre fermée — PostPilot s'arrête.")

    # propre : ferme les fenêtres de réseaux et Playwright
    try:
        from postpilot import browser
        browser.shutdown()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        _log.write("\n[PostPilot] launcher terminé avec une erreur — voir ci-dessus.\n")
        _log.flush()
        raise SystemExit(1)
