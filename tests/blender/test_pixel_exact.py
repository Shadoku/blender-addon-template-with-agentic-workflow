"""Pixel-exact mode: whole-pixel depth steps, a camera on the pixel grid and even resolutions."""

import bpy
import pytest


def _settings(addon):
    return addon.properties.get_settings(bpy.context)


def _params(addon):
    return addon.properties.params_from_settings(_settings(addon))


def test_modifier_inputs_follow_params(addon) -> None:
    o = addon.core.oblique
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    mod = bpy.data.objects[o.RIG_NAME].modifiers[o.MODIFIER_NAME]
    got = tuple(
        addon.rig.get_modifier_input(mod, name) for name in ("Slope Run", "Slope Rise", "Depth Scale")
    )
    assert got == pytest.approx(_params(addon).modifier_inputs())


def test_one_unit_of_depth_moves_whole_pixels(addon, rig_vertices, source_box) -> None:
    bpy.ops.oblique_rig.build()
    source_box(
        "Probe", (-0.5, 0.0, 0.0), (0.5, 1.0, 1.0)
    )  # centred, front edge at y = 0: auto seat is a no-op

    verts = rig_vertices()
    front_bottom_left = min((v for v in verts if abs(v[1]) < 1e-6), key=lambda v: (v[0], v[2]))
    back_bottom_left = min((v for v in verts if abs(v[1] - 1.0) < 1e-6), key=lambda v: (v[0], v[2]))
    assert front_bottom_left == pytest.approx((-0.5, 0.0, 0.0), abs=1e-6)
    assert back_bottom_left[0] - front_bottom_left[0] == pytest.approx(1.0, abs=1e-6), (
        "16 px right at 16 px/unit"
    )
    assert back_bottom_left[2] - front_bottom_left[2] == pytest.approx(0.5, abs=1e-6), "8 px up"
    for v in verts:
        for coord in (v[0], v[2]):
            assert coord * 16 == pytest.approx(round(coord * 16), abs=1e-4), v


def test_other_pixel_steps(addon, rig_vertices, source_box) -> None:
    settings = _settings(addon)
    settings.depth_px_right = 12
    settings.depth_px_up = 4
    settings.pixels_per_unit = 8
    bpy.ops.oblique_rig.build()
    source_box("Probe", (-0.5, 0.0, 0.0), (0.5, 2.0, 1.0))
    deepest = max(rig_vertices(), key=lambda v: (v[1], v[0], v[2]))
    # Two units of depth: 2 * 12 px right, 2 * 4 px up at 8 px per unit.
    assert deepest == pytest.approx((0.5 + 24 / 8, 2.0, 1.0 + 8 / 8), abs=1e-6)


def test_camera_is_snapped_to_pixels(addon) -> None:
    o = addon.core.oblique
    settings = _settings(addon)
    settings.camera_height_fraction = 0.333  # 12.5 units * 0.333 = 4.1625 -> 66.6 px
    settings.camera_offset_x = 0.51  # 8.16 px
    bpy.ops.oblique_rig.build()
    cam = bpy.data.objects[o.CAMERA_NAME]
    assert cam.location.z * 16 == pytest.approx(round(cam.location.z * 16), abs=1e-5)
    assert cam.location.x * 16 == pytest.approx(round(cam.location.x * 16), abs=1e-5)
    assert tuple(cam.location) == pytest.approx(_params(addon).camera(), abs=1e-6)
    assert cam.location.z == pytest.approx(67 / 16, abs=1e-6)
    assert cam.location.x == pytest.approx(0.5, abs=1e-6)


def test_camera_is_not_snapped_in_float_mode(addon) -> None:
    o = addon.core.oblique
    settings = _settings(addon)
    settings.pixel_exact = False
    settings.camera_height_fraction = 0.333
    settings.camera_offset_x = 0.51
    bpy.ops.oblique_rig.build()
    cam = bpy.data.objects[o.CAMERA_NAME]
    assert cam.location.z == pytest.approx(200 / 16 * 0.333, abs=1e-6)
    assert cam.location.x == pytest.approx(0.51, abs=1e-6)


def test_odd_resolution_is_rendered_even(addon) -> None:
    settings = _settings(addon)
    settings.resolution_x = 321
    settings.resolution_y = 199
    bpy.ops.oblique_rig.build()
    r = bpy.context.scene.render
    assert (r.resolution_x, r.resolution_y) == (322, 200)
    assert (settings.resolution_x, settings.resolution_y) == (321, 199), "the settings are not rewritten"
    cam = bpy.data.objects[addon.core.oblique.CAMERA_NAME]
    assert cam.data.ortho_scale == pytest.approx(322 / 16)


def test_odd_resolution_is_kept_in_float_mode(addon) -> None:
    settings = _settings(addon)
    settings.pixel_exact = False
    settings.resolution_x = 321
    bpy.ops.oblique_rig.build()
    assert bpy.context.scene.render.resolution_x == 321
