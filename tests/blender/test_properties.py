import bpy
import pytest

DEFAULTS = {
    "pixels_per_unit": 16,
    "resolution_x": 320,
    "resolution_y": 200,
    "slope_run": 2.0,
    "slope_rise": 1.0,
    "depth_scale": 0.6,
    "camera_height_fraction": 0.35,
}

MINIMUMS = {
    "pixels_per_unit": 1,
    "resolution_x": 1,
    "resolution_y": 1,
    "slope_run": 0.0,
    "slope_rise": 0.0,
    "depth_scale": 0.0,
}


def test_scene_attribute(addon) -> None:
    assert addon.properties.SCENE_ATTR == "oblique_rig"
    assert isinstance(bpy.context.scene.oblique_rig, addon.properties.OBLIQUE_RIG_Settings)


def test_declared_properties(addon) -> None:
    settings = addon.properties.get_settings(bpy.context)
    declared = {p.identifier for p in settings.bl_rna.properties if p.identifier not in {"rna_type", "name"}}
    assert declared == set(DEFAULTS)


@pytest.mark.parametrize(("name", "value"), DEFAULTS.items())
def test_defaults(addon, name, value) -> None:
    settings = addon.properties.get_settings(bpy.context)
    assert getattr(settings, name) == pytest.approx(value)


def test_types(addon) -> None:
    rna = addon.properties.OBLIQUE_RIG_Settings.bl_rna.properties
    for name in ("pixels_per_unit", "resolution_x", "resolution_y"):
        assert rna[name].type == "INT"
    for name in ("slope_run", "slope_rise", "depth_scale", "camera_height_fraction"):
        assert rna[name].type == "FLOAT"
    assert rna["depth_scale"].soft_max == pytest.approx(2.0)


@pytest.mark.parametrize(("name", "minimum"), MINIMUMS.items())
def test_clamped_at_min(addon, name, minimum) -> None:
    settings = addon.properties.get_settings(bpy.context)
    setattr(settings, name, -5)
    assert getattr(settings, name) == pytest.approx(minimum)
