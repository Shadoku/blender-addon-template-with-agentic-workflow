import dataclasses
import warnings

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
    "view_mode": "SHEARED",
    "pixel_exact": True,
    "depth_px_right": 16,
    "depth_px_up": 8,
    "camera_offset_x": 0.0,
    "direction": 0.0,
    "auto_seat": True,
    "direction_count": 4,
    "output_dir": "//guides/",
    "output_name": "guide",
    "pass_flat": True,
    "pass_shaded": True,
    "pass_ids": False,
    "pass_silhouette": False,
    "pass_composite": True,
    "make_sheet": True,
    "grid_enabled": False,
    "grid_step": 1,
    "grid_extent": 8,
    "grid_color": (0.0, 0.8, 1.0, 0.6),
    "outline_enabled": False,
    "outline_outer_px": 1,
    "outline_inner_px": 1,
    "outline_position": "OUTSIDE",
    "inner_lines": "OBJECTS",
    "outline_corners": False,
    "outline_color": (0.0, 0.0, 0.0, 1.0),
    "last_footprint": "",
    "last_warnings": "",
}

MINIMUMS = {
    "pixels_per_unit": 1,
    "resolution_x": 1,
    "resolution_y": 1,
    "slope_run": 0.0,
    "slope_rise": 0.0,
    "depth_scale": 0.0,
    "depth_px_right": 0,
    "depth_px_up": 0,
    "direction_count": 1,
    "grid_step": 1,
    "grid_extent": 1,
    "outline_outer_px": 0,
    "outline_inner_px": 0,
}

MAXIMUMS = {
    "direction_count": 16,
    "outline_outer_px": 8,
    "outline_inner_px": 8,
}

TYPES = {
    "INT": {
        "pixels_per_unit",
        "resolution_x",
        "resolution_y",
        "depth_px_right",
        "depth_px_up",
        "direction_count",
        "grid_step",
        "grid_extent",
        "outline_outer_px",
        "outline_inner_px",
    },
    "FLOAT": {
        "slope_run",
        "slope_rise",
        "depth_scale",
        "camera_height_fraction",
        "camera_offset_x",
        "direction",
        "grid_color",
        "outline_color",
    },
    "BOOLEAN": {
        "pixel_exact",
        "auto_seat",
        "pass_flat",
        "pass_shaded",
        "pass_ids",
        "pass_silhouette",
        "pass_composite",
        "make_sheet",
        "grid_enabled",
        "outline_enabled",
        "outline_corners",
    },
    "STRING": {"output_dir", "output_name", "last_footprint", "last_warnings"},
    "ENUM": {"view_mode", "outline_position", "inner_lines"},
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
    got = getattr(settings, name)
    if isinstance(value, str):
        assert got == value
    elif isinstance(value, tuple):
        assert tuple(got) == pytest.approx(value)
    else:
        assert got == pytest.approx(value)


def test_types(addon) -> None:
    rna = addon.properties.OBLIQUE_RIG_Settings.bl_rna.properties
    for kind, names in TYPES.items():
        for name in names:
            assert rna[name].type == kind, name
    assert set().union(*TYPES.values()) == set(DEFAULTS)
    assert rna["depth_scale"].soft_max == pytest.approx(2.0)
    assert rna["depth_px_right"].soft_max == 64 and rna["depth_px_up"].soft_max == 64
    assert {i.identifier for i in rna["view_mode"].enum_items} == {"SOURCE", "SHEARED"}
    assert {i.identifier for i in rna["outline_position"].enum_items} == {"OUTSIDE", "INSIDE"}
    assert {i.identifier for i in rna["inner_lines"].enum_items} == {"NONE", "OBJECTS", "MATERIALS"}


def test_subtypes(addon) -> None:
    rna = addon.properties.OBLIQUE_RIG_Settings.bl_rna.properties
    assert rna["direction"].subtype == "ANGLE"
    assert rna["output_dir"].subtype == "DIR_PATH"
    assert rna["camera_offset_x"].unit == "LENGTH"
    for name in ("grid_color", "outline_color"):
        assert rna[name].subtype == "COLOR"
        assert rna[name].array_length == 4
        assert (rna[name].hard_min, rna[name].hard_max) == pytest.approx((0.0, 1.0))


def test_output_dir_accepts_blend_relative_paths(addon) -> None:
    """Without PATH_SUPPORTS_BLEND_RELATIVE, assigning "//..." prints a RuntimeWarning."""
    rna = addon.properties.OBLIQUE_RIG_Settings.bl_rna.properties
    assert rna["output_dir"].is_path_supports_blend_relative
    settings = addon.properties.get_settings(bpy.context)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        settings.output_dir = "//renders/"
    assert settings.output_dir == "//renders/"


@pytest.mark.parametrize(("name", "minimum"), MINIMUMS.items())
def test_clamped_at_min(addon, name, minimum) -> None:
    settings = addon.properties.get_settings(bpy.context)
    setattr(settings, name, -5)
    assert getattr(settings, name) == pytest.approx(minimum)


@pytest.mark.parametrize(("name", "maximum"), MAXIMUMS.items())
def test_clamped_at_max(addon, name, maximum) -> None:
    settings = addon.properties.get_settings(bpy.context)
    setattr(settings, name, 1000)
    assert getattr(settings, name) == maximum


def test_params_from_settings(addon) -> None:
    settings = addon.properties.get_settings(bpy.context)
    got = dataclasses.asdict(addon.properties.params_from_settings(settings))
    expected = dataclasses.asdict(addon.core.oblique.RigParams())
    assert got.keys() == expected.keys()
    for key, value in expected.items():
        assert got[key] == (value if isinstance(value, (str, bool)) else pytest.approx(value)), key

    settings.pixel_exact = False
    settings.depth_px_right = 12
    settings.direction = 1.25
    settings.auto_seat = False
    settings.camera_offset_x = 0.75
    settings.view_mode = "SOURCE"
    params = addon.properties.params_from_settings(settings)
    assert isinstance(params, addon.core.oblique.RigParams)
    assert params.pixel_exact is False
    assert params.depth_px_right == 12
    assert params.direction == pytest.approx(1.25)
    assert params.auto_seat is False
    assert params.camera_offset_x == pytest.approx(0.75)
    assert params.view_mode == "SOURCE"


def test_reset_restores_every_default(addon) -> None:
    """conftest unsets every property between tests; that must reach the defaults again."""
    settings = addon.properties.get_settings(bpy.context)
    settings.grid_color = (1.0, 1.0, 1.0, 1.0)
    settings.output_name = "x"
    settings.last_warnings = "A / B"
    for prop in settings.bl_rna.properties:
        if prop.identifier != "rna_type":
            settings.property_unset(prop.identifier)
    assert tuple(settings.grid_color) == pytest.approx(DEFAULTS["grid_color"])
    assert settings.output_name == "guide"
    assert settings.last_warnings == ""
