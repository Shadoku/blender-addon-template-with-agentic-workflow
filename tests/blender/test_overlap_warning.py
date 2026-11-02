"""Build and Fit flag source objects whose sheared shapes overlap while their depth ranges interleave."""

import math

import bpy
import pytest


def _settings(addon):
    return addon.properties.get_settings(bpy.context)


def test_interleaved_depth_is_flagged(addon, source_box) -> None:
    bpy.ops.oblique_rig.build()
    source_box("Near", (-0.5, 0.0, 0.0), (0.5, 1.0, 1.0))
    source_box("Far", (-0.5, 0.5, 0.0), (0.5, 1.5, 1.0))
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    warnings = _settings(addon).last_warnings
    assert warnings == addon.core.overlap.format_warnings([("Far", "Near")]), "collection order is by name"
    assert "Far / Near" in warnings


def test_separated_objects_are_not_flagged(addon, source_box) -> None:
    bpy.ops.oblique_rig.build()
    source_box("Left", (-0.5, 0.0, 0.0), (0.5, 1.0, 1.0))
    source_box("Right", (9.5, 0.5, 0.0), (10.5, 1.5, 1.0))
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    assert _settings(addon).last_warnings == ""


def test_calibration_cubes_are_not_paired(addon) -> None:
    """The two cubes are 3 units apart in depth, so their order is unambiguous (the floor may still be paired)."""
    bpy.ops.oblique_rig.build()
    bpy.ops.oblique_rig.add_calibration()
    bpy.ops.oblique_rig.build()
    warnings = _settings(addon).last_warnings
    o = addon.core.oblique
    assert f"{o.CALIB_FRONT} / {o.CALIB_BACK}" not in warnings, "3 units apart in depth: unambiguous"
    assert f"{o.CALIB_BACK} / {o.CALIB_FRONT}" not in warnings


def test_at_most_three_pairs(addon, source_box) -> None:
    bpy.ops.oblique_rig.build()
    for i in range(4):
        source_box(f"Box{i}", (-0.5, 0.1 * i, 0.0), (0.5, 1.0 + 0.1 * i, 1.0))
    bpy.ops.oblique_rig.build()
    warnings = _settings(addon).last_warnings
    all_pairs = [(f"Box{i}", f"Box{j}") for i in range(4) for j in range(i + 1, 4)]
    assert warnings == addon.core.overlap.format_warnings(all_pairs[:3]), "6 pairs overlap; 3 are shown"


def test_fit_updates_warnings(addon, source_box) -> None:
    bpy.ops.oblique_rig.build()
    source_box("Near", (-0.5, 0.0, 0.0), (0.5, 1.0, 1.0))
    source_box("Far", (-0.5, 0.5, 0.0), (0.5, 1.5, 1.0))
    _settings(addon).last_warnings = ""
    assert bpy.ops.oblique_rig.fit_to_content() == {"FINISHED"}
    assert _settings(addon).last_warnings != ""


def test_source_rects_follow_direction(addon, source_box) -> None:
    """Turned a quarter, two boxes side by side in x become one behind the other in depth."""
    o = addon.core.oblique
    bpy.ops.oblique_rig.build()
    source_box("A", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    source_box("B", (3.0, 0.0, 0.0), (4.0, 1.0, 1.0))
    params = o.RigParams(direction=math.radians(90))
    rects = {name: (rect, depth) for name, rect, depth in addon.rig.source_rects(bpy.context.scene, params)}
    assert set(rects) == {"A", "B"}
    # Turned: A spans y 0..1, B y 3..4 (auto seat puts the front edge on y = 0).
    assert rects["A"][1] == pytest.approx((0.0, 1.0), abs=1e-5)
    assert rects["B"][1] == pytest.approx((3.0, 4.0), abs=1e-5)
    # Without turning both share the depth range 0..1 and sit side by side on screen.
    rects = {
        name: (rect, depth) for name, rect, depth in addon.rig.source_rects(bpy.context.scene, o.RigParams())
    }
    assert rects["A"][1] == pytest.approx((0.0, 1.0), abs=1e-5)
    assert rects["B"][1] == pytest.approx((0.0, 1.0), abs=1e-5)
    assert rects["B"][0][0] - rects["A"][0][0] == pytest.approx(3 * 16, abs=1e-4), "3 units apart at 16 px"
