"""Moteur navigateur visible (Playwright) avec sessions persistantes.

Points clés :
- fenêtres CHACUNE visibles (headless=False) → l'utilisateur suit le travail ;
- profil persistant par plateforme dans data/sessions/<plateforme> :
  les cookies restent, la connexion reste acquise entre deux lancements ;
- **tout** passe par UN SEUL thread : l'API sync de Playwright est liée au
  thread qui l'a lancée, or le serveur HTTP est multi-threads. On utilise un
  ThreadPoolExecutor(max_workers=1) — la file est gérée par la bibliothèque
  standard, pas par une file d'attente maison.
"""
from __future__ import annotations

import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from pathlib import Path
from typing import Any, Callable

from . import config, store

_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="socia-browser")
_lock = threading.RLock()                 # sérialise les opérations navigateur
_contexts: dict[str, Any] = {}            # plateforme -> BrowserContext (thread unique)
_visible: dict[str, bool] = {}            # plateforme -> fenêtre visible (connexion)
_last_windows: list[dict] = []            # cache : /api/state ne bloque jamais
_stale_checked: set[str] = set()
_DEFAULT_TIMEOUT_MS = 25000
_FUTURE_TIMEOUT = 90.0                    # budget total d'une opération

# ── Aperçu en direct (images servies à l'interface SOCIA AI) ────────────────
_screens: dict[str, dict] = {}            # plateforme -> {img, ts, url}
_screen_lock = threading.Lock()
_capture_scheduled: set[str] = set()      # au plus une capture en vol par réseau


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


# ── nettoyage des profils verrouillés ──────────────────────────────────────
def _kill_stale_profile(platform: str) -> None:
    """Ferme les Chrome orphelins qui gardent le verrou DU PROFIL DE CETTE
    plateforme.

    Si le serveur a été tué net, Chrome reste vivant et le lancement suivant
    resterait bloqué. Le marqueur est le dossier du profil lui-même
    (data\\sessions\\<plateforme>) : on ne touche JAMAIS aux fenêtres des
    autres réseaux — ouvrir Instagram ne doit pas fermer Facebook.
    """
    if platform in _stale_checked:
        return
    marker = str(config.SESSIONS / platform)
    if not Path(marker).exists():
        _stale_checked.add(platform)
        return
    try:
        script = (
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            "Where-Object { $_.CommandLine -like '*" + marker + "*' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=20,
        ).stdout or ""
        pids = [p.strip() for p in out.replace("\r", "\n").split("\n")
                if p.strip().isdigit()]
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid],
                           capture_output=True, timeout=10)
        if pids:
            import time
            time.sleep(1.5)
            store.log(f"{len(pids)} fenêtre(s) orpheline(s) fermée(s) — "
                      f"profil {platform} libéré.", source="navigateur")
    except Exception:
        pass
    _stale_checked.add(platform)


# ── fenêtres (exécuté sur le thread unique) ────────────────────────────────
def _pw():
    from playwright.sync_api import sync_playwright
    if not hasattr(_pw, "_inst"):
        _pw._inst = sync_playwright().start()
    return _pw._inst


def _open_window_locked(platform: str, url: str | None = None,
                         visible: bool = False):
    """(context, page) — UNIQUEMENT sur le thread navigateur.

    Par défaut ``visible=False`` : la fenêtre s'ouvre EN ARRIÈRE-PLAN
    (sans pop-up) et se suit dans l'aperçu intégré de l'interface SOCIA AI.
    ``visible=True`` uniquement quand l'utilisateur clique pour se
    connecter lui-même — une fenêtre d'arrière-plan existante est alors
    relancée visible.
    """
    ctx = _contexts.get(platform)
    if ctx is not None and visible and not _visible.get(platform, False):
        # l'utilisateur veut VOIR la fenêtre (connexion) : on la relance
        _visible[platform] = False
        forget_frame(platform)
        try:
            ctx.close()
        except Exception:
            pass
        _contexts.pop(platform, None)
        ctx = None
    if ctx is not None:
        try:
            page = ctx.pages[-1] if ctx.pages else ctx.new_page()
            if url:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return ctx, page
        except Exception:
            _contexts.pop(platform, None)
            _visible.pop(platform, None)
            forget_frame(platform)
            try:
                ctx.close()
            except Exception:
                pass

    profile = config.SESSIONS / platform
    profile.mkdir(parents=True, exist_ok=True)
    _kill_stale_profile(platform)
    ctx = _pw().chromium.launch_persistent_context(
        user_data_dir=str(profile),
        channel="chrome",                 # utilise Chrome/Edge déjà installés
        headless=not visible,             # en arrière-plan par défaut
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx.set_default_timeout(_DEFAULT_TIMEOUT_MS)
    _contexts[platform] = ctx
    _visible[platform] = visible
    page = ctx.pages[-1] if ctx.pages else ctx.new_page()
    page.goto(url or config.HOME_URLS.get(platform, "about:blank"),
              wait_until="domcontentloaded", timeout=30000)
    return ctx, page


# ── exécution ──────────────────────────────────────────────────────────────
def _call(fn: Callable, timeout: float = _FUTURE_TIMEOUT) -> Any:
    """Exécute fn() sur le thread navigateur et renvoie son résultat."""
    if not available():
        raise RuntimeError("Playwright n'est pas installé (pip install playwright)")
    fut = _EXEC.submit(fn)
    try:
        result = fut.result(timeout=timeout)
    except FutTimeout:
        raise TimeoutError(f"opération navigateur trop longue (> {timeout:.0f}s)")
    if isinstance(result, BaseException):
        raise result
    return result


def with_page(platform: str, fn: Callable, visible: bool = False,
              timeout: float = _FUTURE_TIMEOUT) -> Any:
    """Exécute fn(page) avec la fenêtre de la plateforme ouverte.

    ``visible=True`` pour que l'utilisateur VOIE le travail de l'agent
    (ex. suivre la publication dans un groupe).    ``timeout`` = budget total
    de l'opération : les campagnes multi-liens (199 cibles × publication +
    pauses) dépassent largement les 90 s par défaut → l'appelant d'une
    opération longue (publication) DOIT passer un budget à la hauteur du
    nombre de cibles.
    """
    with _lock:
        def _job():
            _, page = _open_window_locked(platform, visible=visible)
            return fn(page)
        return _call(_job, timeout=timeout)


def open_window_now(platform: str, url: str | None = None,
                     visible: bool = False) -> None:
    """Ouvre la fenêtre d'une plateforme — en arrière-plan par défaut,
    visible sur demande explicite (connexion de l'utilisateur)."""
    with _lock:
        _call(lambda: _open_window_locked(platform, url, visible))


def close_window(platform: str) -> bool:
    with _lock:
        def _job():
            ctx = _contexts.pop(platform, None)
            _visible.pop(platform, None)
            if ctx is None:
                return False
            try:
                ctx.close()
            except Exception:
                pass
            return True
        ok = _call(_job, timeout=20)
    if ok:
        forget_frame(platform)
        store.log(f"Fenêtre {config.PLATFORM_LABELS.get(platform, platform)} fermée.",
                  source="navigateur")
    return bool(ok)


def close_all() -> None:
    global _last_windows
    with _lock:
        def _job():
            for p in list(_contexts):
                ctx = _contexts.pop(p, None)
                _visible.pop(p, None)
                if ctx is not None:
                    try:
                        ctx.close()
                    except Exception:
                        pass
            return True
        try:
            _call(_job, timeout=20)
        except Exception:
            _contexts.clear()
        _last_windows = []


def windows_status() -> list[dict]:
    """Statut des fenêtres — ne bloque jamais l'API.

    Si une opération est en cours, renvoie le dernier état connu.
    """
    global _last_windows
    if not _lock.acquire(timeout=0.4):
        return _last_windows
    try:
        def _job():
            out = []
            for p in list(_contexts):
                ctx = _contexts[p]
                try:
                    if not ctx.pages or ctx.pages[0].is_closed():
                        _contexts.pop(p, None)
                        forget_frame(p)          # plus de fenêtre → plus d'image
                        continue
                except Exception:
                    _contexts.pop(p, None)
                    forget_frame(p)
                    continue
                titles = []
                urls = []
                for pg in ctx.pages:
                    try:
                        titles.append((pg.title() or "")[:80])
                    except Exception:
                        pass
                    try:
                        urls.append(str(pg.url or "")[:200])
                    except Exception:
                        pass
                out.append({"platform": p, "pages": len(ctx.pages),
                            "titles": titles, "urls": urls,
                            "visible": _visible.get(p, False)})
            return out
        try:
            _last_windows = _call(_job, timeout=6) or []
        except Exception:
            return _last_windows
        for w in _last_windows:              # aperçu toujours à jour
            request_capture(w.get("platform") or "")
        return _last_windows
    finally:
        _lock.release()


def screenshot(page, name: str):
    """Capture l'état de la fenêtre (appelé depuis le thread navigateur)."""
    try:
        config.SHOTS.mkdir(parents=True, exist_ok=True)
        path = config.SHOTS / f"{name}.png"
        page.screenshot(path=str(path))
        return str(path)
    except Exception:
        return None


# ── Aperçu en direct dans l'interface ───────────────────────────────────────
def store_frame(platform: str, page) -> bool:
    """Photographie la page pour l'aperçu intégré de SOCIA AI.

    UNIQUEMENT depuis le thread navigateur (ex. au milieu d'une publication).
    Ne lève JAMAIS d'exception et ne doit jamais faire échouer la publication.
    """
    try:
        data = page.screenshot(type="jpeg", quality=55, timeout=3000)
    except Exception:
        return False
    try:
        url = str(page.url or "")[:200]
    except Exception:
        url = ""
    if not data:
        return False
    with _screen_lock:
        _screens[platform] = {"img": data, "ts": time.time(), "url": url}
    return True


def request_capture(platform: str) -> None:
    """Planifie une capture (appelable depuis n'importe quelle thread).

    N'est jamais mis en file derrière une publication : au plus UNE capture
    en attente par plateforme, donc l'aperçu ne ralentit jamais le travail.
    """
    if platform not in _contexts:
        return
    with _screen_lock:
        if platform in _capture_scheduled:
            return
        _capture_scheduled.add(platform)

    def _job():
        with _screen_lock:
            _capture_scheduled.discard(platform)
        ctx = _contexts.get(platform)
        if ctx is None:
            return
        try:
            page = ctx.pages[-1] if ctx.pages else None
        except Exception:
            return
        if page is not None:
            store_frame(platform, page)

    try:
        _EXEC.submit(_job)
    except Exception:
        with _screen_lock:
            _capture_scheduled.discard(platform)


def frame(platform: str) -> dict | None:
    """Dernière image disponible pour une plateforme (ou None)."""
    with _screen_lock:
        item = _screens.get(platform)
        return dict(item) if item else None


def forget_frame(platform: str) -> None:
    with _screen_lock:
        _screens.pop(platform, None)


def shutdown() -> None:
    try:
        close_all()
    except Exception:
        pass
    try:
        _call(lambda: (_pw().stop(), setattr(_pw, "_inst", None)), timeout=15)
    except Exception:
        pass
    _EXEC.shutdown(wait=False)


def diagnose() -> dict:
    info = {"playwright": available(), "chrome": False, "detail": ""}
    import os
    for exe in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ):
        if os.path.exists(exe):
            info["chrome"] = True
            info["detail"] = exe
            break
    return info
