"""Registre des plateformes gérées par SOCIA AI."""
from __future__ import annotations

from . import facebook, instagram, tiktok

MODULES = {
    "facebook": facebook,
    "instagram": instagram,
    "tiktok": tiktok,
}


def get(platform: str):
    return MODULES.get(platform)
