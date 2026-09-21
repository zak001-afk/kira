"""The core's maths: geometry, projection, matrix rain and state profiles.

KIRA's live core is the Three.js reactor in ``ui/app.js``; this module is the
pure-python twin of its geometry. ``scripts/render_orb_preview.py`` renders
these shapes to a PNG with no display, which is how the artwork in the README
is produced — so the maths is still load-bearing, and still tested.
"""
from __future__ import annotations

import math
import sys
import types

import pytest

import kira_orb


class TestGeometry:
    def test_fibonacci_sphere_points_lie_on_the_sphere(self):
        points = kira_orb.fibonacci_sphere(200, 1.0)
        assert len(points) == 200
        for x, y, z in points:
            assert math.isclose(math.sqrt(x * x + y * y + z * z), 1.0, abs_tol=1e-9)

    def test_fibonacci_sphere_has_no_polar_clumping(self):
        points = kira_orb.fibonacci_sphere(400, 1.0)
        # split into bands of latitude; counts must not collapse at the poles
        bands = [0] * 4
        for _, y, _ in points:
            bands[min(3, int((y + 1.0) / 2.0 * 4))] += 1
        assert min(bands) > 60

    def test_fibonacci_sphere_handles_tiny_and_zero_counts(self):
        assert len(kira_orb.fibonacci_sphere(0)) == 1
        assert len(kira_orb.fibonacci_sphere(1)) == 1

    def test_circle_ring_is_closed_and_sized(self):
        ring = kira_orb.circle_ring(2.0, 24)
        assert len(ring) == 25
        # a closed loop: the last point returns to the first
        assert all(abs(a - b) < 1e-9 for a, b in zip(ring[0], ring[-1]))
        for x, y, z in ring:
            assert math.isclose(math.hypot(x, z), 2.0, abs_tol=1e-9)

    def test_circle_ring_tilt_moves_points_in_y(self):
        flat = kira_orb.circle_ring(1.0, 8, tilt=0.0)
        tilted = kira_orb.circle_ring(1.0, 8, tilt=0.5)
        assert all(abs(point[1]) < 1e-9 for point in flat)
        assert any(abs(point[1]) > 0.1 for point in tilted)

    def test_latitude_rings_shrink_towards_the_poles(self):
        rings = kira_orb.latitude_rings(4, 1.0, 32)
        assert len(rings) == 4
        radii = [max(abs(x) for x, _, _ in ring) for ring in rings]
        # widest at the equator, mirror-symmetric towards each pole
        assert radii[0] < radii[1]
        assert radii[3] < radii[2]
        assert all(radius <= 1.0 + 1e-9 for radius in radii)
        assert radii[0] < 0.9 and radii[3] < 0.9
        assert all(len(ring) == 33 for ring in rings)

    def test_meridian_rings_are_great_circles(self):
        for ring in kira_orb.meridian_rings(6, 1.0, 48):
            for x, y, z in ring:
                assert math.isclose(math.sqrt(x * x + y * y + z * z), 1.0, abs_tol=1e-9)

    def test_orbit_point_stays_on_a_tilted_circle(self):
        for angle in (0.0, 1.0, math.pi, 4.5):
            x, y, z = kira_orb.orbit_point(2.0, angle, tilt=0.4)
            assert math.isclose(math.sqrt(x * x + y * y + z * z), 2.0, abs_tol=1e-9)


class TestRotation:
    def test_rotation_about_y_moves_x_into_z(self):
        x, y, z = kira_orb.rotate((1.0, 0.0, 0.0), ry=math.pi / 2)
        assert abs(x) < 1e-9 and abs(z + 1.0) < 1e-9

    def test_rotation_about_x_moves_y_into_z(self):
        x, y, z = kira_orb.rotate((0.0, 1.0, 0.0), rx=math.pi / 2)
        assert abs(x) < 1e-9 and abs(z - 1.0) < 1e-9

    def test_rotation_preserves_length(self):
        vector = (0.3, -0.7, 0.5)
        rotated = kira_orb.rotate(vector, rx=0.4, ry=1.1, rz=-0.3)
        assert math.isclose(
            math.dist((0, 0, 0), rotated), math.dist((0, 0, 0), vector), abs_tol=1e-9
        )

    def test_rotate_all_handles_clouds_and_polylines(self):
        cloud = kira_orb.rotate_all([(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], ry=0.5)
        assert len(cloud) == 2
        lines = kira_orb.rotate_all([[(1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]], ry=0.5)
        assert len(lines) == 1 and len(lines[0]) == 2

    def test_rotate_all_on_empty_input(self):
        assert kira_orb.rotate_all([]) == []


class TestProjection:
    def test_centre_point_lands_on_the_centre(self):
        point = kira_orb.project((0.0, 0.0, 0.0), 800, 600, 200)
        assert point["x"] == 400 and point["y"] == 300
        assert point["depth"] == 0.5

    def test_near_points_are_bigger_and_deeper(self):
        near = kira_orb.project((0.0, 0.0, 0.9), 800, 600, 200)
        far = kira_orb.project((0.0, 0.0, -0.9), 800, 600, 200)
        assert near["scale"] > far["scale"] > 0
        assert near["depth"] > 0.9 and far["depth"] < 0.1

    def test_depth_is_normalized(self):
        for z in (-1.0, -0.25, 0.0, 0.5, 1.0):
            depth = kira_orb.project((0.0, 0.0, z), 100, 100, 50)["depth"]
            assert 0.0 <= depth <= 1.0

    def test_camera_collision_is_clamped_not_divided_by_zero(self):
        point = kira_orb.project((1.0, 0.0, 3.2), 100, 100, 50, camera=3.2)
        assert math.isfinite(point["x"]) and math.isfinite(point["scale"])

    def test_custom_centre_is_respected(self):
        point = kira_orb.project((0.0, 0.0, 0.0), 800, 600, 200, center=(10, 20))
        assert (point["x"], point["y"]) == (10, 20)

    def test_depth_sort_is_far_to_near(self):
        projected = [kira_orb.project((0, 0, z), 100, 100, 40) for z in (0.5, -0.5, 0.0)]
        order = kira_orb.depth_sort(projected)
        depths = [projected[index]["depth"] for index in order]
        assert depths == sorted(depths)


class TestColour:
    def test_hex_round_trip(self):
        assert kira_orb.hex_to_rgb("#FF2A2A") == (255, 42, 42)
        assert kira_orb.rgb_to_hex((255, 42, 42)) == "#FF2A2A"

    def test_shorthand_and_invalid_colours(self):
        assert kira_orb.hex_to_rgb("#F00") == (255, 0, 0)
        assert kira_orb.hex_to_rgb("") == (255, 42, 42)
        assert kira_orb.hex_to_rgb("nonsense") == (255, 42, 42)

    def test_mix_clamps_and_blends(self):
        assert kira_orb.mix("#000000", "#FFFFFF", 0.0) == "#000000"
        assert kira_orb.mix("#000000", "#FFFFFF", 1.0) == "#FFFFFF"
        assert kira_orb.mix("#000000", "#FFFFFF", 5.0) == "#FFFFFF"
        assert kira_orb.mix("#000000", "#FFFFFF", -3.0) == "#000000"
        assert kira_orb.mix("#000000", "#808080", 0.5) == "#404040"

    def test_depth_colour_brightens_towards_the_viewer(self):
        back = kira_orb.depth_color("#100000", "#FF0000", 0.0)
        front = kira_orb.depth_color("#100000", "#FF0000", 1.0)
        assert kira_orb.hex_to_rgb(front)[0] > kira_orb.hex_to_rgb(back)[0]
        assert front == "#FF0000"


class TestRain:
    def test_columns_span_the_width(self):
        columns = kira_orb.make_columns(800, 600, column_width=16)
        assert len(columns) == 50
        assert columns[0]["x"] < 800 / 50
        assert columns[-1]["x"] > 800 * 0.98

    def test_columns_are_deterministic_for_a_seed(self):
        first = kira_orb.make_columns(400, 300, seed=5)
        second = kira_orb.make_columns(400, 300, seed=5)
        assert first == second
        other = kira_orb.make_columns(400, 300, seed=6)
        assert first != other

    def test_explicit_column_count_is_honoured(self):
        assert len(kira_orb.make_columns(9999, 600, count=12)) == 12
        assert len(kira_orb.make_columns(1, 1)) == 1

    def test_trails_are_longest_at_the_head(self):
        column = {"x": 10, "speed": 1.0, "phase": 0.0, "length": 12, "glyph_offset": 0}
        glyphs = kira_orb.column_glyphs(column, 0.5, 400, row_height=15, glyphs_visible=8)
        assert glyphs, "a column in view must draw glyphs"
        intensities = [intensity for _, _, intensity in glyphs]
        assert intensities == sorted(intensities, reverse=True)
        assert intensities[0] == 1.0
        ys = [y for y, _, _ in glyphs]
        assert ys == sorted(ys, reverse=True)  # tail trails above the falling head

    def test_head_moves_down_as_phase_grows(self):
        column = {"x": 0, "speed": 1.0, "phase": 0.0, "length": 10, "glyph_offset": 0}
        first = kira_orb.column_glyphs(column, 0.10, 400)[0][0]
        later = kira_orb.column_glyphs(column, 0.35, 400)[0][0]
        assert later > first

    def test_glyphs_stay_inside_the_canvas(self):
        column = {"x": 0, "speed": 0.7, "phase": 0.3, "length": 14, "glyph_offset": 5}
        for phase in (0.0, 0.25, 0.5, 0.75):
            for y, _, _ in kira_orb.column_glyphs(column, phase, 300, row_height=15):
                assert -15 <= y <= 315

    def test_glyph_at_is_stable_and_uses_the_alphabet(self):
        alphabet = "abc"
        assert kira_orb.glyph_at(7, alphabet) == kira_orb.glyph_at(7, alphabet)
        assert kira_orb.glyph_at(7, alphabet) in alphabet
        assert kira_orb.glyph_at(0, "") == "0"

    def test_default_glyphs_are_single_characters(self):
        # a double-width glyph would break the monospace column rhythm
        assert all(len(glyph) == 1 for glyph in kira_orb.GLYPHS)
        assert "0" in kira_orb.GLYPHS and "1" in kira_orb.GLYPHS

    def test_rain_intensity_survives_bad_profile_data(self):
        assert kira_orb.rain_intensity({"rain": 2.5}) == 2.5
        assert kira_orb.rain_intensity({"rain": "bogus"}) == 1.0
        assert kira_orb.rain_intensity({}) == 1.0


class TestProfiles:
    def test_every_state_has_a_profile(self):
        for state in ("READY", "LISTENING", "THINKING", "EXECUTING", "SPEAKING", "ERROR"):
            data = kira_orb.profile(state)
            assert set(data) >= {"spin", "tilt", "pulse", "rain", "hue"}
            assert data["hue"].startswith("#")

    def test_unknown_state_falls_back_to_ready(self):
        assert kira_orb.profile("nonsense") == kira_orb.STATE_PROFILES["READY"]
        assert kira_orb.profile("") == kira_orb.STATE_PROFILES["READY"]
        assert kira_orb.profile(None) == kira_orb.STATE_PROFILES["READY"]

    def test_busy_states_spin_and_rain_faster(self):
        ready = kira_orb.profile("READY")
        executing = kira_orb.profile("EXECUTING")
        assert executing["spin"] > ready["spin"]
        assert executing["rain"] > ready["rain"]

    def test_spin_angles_advance_with_phase(self):
        first = kira_orb.spin_angles("THINKING", 0.0)
        later = kira_orb.spin_angles("THINKING", 2.0)
        assert later[1] > first[1]  # yaw grows

    def test_orb_radius_follows_the_smaller_axis(self):
        # same short side → same radius, whichever way the canvas is oriented
        assert kira_orb.orb_radius(1000, 400) == kira_orb.orb_radius(400, 1000)
        assert kira_orb.orb_radius(400, 400) < kira_orb.orb_radius(900, 900)
        assert kira_orb.orb_radius(10, 10) >= 40  # never degenerate

    def test_pulse_stays_in_range(self):
        for phase in (0.0, 0.4, 1.1, 2.7, 5.0):
            assert 0.0 <= kira_orb.pulse(phase) <= 1.0


def _drop_pil_stubs():
    """Remove any stub PIL so the preview script sees the real Pillow."""
    for key in [name for name in sys.modules if name.split(".")[0] == "PIL"]:
        module = sys.modules.get(key)
        if getattr(module, "__kira_stub__", False):
            del sys.modules[key]


class TestPreviewScript:
    def test_module_compiles_and_renders_when_pillow_exists(self):
        import importlib.util
        from pathlib import Path

        _drop_pil_stubs()
        path = Path(__file__).resolve().parent.parent / "scripts" / "render_orb_preview.py"
        spec = importlib.util.spec_from_file_location("kira_orb_preview", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except SystemExit:  # Pillow missing in CI — that is handled gracefully
            pytest.skip("Pillow is not installed")
        image = module.render_frame("THINKING", phase=0.9, width=240, height=200)
        assert image.size == (240, 200)
        assert image.getpixel((120, 100)) != (2, 6, 11)  # something was drawn

    def test_filmstrip_covers_several_states(self):
        import importlib.util
        from pathlib import Path

        _drop_pil_stubs()
        path = Path(__file__).resolve().parent.parent / "scripts" / "render_orb_preview.py"
        spec = importlib.util.spec_from_file_location("kira_orb_preview_sheet", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            pytest.skip("Pillow is not installed")
        sheet = module.filmstrip(width=200, height=160)
        assert sheet.size == (400, 320)
