"""oblique_rig.fit_to_content sizes the frame and camera to the sheared content."""

import bpy
import pytest


def _settings(addon):
    return addon.properties.get_settings(bpy.context)


def _bounds(verts):
    return (
        tuple(min(v[i] for v in verts) for i in range(3)),
        tuple(max(v[i] for v in verts) for i in range(3)),
    )


def test_poll_needs_a_rig(addon) -> None:
    assert bpy.ops.oblique_rig.fit_to_content.poll() is False
    bpy.ops.oblique_rig.build()
    assert bpy.ops.oblique_rig.fit_to_content.poll() is True


def test_fit_calibration(addon, rig_vertices) -> None:
    o = addon.core.oblique
    settings = _settings(addon)
    bpy.ops.oblique_rig.build()
    bpy.ops.oblique_rig.add_calibration()

    assert bpy.ops.oblique_rig.fit_to_content(padding_px=4) == {"FINISHED"}

    lo, hi = _bounds(rig_vertices())
    width, height = o.footprint_px(lo, hi, 16)
    assert settings.last_footprint == f"{width} x {height} px"
    assert (width, height) == (11 * 16, 3 * 16)

    expected = o.fit_frame(lo, hi, 16, 4)
    assert (settings.resolution_x, settings.resolution_y) == (expected.resolution_x, expected.resolution_y)
    assert settings.resolution_x % 2 == 0 and settings.resolution_y % 2 == 0
    assert settings.camera_offset_x == pytest.approx(expected.camera_offset_x)
    assert settings.camera_height_fraction == pytest.approx(expected.camera_height_fraction)

    r = bpy.context.scene.render
    assert (r.resolution_x, r.resolution_y) == (settings.resolution_x, settings.resolution_y), "rebuilt"
    cam = bpy.data.objects[o.CAMERA_NAME]
    assert cam.location.x * 16 == pytest.approx(round(cam.location.x * 16), abs=1e-5)
    assert cam.location.z * 16 == pytest.approx(round(cam.location.z * 16), abs=1e-5)

    # The sheared content sits inside the frame with the padding on every side.
    left, bottom, right, top = o.screen_rect(
        [lo, hi], 0.0, 0.0, 16, cam.location.x, cam.location.z, r.resolution_x, r.resolution_y
    )
    assert left >= 4 - 1e-4 and bottom >= 4 - 1e-4
    assert right <= r.resolution_x - 4 + 1e-4 and top <= r.resolution_y - 4 + 1e-4


def test_fit_uses_current_settings(addon, rig_vertices, source_box) -> None:
    """Fit rebuilds first, so a changed slope is measured, not the stale rig."""
    settings = _settings(addon)
    bpy.ops.oblique_rig.build()
    source_box("Box", (-1.0, 0.0, 0.0), (1.0, 2.0, 1.0))
    settings.depth_px_right = 0
    settings.depth_px_up = 16
    assert bpy.ops.oblique_rig.fit_to_content(padding_px=0) == {"FINISHED"}
    # No sideways depth: 2 units wide; up 1 unit per unit of depth: 1 + 2 = 3 units high.
    assert settings.last_footprint == "32 x 48 px"
    assert (settings.resolution_x, settings.resolution_y) == (32, 48)


def test_fit_without_geometry_cancels_with_a_warning(addon) -> None:
    settings = _settings(addon)
    bpy.ops.oblique_rig.build()
    assert bpy.ops.oblique_rig.fit_to_content() == {"CANCELLED"}
    assert (settings.resolution_x, settings.resolution_y) == (320, 200)


def test_fit_is_undoable(addon) -> None:
    assert addon.operators.OBLIQUE_RIG_OT_fit_to_content.bl_options == {"REGISTER", "UNDO"}
    rna = bpy.ops.oblique_rig.fit_to_content.get_rna_type().properties["padding_px"]
    assert rna.type == "INT" and rna.default == 4
