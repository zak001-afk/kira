"""Smoke test de demarrage : demarre les serveurs UI+API comme main_window,
sonde /health et /, verifie le contenu, puis arrete proprement."""

import sys
import threading
import time
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0, "src")

from kira import paths
import kira.presentation.kira_ui as kira_ui
import kira.api.kira_api as kira_api

UI_PORT, API_PORT = 8899, 8898

ui_dir = kira_ui.validate_ui_bundle(paths.root_path("ui"))
kira_ui.KiraUIHandler.api_port = API_PORT
api_server = kira_api.start_server(host="127.0.0.1", port=API_PORT, daemon=True)
handler = partial(kira_ui.KiraUIHandler, directory=str(ui_dir))
ui_server = ThreadingHTTPServer(("127.0.0.1", UI_PORT), handler)
thread = threading.Thread(target=ui_server.serve_forever, daemon=True)
thread.start()
time.sleep(0.6)

ok = True
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{API_PORT}/health", timeout=4) as r:
        body = r.read().decode("utf-8", "replace")
        print("health:", r.status, body[:100])
        ok &= r.status == 200
    with urllib.request.urlopen(f"http://127.0.0.1:{UI_PORT}/", timeout=4) as r:
        html = r.read().decode("utf-8", "replace")
        print("index:", r.status, "octets:", len(html))
        print("build:", 'kira-ui-build" content="med-anticlick-01"' in html)
        print("style vert:", 'style.css?v=green-1' in html)
        print("nav sante:", "openView('sante')" in html)
        ok &= r.status == 200 and 'style.css?v=green-1' in html
    with urllib.request.urlopen(f"http://127.0.0.1:{UI_PORT}/style.css?v=green-1", timeout=4) as r:
        css = r.read().decode("utf-8", "replace")
        print("css:", r.status, "octets:", len(css))
        ok &= r.status == 200 and len(css) > 5000
finally:
    ui_server.shutdown()
    ui_server.server_close()
    kira_api.stop_server(api_server)

print("SMOKE:", "OK" if ok else "ECHEC")
sys.exit(0 if ok else 1)
