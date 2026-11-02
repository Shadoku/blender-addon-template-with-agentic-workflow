"""Direction turns the source about Z before the shear; Auto Seat puts it back on the reference plane."""

import math

import bpy
import pytest


def _flat(addon) -> None:
    """No shear, so the evaluated mesh is the turned and seated source itself."""
    settings = addon.properties.get_settings(bpy.context)
    settings.pixel_exact = False
    settings.depth_scale = 0.0


def _bounds(verts):
    return (
        tuple(min(v[i] for v in verts) for i in range(3)),
        tuple(max(v[i] for v in verts) for i in range(3)),
    )


def _asymmetric_source(source_box) -> None:
    """Off-centre and asymmetric: a 3 x 1 box at x 5..8, y 3..4 and a 1 x 2 box at x 5..6, y 4..6."""
    source_box("Long", (5.0, 3.0, 0.0), (8.0, 4.0, 1.0))
    source_box("Tall", (5.0, 4.0, 0.0), (6.0, 6.0, 2.0))


def test_direction_reaches_the_modifier(addon) -> None:
    o = addon.core.oblique
    settings = addon.properties.get_settings(bpy.context)
    settings.direction = math.radians(90)
    settings.auto_seat = False
    bpy.ops.oblique_rig.build()
    mod = bpy.data.objects[o.RIG_NAME].modifiers[o.MODIFIER_NAME]
    assert addon.rig.get_modifier_input(mod, "Direction") == pytest.approx(math.pi / 2)
    assert addon.rig.get_modifier_input(mod, "Auto Seat") is False


def test_auto_seat_after_quarter_turn(addon, rig_vertices, source_box) -> None:
    _flat(addon)
    addon.properties.get_settings(bpy.context).direction = math.radians(90)
    bpy.ops.oblique_rig.build()
    _asymmetric_source(source_box)

    lo, hi = _bounds(rig_vertices())
    assert lo[1] == pytest.approx(0.0, abs=1e-5), "front edge on y = 0"
    assert lo[0] + hi[0] == pytest.approx(0.0, abs=1e-5), "centred on x = 0"
    # Turned 90 degrees: x' = -y spans -6..-3 (3 wide), y' = x spans 5..8 (3 deep).
    assert hi[0] - lo[0] == pytest.approx(3.0, abs=1e-5)
    assert hi[1] - lo[1] == pytest.approx(3.0, abs=1e-5)
    assert (lo[2], hi[2]) == pytest.approx((0.0, 2.0), abs=1e-5), "z is never moved"


def test_auto_seat_off_leaves_the_turned_source(addon, rig_vertices, source_box) -> None:
    _flat(addon)
    settings = addon.properties.get_settings(bpy.context)
    settings.direction = math.radians(90)
    settings.auto_seat = False
    bpy.ops.oblique_rig.build()
    _asymmetric_source(source_box)

    lo, hi = _bounds(rig_vertices())
    assert lo == pytest.approx((-6.0, 5.0, 0.0), abs=1e-5)
    assert hi == pytest.approx((-3.0, 8.0, 2.0), abs=1e-5)


def test_auto_seat_without_turn_centres_and_seats(addon, rig_vertices, source_box) -> None:
    _flat(addon)
    bpy.ops.oblique_rig.build()
    _asymmetric_source(source_box)
    lo, hi = _bounds(rig_vertices())
    assert lo == pytest.approx((-1.5, 0.0, 0.0), abs=1e-5)
    assert hi == pytest.approx((1.5, 3.0, 2.0), abs=1e-5)


def test_seated_then_sheared(addon, rig_vertices, source_box) -> None:
    """With the default pixel-exact shear the seat still holds: y is never sheared."""
    settings = addon.properties.get_settings(bpy.context)
    settings.direction = math.radians(90)
    bpy.ops.oblique_rig.build()
    _asymmetric_source(source_box)
    a, b = addon.properties.params_from_settings(settings).shear()

    verts = rig_vertices()
    lo, hi = _bounds(verts)
    assert lo[1] == pytest.approx(0.0, abs=1e-5)
    assert hi[1] == pytest.approx(3.0, abs=1e-5)
    # The front-left corner of the seated source (x = -1.5, y = 0, z = 0) is not moved by the shear.
    assert lo[0] == pytest.approx(-1.5, abs=1e-5)
    assert lo[2] == pytest.approx(0.0, abs=1e-5)
    # Seated, "Long" spans x -0.5..1.5, y 0..3, z 0..1 and "Tall" x -1.5..0.5, y 0..1, z 0..2.
    assert hi[0] == pytest.approx(1.5 + 3.0 * a, abs=1e-5)
    assert hi[2] == pytest.approx(max(1.0 + 3.0 * b, 2.0 + 1.0 * b), abs=1e-5)


def test_full_turn_matches_no_turn(addon, rig_vertices, source_box) -> None:
    settings = addon.properties.get_settings(bpy.context)
    bpy.ops.oblique_rig.build()
    _asymmetric_source(source_box)
    before = sorted(_rounded(rig_vertices()))
    settings.direction = 2 * math.pi
    bpy.ops.oblique_rig.build()
    after = sorted(_rounded(rig_vertices()))
    assert before == after


def _rounded(verts):
    """Round away float noise (sin(2 pi) is not 0) so sorting cannot swap near-equal vertices."""
    return [tuple(round(c, 4) + 0.0 for c in v) for v in verts]
