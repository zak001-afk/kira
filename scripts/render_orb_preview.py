#!/usr/bin/env python3
"""Render the KIRA core (3D orb + matrix rain) to a PNG — no display needed.

This is the offline twin of the tkinter renderer: it uses exactly the same
geometry, projection and rain maths from ``kira_orb.py``, so what you see
here is what the UI draws.

Usage:
    python scripts/render_orb_preview.py                      # READY, one frame
    python scripts/render_orb_preview.py --state THINKING
    python scripts/render_orb_preview.py --phase 2.5 --out orb.png
    python scripts/render_orb_preview.py --filmstrip          # 4 phases in one sheet

Requires Pillow (development-only dependency; the app itself does not).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - dev tool only
    print("Pillow is required for the preview: pip install Pillow")
    raise SystemExit(1)

import kira_orb  # noqa: E402

BACKGROUND = "#02060B"
RAIN_FAR = "#3A0608"
RAIN_NEAR = "#B01212"
CORE_DARK = "#100304"
TEXT_COLOR = "#F4F8FF"

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)
MONO_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
)


def load_font(candidates, size: int):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def draw_rain(draw, width, height, phase, state, layer: str, font):
    """Draw the glyph rain in one depth layer ('far' or 'near').

    The far layer is dense, small and dim; the near layer is sparse, larger
    and bright, drawn over the orb so the sphere sits *inside* the rain.
    """
    far_layer = layer == "far"
    columns = kira_orb.make_columns(
        width,
        height,
        column_width=11.0 if far_layer else 27.0,
        seed=7 if far_layer else 23,
    )
    speed = kira_orb.rain_intensity(kira_orb.profile(state)) * (0.85 if far_layer else 1.25)
    trail = 12 if far_layer else 9
    for column in columns:
        for y, glyph, intensity in kira_orb.column_glyphs(
            column, phase * speed, height, row_height=15.0, glyphs_visible=trail
        ):
            if far_layer:
                base = kira_orb.depth_color(RAIN_FAR, "#7A0F0F", intensity * 0.75)
            else:
                base = kira_orb.depth_color("#6E1010", RAIN_NEAR, intensity)
            if intensity >= 0.999:  # the falling head burns brighter
                base = kira_orb.mix(base, "#FFFFFF", 0.55)
            draw.text((column["x"], y), glyph, font=font, fill=base, anchor="mm")


def draw_orb(draw, width, height, phase, state):
    """Draw the 3D point-cloud orb, wireframe, glow and satellites."""
    data = kira_orb.profile(state)
    hue = data["hue"]
    cx, cy = width / 2.0, height / 2.0
    radius = kira_orb.orb_radius(width, height, margin=0.30)
    camera = 3.2
    breath = kira_orb.pulse(phase, 1.8)
    spin_x, spin_y, spin_z = kira_orb.spin_angles(state, phase)

    # ── halo behind the sphere: a whisper of light, not a plate ──────────
    halo_radius = radius * (1.16 + 0.03 * breath)
    for step in range(10, 0, -1):
        t = step / 10.0
        ring = halo_radius * (0.82 + 0.18 * t)
        color = kira_orb.mix(BACKGROUND, hue, 0.022 * (1.0 - t) ** 3)
        draw.ellipse([cx - ring, cy - ring, cx + ring, cy + ring], fill=color)

    # ── wireframe: smooth runs, coloured by their average depth ──────────
    lines = list(kira_orb.meridian_rings(6, 1.0, 96)) + list(
        kira_orb.latitude_rings(4, 1.0, 96)
    )
    run_length = 8
    for line in lines:
        rotated = kira_orb.rotate_all(line, spin_x, spin_y, spin_z)
        projected = kira_orb.project_all(rotated, width, height, radius, camera)
        for start in range(0, len(projected) - 1, run_length):
            run = projected[start : start + run_length + 1]
            if len(run) < 2:
                continue
            depth = sum(point["depth"] for point in run) / len(run)
            # the far side stays a ghost so the near side reads as the front
            color = kira_orb.depth_color(
                "#1C0303", kira_orb.mix(hue, "#FFFFFF", 0.22), max(0.0, depth - 0.2)
            )
            if depth < 0.35:
                color = kira_orb.mix(color, kira_orb.mix(BACKGROUND, hue, 0.10), 0.5)
            draw.line(
                [(point["x"], point["y"]) for point in run],
                fill=color,
                width=1,
            )

    # ── point cloud, drawn far → near ─────────────────────────────────────
    cloud = kira_orb.fibonacci_sphere(420, 1.0)
    cloud = kira_orb.rotate_all(cloud, spin_x, spin_y, spin_z)
    projected = kira_orb.project_all(cloud, width, height, radius, camera)
    for index in kira_orb.depth_sort(projected):
        point = projected[index]
        depth = point["depth"]
        size = max(1.0, 1.05 + depth * 1.85)
        color = kira_orb.depth_color("#3C0606", hue, depth)
        draw.ellipse(
            [
                point["x"] - size,
                point["y"] - size,
                point["x"] + size,
                point["y"] + size,
            ],
            fill=color,
        )

    # ── equatorial scan ring ──────────────────────────────────────────────
    scan = kira_orb.circle_ring(1.06, 96, tilt=math.sin(phase * 0.7) * 0.35)
    scan = kira_orb.rotate_all(scan, spin_x, spin_y, spin_z)
    projected = kira_orb.project_all(scan, width, height, radius, camera)
    draw.line(
        [(point["x"], point["y"]) for point in projected],
        fill=kira_orb.mix(hue, "#FFFFFF", 0.35 + 0.25 * breath),
        width=2,
    )

    # ── the core: dark shell with a glowing heart (drawn inside out) ──────
    core = radius * (0.50 + 0.04 * breath)
    steps = 22
    for step in range(steps, 0, -1):
        t = step / steps  # 1 = outer shell, 0 = centre
        ring = core * (0.18 + 0.82 * t)
        # brightest at the middle, falling away to the dark shell
        glow = (1.0 - t) ** 1.8
        color = kira_orb.mix("#0A0203", hue, 0.06 + 0.42 * glow)
        draw.ellipse([cx - ring, cy - ring, cx + ring, cy + ring], fill=color)
    # rim light
    draw.ellipse(
        [cx - core, cy - core, cx + core, cy + core],
        outline=kira_orb.mix(hue, "#FFFFFF", 0.30 + 0.25 * breath),
        width=2,
    )
    # inner iris ring for depth
    iris = core * 0.62
    draw.ellipse(
        [cx - iris, cy - iris, cx + iris, cy + iris],
        outline=kira_orb.mix(hue, "#FFFFFF", 0.05 + 0.10 * breath),
        width=1,
    )

    # ── orbiting satellites (3D orbits, depth-shaded) ─────────────────────
    for index in range(12):
        angle = kira_orb.TAU * index / 12 + phase * (data["spin"] * 0.45)
        orbit = kira_orb.orbit_point(1.28, angle, tilt=0.42)
        point = kira_orb.project(orbit, width, height, radius, camera)
        size = 1.4 + point["depth"] * 2.2
        color = kira_orb.depth_color("#4A0707", hue, point["depth"])
        draw.ellipse(
            [
                point["x"] - size,
                point["y"] - size,
                point["x"] + size,
                point["y"] + size,
            ],
            fill=color,
        )

    # ── labels ────────────────────────────────────────────────────────────
    title_font = load_font(FONT_CANDIDATES, max(18, int(radius * 0.22)))
    subtitle_font = load_font(FONT_CANDIDATES, max(10, int(radius * 0.075)))
    draw.text(
        (cx, cy - radius * 0.06),
        "KIRA",
        font=title_font,
        fill=TEXT_COLOR,
        anchor="mm",
    )
    draw.text(
        (cx, cy + radius * 0.17),
        "CORE",
        font=subtitle_font,
        fill=kira_orb.mix(hue, "#FFFFFF", 0.25 + 0.35 * breath),
        anchor="mm",
    )


def render_frame(state: str = "READY", phase: float = 1.0,
                 width: int = 900, height: int = 760):
    """Render one frame of the KIRA core and return a PIL image."""
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    mono_far = load_font(MONO_CANDIDATES, 11)
    mono_near = load_font(MONO_CANDIDATES, 15)

    draw_rain(draw, width, height, phase, state, "far", mono_far)
    draw_orb(draw, width, height, phase, state)
    draw_rain(draw, width, height, phase * 0.6, state, "near", mono_near)
    return image


def filmstrip(states=("READY", "LISTENING", "THINKING", "SPEAKING"),
              width=520, height=440):
    """A 2x2 sheet of states for docs and review."""
    sheet = Image.new("RGB", (width * 2, height * 2), BACKGROUND)
    for index, state in enumerate(states):
        frame = render_frame(state, phase=0.8 + index * 1.3, width=width, height=height)
        sheet.paste(frame, ((index % 2) * width, (index // 2) * height))
    return sheet


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the KIRA core to a PNG.")
    parser.add_argument("--state", default="READY", choices=sorted(kira_orb.STATE_PROFILES))
    parser.add_argument("--phase", type=float, default=1.0)
    parser.add_argument("--width", type=int, default=900)
    parser.add_argument("--height", type=int, default=760)
    parser.add_argument("--filmstrip", action="store_true")
    parser.add_argument("--out", default="kira_orb_preview.png")
    args = parser.parse_args()

    image = (
        filmstrip()
        if args.filmstrip
        else render_frame(args.state, args.phase, args.width, args.height)
    )
    image.save(args.out)
    print(f"wrote {args.out} ({image.width}x{image.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
