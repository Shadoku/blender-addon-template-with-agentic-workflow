import bpy
import pytest


def test_defaults(addon) -> None:
    settings = addon.properties.get_settings(bpy.context)
    assert settings.axis == "X"
    assert settings.gap == pytest.approx(2.0)


def test_gap_is_clamped_at_zero(addon) -> None:
    settings = addon.properties.get_settings(bpy.context)
    settings.gap = -5.0
    assert settings.gap == 0.0


def test_axis_accepts_every_declared_item(addon) -> None:
    settings = addon.properties.get_settings(bpy.context)
    for identifier, _, _ in addon.properties.AXIS_ITEMS:
        settings.axis = identifier
        assert settings.axis == identifier


def test_invalid_enum_value_raises(addon) -> None:
    settings = addon.properties.get_settings(bpy.context)
    with pytest.raises(TypeError):
        settings.axis = "W"
