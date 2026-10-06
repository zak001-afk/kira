#!/usr/bin/env python3
"""Génère les deux visuels de fond consommés par ``ui/``.

``ui/assets/circuit-board.webp``
    Fond « PCB » vert qui remplace la pluie de glyphes Matrix : c'est le décor
    plein écran visible sur la maquette (traces, vias, puces, points lumineux).

``ui/assets/avatar-cutout.webp``
    Portrait de KIRA détouré : l'anneau lumineux, le visage et le socle
    holographique sont conservés, l'extérieur (la pluie de glyphes) devient
    transparent pour laisser voir le circuit imprimé.

Re-générer avec :  python scripts/gen_ui_assets.py
Déterministe (graine fixe) : deux exécutions produisent des octets identiques.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "ui" / "assets"

# ── Fond circuit imprimé ─────────────────────────────────────────────────────
W, H = 2560, 1440
SEED = 2050
GRID = 32  # pas de routage : toutes les traces s'alignent sur cette grille

BASE = (3, 7, 5)
TRACE = (22, 86, 34)
TRACE_GLOW = (6, 36, 14)
VIA_EDGE = (38, 130, 50)
BRIGHT = (120, 240, 120)

# ── Portrait détouré ─────────────────────────────────────────────────────────
# Mesurées sur ui/assets/avatar-natural.webp (1024 × 1024) : cercle de l'anneau
# (sommet du cercle observé en x=512, y=32 -> cy - r = 32) et zone occupée par
# le faisceau + le socle holographique.
RING = {"cx": 512, "cy": 366, "r": 334}
RING_MARGIN = 20  # l'anneau et sa lueur doivent rester entièrement dedans
MASK_FEATHER = 12  # fondu : la pluie de glyphes se dissout au lieu d'être coupée
CONE = [(444, 604), (580, 604), (716, 820), (308, 820)]
BASE_ELLIPSE = (512, 878, 352, 128)  # centre x, centre y, rayon x, rayon y


# Routage Manhattan (axes) avec quelques coupes à 45°, comme une carte mère.
_ORTHO = [(1, 0), (-1, 0), (0, 1), (0, -1)]
_DIAG = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def _polylines(rnd: random.Random, count: int) -> list[list[tuple[float, float]]]:
    """Traces alignees sur GRID : longues tranches paralleles, coudes a 90 deg."""
    paths = []
    cols, rows = max(1, W // GRID), max(1, H // GRID)
    for _ in range(count):
        x = rnd.randrange(cols) * GRID
        y = rnd.randrange(rows) * GRID
        dx, dy = rnd.choice(_ORTHO)
        pts = [(float(x), float(y))]
        for _ in range(rnd.randrange(3, 8)):
            if rnd.random() < 0.25:
                sx, sy = rnd.choice(_DIAG)
                length = rnd.randrange(1, 4) * GRID
            else:
                sx, sy = dx, dy
                length = rnd.randrange(3, 10) * GRID
            nx, ny = x + sx * length, y + sy * length
            if not (0 <= nx <= W and 0 <= ny <= H):
                # Hors plan : demi-tour plutot que de couper la trace.
                nx, ny = x - sx * length, y - sy * length
                if not (0 <= nx <= W and 0 <= ny <= H):
                    break
            pts.append((float(nx), float(ny)))
            x, y = nx, ny
            dx, dy = (dy, -dx) if rnd.random() < 0.5 else (-dy, dx)
        if len(pts) > 2:
            paths.append(pts)
    return paths


def _vignette(image: Image.Image) -> Image.Image:
    """Assombrit les bords (lisibilité du HUD) et écrase la luminosité globale.

    Le fond doit rester un fond : sans cette atténuation le circuit imprimé
    rivalise avec le portrait et les panneaux.
    """
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([-W * 0.24, -H * 0.38, W * 1.24, H * 1.38], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(200))
    level = mask.point(lambda v: 27 + v * 112 // 255)
    darkened = ImageChops.multiply(image, Image.merge("RGB", (level, level, level)))
    # Halo doux derrière la tête : le centre du décor reste légèrement vivant.
    halo = Image.new("L", (W, H), 0)
    hd = ImageDraw.Draw(halo)
    hd.ellipse([W * 0.24, H * 0.05, W * 0.76, H * 0.95], fill=64)
    halo = halo.filter(ImageFilter.GaussianBlur(220))
    lit = ImageChops.screen(
        darkened,
        Image.merge("RGB", (halo.point(lambda v: v // 5),) * 3),
    )
    return lit


def build_backdrop(rnd: random.Random) -> Image.Image:
    board = Image.new("RGB", (W, H), BASE)
    grid = ImageDraw.Draw(board)
    for x in range(0, W + 1, GRID * 2):
        grid.line([(x, 0), (x, H)], fill=(6, 11, 8), width=1)
    for y in range(0, H + 1, GRID * 2):
        grid.line([(0, y), (W, y)], fill=(6, 11, 8), width=1)

    paths = _polylines(rnd, 72)

    # Halo des traces (calque séparé flouté, puis « screen » sur le fond).
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for pts in paths:
        gd.line(pts, fill=TRACE_GLOW, width=5, joint="curve")
    board = ImageChops.screen(board, glow.filter(ImageFilter.GaussianBlur(12)))

    draw = ImageDraw.Draw(board)
    for pts in paths:
        draw.line(pts, fill=TRACE, width=2, joint="curve")

    # Vias : un seul tous les quatre tracés, pour ne pas semer des ronds partout.
    for pts in paths[::4]:
        for x, y in (pts[0], pts[-1]):
            draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill=BASE, outline=VIA_EDGE, width=2)
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=VIA_EDGE)

    # Puces (rectangles a broches) : peu et grandes, pour laisser du noir.
    for _ in range(6):
        cw = rnd.randrange(200, 420)
        ch = rnd.randrange(120, 300)
        x = rnd.randrange(20, W - cw - 20)
        y = rnd.randrange(20, H - ch - 20)
        draw.rounded_rectangle([x, y, x + cw, y + ch], radius=8, fill=(4, 9, 6), outline=(16, 62, 24), width=2)
        for pin in range(6, cw - 20, 40):
            draw.line([(x + pin, y - 10), (x + pin, y)], fill=(16, 62, 24), width=2)
            draw.line([(x + pin, y + ch), (x + pin, y + ch + 10)], fill=(16, 62, 24), width=2)

    # Points lumineux : rares, c'est ce qui « brille » sur la maquette.
    spark = Image.new("RGB", (W, H), (0, 0, 0))
    sd = ImageDraw.Draw(spark)
    for _ in range(60):
        x = rnd.randrange(0, W)
        y = rnd.randrange(0, H)
        size = rnd.choice((4, 5, 6, 8))
        sd.rectangle([x, y, x + size, y + size], fill=BRIGHT)
    for _ in range(18):
        x = rnd.randrange(0, W)
        y = rnd.randrange(0, H)
        w = rnd.randrange(30, 120)
        h = rnd.randrange(6, 14)
        sd.rounded_rectangle([x, y, x + w, y + h], radius=4, fill=(70, 190, 84))
    board = ImageChops.screen(board, spark.filter(ImageFilter.GaussianBlur(7)))
    board = ImageChops.screen(board, spark)

    return _vignette(board)


# Visage : zone exclue du détourage des glyphes (sinon l'iris vert des yeux
# serait confondu avec le fond). Les cheveux, eux, sont neutres et jamais touchés.
FACE = (501, 355, 168, 240)  # centre x, centre y, rayon x, rayon y


def _inner_region(size, radius):
    """Disque intérieur de l'anneau, moins le visage et le faisceau : les zones
    où un pixel vert doit être préservé (yeux, peau, col, lumière du socle)."""
    cx, cy = RING["cx"], RING["cy"]
    region = Image.new("L", size, 0)
    draw = ImageDraw.Draw(region)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius], fill=255
    )
    fx, fy, frx, fry = FACE
    draw.ellipse([fx - frx, fy - fry, fx + frx, fy + fry], fill=0)
    draw.polygon(CONE, fill=0)
    ex, ey, erx, ery = BASE_ELLIPSE
    draw.ellipse([ex - erx, ey - ery, ex + erx, ey + ery], fill=0)
    return region.filter(ImageFilter.GaussianBlur(6))


def _key_out_glyphs(portrait):
    """Éteint la pluie de glyphes Matrix derrière la tête.

    On vise strictement le vert moyen dominant (les glyphes) : la peau (rouge
    dominante), les cheveux (neutres, même sombres) et l'anneau (vert clair) ne
    remplissent pas les critères. Le fond devient transparent, c'est le circuit
    imprimé qui prend le relais — plus aucune auréole verte autour de la tête.
    """
    region = _inner_region(portrait.size, RING["r"] + RING_MARGIN - 24)
    red, green, blue, alpha = portrait.split()
    # Vert dominant : g dépasse nettement le rouge et le bleu.
    dominant = ImageChops.subtract(green, ImageChops.lighter(red, blue))
    dominant = dominant.point(lambda v: 255 if v > 14 else 0)
    # Intermédiaire : ni noir (cheveux) ni très lumineux (anneau, peau éclairée).
    mid_bright = green.point(lambda v: 255 if 26 < v < 200 else 0)
    key = ImageChops.darker(ImageChops.darker(dominant, mid_bright), region)
    keep = ImageChops.invert(key).filter(ImageFilter.GaussianBlur(1.5))
    portrait.putalpha(ImageChops.multiply(alpha, keep))
    return portrait


def build_portrait() -> Image.Image:
    """Détoure le portrait : garde anneau + visage + socle, transparent ailleurs."""
    src = Image.open(ASSETS / "avatar-natural.webp").convert("RGBA")
    width, height = src.size

    keep = Image.new("L", (width, height), 0)
    mask = ImageDraw.Draw(keep)
    cx, cy, r = RING["cx"], RING["cy"], RING["r"] + RING_MARGIN
    mask.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    mask.polygon(CONE, fill=255)
    ex, ey, erx, ery = BASE_ELLIPSE
    mask.ellipse([ex - erx, ey - ery, ex + erx, ey + ery], fill=255)
    keep = keep.filter(ImageFilter.GaussianBlur(MASK_FEATHER))

    src.putalpha(ImageChops.multiply(src.getchannel("A"), keep))
    return _key_out_glyphs(src)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    rnd = random.Random(SEED)
    backdrop = build_backdrop(rnd)
    backdrop_path = ASSETS / "circuit-board.webp"
    backdrop.save(backdrop_path, "WEBP", quality=90, method=6)
    stale = ASSETS / "circuit-board.png"
    if stale.exists():  # ancien format, plus référencé par l'UI
        stale.unlink()

    portrait = build_portrait()
    portrait_path = ASSETS / "avatar-cutout.webp"
    portrait.save(portrait_path, "WEBP", quality=92, method=6)

    for path in (backdrop_path, portrait_path):
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} Ko")


if __name__ == "__main__":
    main()
