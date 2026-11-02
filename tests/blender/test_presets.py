"""Slope and resolution presets set the settings in one click and rebuild an existing rig."""

import bpy
import pytest


def _settings(addon):
    return addon.properties.get_settings(bpy.context)


def test_slope_enum_lists_core_presets(addon) -> None:
    rna = bpy.ops.oblique_rig.apply_slope_preset.get_rna_type().properties["preset"]
    assert [i.identifier for i in rna.enum_items] == [p.identifier for p in addon.core.presets.SLOPE_PRESETS]
    assert [i.name for i in rna.enum_items] == [p.label for p in addon.core.presets.SLOPE_PRESETS]
    assert all(i.description for i in rna.enum_items)


def test_resolution_enum_lists_core_presets(addon) -> None:
    rna = bpy.ops.oblique_rig.apply_resolution_preset.get_rna_type().properties["preset"]
    assert [i.identifier for i in rna.enum_items] == [
        p.identifier for p in addon.core.presets.RESOLUTION_PRESETS
    ]


@pytest.mark.parametrize("preset", ["PIXEL_2_1", "CABINET_2_1", "PIXEL_1_1", "PIXEL_3_2", "PIXEL_1_2"])
def test_apply_slope_preset(addon, preset) -> None:
    settings = _settings(addon)
    settings.pixel_exact = False
    settings.pixels_per_unit = 32
    assert bpy.ops.oblique_rig.apply_slope_preset(preset=preset) == {"FINISHED"}
    assert (settings.depth_px_right, settings.depth_px_up) == addon.core.presets.slope_preset(preset, 32)
    assert settings.pixel_exact is True


def test_slope_preset_rebuilds_existing_rig(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.build()
    bpy.ops.oblique_rig.apply_slope_preset(preset="PIXEL_1_2")
    mod = bpy.data.objects[o.RIG_NAME].modifiers[o.MODIFIER_NAME]
    assert addon.rig.get_modifier_input(mod, "Slope Run") == pytest.approx(8)
    assert addon.rig.get_modifier_input(mod, "Slope Rise") == pytest.approx(16)


def test_slope_preset_without_rig_builds_nothing(addon) -> None:
    bpy.ops.oblique_rig.apply_slope_preset(preset="PIXEL_1_1")
    assert len(bpy.data.objects) == 0


def test_apply_resolution_preset(addon) -> None:
    settings = _settings(addon)
    assert bpy.ops.oblique_rig.apply_resolution_preset(preset="R128_128_8") == {"FINISHED"}
    assert (settings.resolution_x, settings.resolution_y, settings.pixels_per_unit) == (128, 128, 8)


def test_resolution_preset_rebuilds_existing_rig(addon) -> None:
    bpy.ops.oblique_rig.build()
    bpy.ops.oblique_rig.apply_resolution_preset(preset="R512_288_32")
    r = bpy.context.scene.render
    assert (r.resolution_x, r.resolution_y) == (512, 288)
    cam = bpy.data.objects[addon.core.oblique.CAMERA_NAME]
    assert cam.data.ortho_scale == pytest.approx(512 / 32)


def test_presets_are_undoable(addon) -> None:
    for cls in (
        addon.operators.OBLIQUE_RIG_OT_apply_slope_preset,
        addon.operators.OBLIQUE_RIG_OT_apply_resolution_preset,
    ):
        assert cls.bl_options == {"REGISTER", "UNDO"}
        assert cls.bl_property == "preset"
