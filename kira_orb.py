"""The KIRA core: a real 3D orb and the matrix rain around it.

This module is **pure maths** — no tkinter, no PIL, no I/O — so the whole
visual model can be unit-tested and rendered anywhere (the UI draws it with
tkinter, `scripts/render_orb_preview.py` renders the same frame to a PNG).

Coordinates are right-handed with +z toward the viewer:

    x → right, y → down, z → toward the camera

`project()` turns a 3D point into screen coordinates plus a normalized depth
``0.0 .. 1.0`` (0 = far side of the sphere, 1 = nearest the viewer), which the
renderer uses for size, brightness and draw order.
"""
from __future__ import annotations

import math
import random

Vec3 = "tuple[float, float, float]"
TAU = math.tau

# ── per-state animation profiles ─────────────────────────────────────────────

STATE_PROFILES = {
    "READY": {"spin": 0.16, "tilt": 0.05, "pulse": 0.30, "rain": 1.0, "hue": "#FF2A2A"},
    "LISTENING": {"spin": 0.55, "tilt": 0.10, "pulse": 0.75, "rain": 1.5, "hue": "#FF5252"},
    "THINKING": {"spin": 1.15, "tilt": 0.22, "pulse": 0.60, "rain": 2.1, "hue": "#FF1744"},
    "EXECUTING": {"spin": 1.60, "tilt": 0.30, "pulse": 0.85, "rain": 2.6, "hue": "#FF3B30"},
    "SPEAKING": {"spin": 0.80, "tilt": 0.16, "pulse": 1.00, "rain": 1.8, "hue": "#FF2A2A"},
    "ERROR": {"spin": 0.35, "tilt": 0.08, "pulse": 0.65, "rain": 0.8, "hue": "#D50000"},
}
DEFAULT_PROFILE = STATE_PROFILES["READY"]


def profile(state: str) -> dict:
    """Animation profile for a UI state (never raises)."""
    return STATE_PROFILES.get(str(state or "").upper(), DEFAULT_PROFILE)


# ── geometry ─────────────────────────────────────────────────────────────────

def fibonacci_sphere(count: int, radius: float = 1.0) -> "list":
    """``count`` points spread evenly over a sphere (no polar clustering)."""
    count = max(1, int(count))
    points = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for index in range(count):
        y = 1.0 - 2.0 * (index + 0.5) / count
        y = max(-1.0, min(1.0, y))
        ring_radius = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden * index
        points.append(
            (
                math.cos(theta) * ring_radius * radius,
                y * radius,
                math.sin(theta) * ring_radius * radius,
            )
        )
    return points


def circle_ring(radius: float = 1.0, segments: int = 72, tilt: float = 0.0) -> "list":
    """A closed ring in the x/z plane, optionally tilted about x."""
    segments = max(4, int(segments))
    points = []
    for index in range(segments + 1):
        angle = TAU * index / segments
        x = math.cos(angle) * radius
        z = math.sin(angle) * radius
        y = 0.0
        if tilt:
            y = z * math.sin(tilt)
            z = z * math.cos(tilt)
        points.append((x, y, z))
    return points


def latitude_rings(count: int = 6, radius: float = 1.0, segments: int = 64) -> "list":
    """Horizontal rings between the poles, as closed loops."""
    count = max(1, int(count))
    rings = []
    for index in range(1, count + 1):
        y = -1.0 + 2.0 * index / (count + 1)
        ring_radius = math.sqrt(max(0.0, 1.0 - y * y)) * radius
        loop = []
        for step in range(segments + 1):
            angle = TAU * step / segments
            loop.append(
                (
                    math.cos(angle) * ring_radius,
                    y * radius,
                    math.sin(angle) * ring_radius,
                )
            )
        rings.append(loop)
    return rings


def meridian_rings(count: int = 8, radius: float = 1.0, segments: int = 64) -> "list":
    """Vertical great circles, evenly rotated around the y axis."""
    count = max(1, int(count))
    rings = []
    for index in range(count):
        offset = math.pi * index / count
        loop = []
        for step in range(segments + 1):
            angle = TAU * step / segments
            x = math.cos(angle) * radius
            y = math.sin(angle) * radius
            loop.append(
                (
                    x * math.cos(offset),
                    y,
                    x * math.sin(offset),
                )
            )
        rings.append(loop)
    return rings


def rotate(point, rx: float = 0.0, ry: float = 0.0, rz: float = 0.0):
    """Rotate a point about x, then y, then z (radians)."""
    x, y, z = point

    if rx:
        cos_x, sin_x = math.cos(rx), math.sin(rx)
        y, z = y * cos_x - z * sin_x, y * sin_x + z * cos_x
    if ry:
        cos_y, sin_y = math.cos(ry), math.sin(ry)
        x, z = x * cos_y + z * sin_y, -x * sin_y + z * cos_y
    if rz:
        cos_z, sin_z = math.cos(rz), math.sin(rz)
        x, y = x * cos_z - y * sin_z, x * sin_z + y * cos_z
    return (x, y, z)


def rotate_all(points, rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> "list":
    """Rotate a point cloud or a list of polylines (detected automatically)."""
    if not points:
        return []
    if isinstance(points[0], (int, float)):
        return [rotate(points, rx, ry, rz)]  # a single point given as a tuple
    first = points[0]
    if first and isinstance(first[0], (int, float)):
        return [rotate(point, rx, ry, rz) for point in points]
    return [rotate_all(line, rx, ry, rz) for line in points]


def project(point, width: float, height: float, radius: float,
            camera: float = 3.2, center=None) -> dict:
    """Perspective-project a point onto the canvas.

    Returns ``{"x","y","scale","depth"}`` where depth is 0 (far) → 1 (near).
    """
    x, y, z = point
    camera = max(1.05, float(camera))
    denominator = camera - z
    if denominator < 0.05:  # never divide by ~0 when a point meets the camera
        denominator = 0.05
    perspective = camera / denominator
    cx, cy = center if center else (width / 2.0, height / 2.0)
    return {
        "x": cx + x * radius * perspective,
        "y": cy + y * radius * perspective,
        "scale": perspective,
        "depth": (z + 1.0) / 2.0,
    }


def project_all(points, width, height, radius, camera: float = 3.2, center=None):
    """Project a point cloud, returning dicts in the original order."""
    return [project(point, width, height, radius, camera, center) for point in points]


def depth_sort(projected) -> "list":
    """Indices ordered far → near, so nearer points are drawn last."""
    return sorted(range(len(projected)), key=lambda index: projected[index]["depth"])


# ── colour ───────────────────────────────────────────────────────────────────

def hex_to_rgb(color: str):
    text = str(color or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return (255, 42, 42)
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 42, 42)


def rgb_to_hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(round(channel)))) for channel in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(color_a: str, color_b: str, t: float) -> str:
    """Blend two colours; ``t`` is clamped to 0..1."""
    t = max(0.0, min(1.0, float(t)))
    a, b = hex_to_rgb(color_a), hex_to_rgb(color_b)
    return rgb_to_hex(a[i] + (b[i] - a[i]) * t for i in range(3))


def depth_color(far: str, near: str, depth: float) -> str:
    """Shade a point by depth: dark at the back, bright at the front."""
    eased = max(0.0, min(1.0, depth)) ** 1.6
    return mix(far, near, eased)


# ── the matrix rain ──────────────────────────────────────────────────────────

# Only characters that ordinary monospace fonts actually have: a missing
# glyph renders as a blank box, which looks like a rendering bug rather than
# matrix rain (Consolas, DejaVu Sans Mono and Consolas-on-Windows all cover
# these).
GLYPHS = "0123456789+-*/\\|=<>[]{}#$%&@?!:;^~"
KATAKANA = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉ"


def make_columns(
    width: float,
    height: float,
    column_width: float = 14.0,
    count: "int | None" = None,
    seed: int = 7,
) -> "list":
    """Deterministic rain columns spanning the full width."""
    width = max(1.0, float(width))
    column_width = max(6.0, float(column_width))
    total = int(width // column_width) if count is None else int(count)
    total = max(1, total)
    rng = random.Random(seed)
    columns = []
    for index in range(total):
        columns.append(
            {
                "x": (index + 0.5) * (width / total),
                "speed": rng.uniform(0.55, 1.55),
                "phase": rng.uniform(0.0, 1.0),
                "length": rng.randint(6, 18),
                "glyph_offset": rng.randint(0, 999),
                "bright": rng.random() < 0.18,
            }
        )
    return columns


def column_glyphs(column: dict, phase: float, height: float,
                  row_height: float = 15.0, glyphs_visible: int = 10) -> "list":
    """Visible glyphs for one column: ``[(y, char, intensity 0..1)]``.

    A column is a *stream*: a bright white-hot head with a long tail that
    fades out over ``glyphs_visible`` rows, which is what makes the rain read
    as falling code rather than scattered digits.
    """
    height = max(1.0, float(height))
    row_height = max(6.0, float(row_height))
    rows = int(height // row_height) + 2
    length = max(1, int(glyphs_visible))
    head = ((phase * column.get("speed", 1.0) + column.get("phase", 0.0)) % 1.0) * (
        rows + column.get("length", 10)
    )
    glyphs = []
    for step in range(length):
        row = head - step
        if row < 0:
            continue
        y = row * row_height
        if y > height + row_height:
            continue
        if step == 0:
            intensity = 1.0
        else:
            intensity = (1.0 - step / length) ** 1.7
            if intensity < 0.06:
                break
        index = int(row) + column.get("glyph_offset", 0)
        glyphs.append((y, glyph_at(index), intensity))
    return glyphs


def glyph_at(index: int, glyphs: str = GLYPHS) -> str:
    """Stable pseudo-random glyph for a stream index."""
    if not glyphs:
        return "0"
    mixed = (int(index) * 2654435761) % 2**32
    mixed ^= mixed >> 13
    return glyphs[mixed % len(glyphs)]


def rain_intensity(profile_data: dict) -> float:
    """Rain speed multiplier for a state profile."""
    try:
        return float(profile_data.get("rain", 1.0))
    except (TypeError, ValueError):
        return 1.0


# ── frame composition helpers ────────────────────────────────────────────────

def spin_angles(state: str, phase: float) -> "tuple[float, float, float]":
    """Rotation angles for the current frame."""
    data = profile(state)
    yaw = phase * data["spin"]
    tilt = math.sin(phase * 0.35) * data["tilt"]
    roll = math.sin(phase * 0.21) * data["tilt"] * 0.5
    return tilt, yaw, roll


def orb_radius(width: float, height: float, margin: float = 0.34) -> float:
    """Radius that keeps the orb comfortably inside the canvas."""
    return max(40.0, min(width, height) * float(margin))


def pulse(phase: float, speed: float = 2.0) -> float:
    """0..1 breathing value."""
    return (math.sin(phase * speed) + 1.0) / 2.0


def orbit_point(radius: float, angle: float, tilt: float = 0.42):
    """A point on a tilted orbit (used for satellites around the core)."""
    x = math.cos(angle) * radius
    z = math.sin(angle) * radius
    y = z * math.sin(tilt)
    z = z * math.cos(tilt)
    return (x, y, z)
