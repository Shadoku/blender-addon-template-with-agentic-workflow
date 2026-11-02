"""Build and Fit flag source objects that interpenetrate (their world bounding boxes overlap in 3D)."""

import math

import bpy
import pytest


def _settings(addon):
    return addon.properties.get_settings(bpy.context)


def test_interpenetrating_boxes_are_flagged(addon, source_box) -> None:
    bpy.ops.oblique_rig.build()
    source_box("Near", (-0.5, 0.0, 0.0), (0.5, 1.0, 1.0))
    source_box("Far", (-0.5, 0.5, 0.25), (0.5, 1.5, 1.25))
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


def test_one_behind_the_other_is_not_flagged(addon, source_box) -> None:
    """Overlapping on screen but separate in depth: the shear keeps the order readable."""
    bpy.ops.oblique_rig.build()
    source_box("Front", (-0.5, 0.0, 0.0), (0.5, 1.0, 1.0))
    source_box("Back", (-0.25, 1.5, 0.0), (0.75, 2.5, 1.0))
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    assert _settings(addon).last_warnings == ""


def test_cubes_standing_on_a_floor_are_not_flagged(addon, source_box) -> None:
    bpy.ops.oblique_rig.build()
    source_box("Floor", (-3.0, 0.0, 0.0), (3.0, 5.0, 0.0))
    source_box("Crate", (-0.5, 1.0, 0.0), (0.5, 2.0, 1.0))
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    assert _settings(addon).last_warnings == ""


def test_calibration_build_has_no_warning(addon) -> None:
    """The calibration cubes stand on the floor and are 3 units apart: nothing interpenetrates."""
    bpy.ops.oblique_rig.build()
    bpy.ops.oblique_rig.add_calibration()
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    assert _settings(addon).last_warnings == ""


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


def test_source_boxes_are_world_bounds(addon, source_box) -> None:
    """Evaluated world-space boxes: object transforms count, empties are skipped, sorted by name."""
    bpy.ops.oblique_rig.build()
    b = source_box("B", (0.0, 0.0, 0.0), (1.0, 2.0, 1.0))
    b.location = (3.0, 0.0, 0.0)
    b.rotation_euler = (0.0, 0.0, math.radians(90))
    source_box("A", (-1.0, 0.0, 0.0), (1.0, 1.0, 0.5))
    empty = bpy.data.objects.new("Empty", None)
    bpy.data.collections[addon.core.oblique.SOURCE_COLLECTION].objects.link(empty)
    bpy.context.view_layer.update()

    boxes = addon.rig.source_boxes(bpy.context.scene)
    assert [name for name, _, _ in boxes] == ["A", "B"]
    (_, lo_a, hi_a), (_, lo_b, hi_b) = boxes
    assert lo_a == pytest.approx((-1.0, 0.0, 0.0), abs=1e-6)
    assert hi_a == pytest.approx((1.0, 1.0, 0.5), abs=1e-6)
    # Turned a quarter about Z at x = 3: x spans 3 - 2 .. 3, y 0 .. 1.
    assert lo_b == pytest.approx((1.0, 0.0, 0.0), abs=1e-6)
    assert hi_b == pytest.approx((3.0, 1.0, 1.0), abs=1e-6)


def test_source_boxes_without_source_collection(addon) -> None:
    assert addon.rig.source_boxes(bpy.context.scene) == []
