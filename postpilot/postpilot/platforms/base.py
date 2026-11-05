"""Aides communes aux modules de plateformes (sélecteurs tolérants)."""
from __future__ import annotations

import re
import time

LOGIN_HINTS = re.compile(r"/login|/accounts/login|/auth|signin|log_in", re.I)


def first(page, selectors, timeout: int = 4000):
    """Retourne le premier sélecteur qui correspond, sinon None.

    Chaque sélecteur peut être une chaîne Playwright classique.
    """
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=timeout):
                return loc
        except Exception:
            continue
    return None


def click_first(page, selectors, timeout: int = 4000) -> bool:
    loc = first(page, selectors, timeout=timeout)
    if loc is None:
        return False
    try:
        loc.click(timeout=timeout)
        return True
    except Exception:
        return False


def looks_logged_out(page) -> bool:
    """Heuristique : formulaire de connexion visible ou URL de login."""
    try:
        url = page.url or ""
    except Exception:
        return True
    if LOGIN_HINTS.search(url):
        return True
    for sel in ('input[name="pass"]', 'input[name="email"]',
                'input[name="username"]',
                'input[autocomplete="current-password"]',
                'button:has-text("Se connecter")',
                'button:has-text("Log in")',
                'button:has-text("Connexion")'):
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=1500):
                return True
        except Exception:
            continue
    return False


def type_into(page, selectors, text: str, timeout: int = 6000) -> bool:
    loc = first(page, selectors, timeout=timeout)
    if loc is None:
        return False
    try:
        loc.click(timeout=timeout)
        loc.fill("", timeout=timeout)
    except Exception:
        pass
    try:
        loc.type(text, delay=12)          # tape « à la main » : plus naturel
        return True
    except Exception:
        try:
            loc.fill(text, timeout=timeout)
            return True
        except Exception:
            return False


def wait_stable(page, ms: int = 1500) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    time.sleep(ms / 1000)
