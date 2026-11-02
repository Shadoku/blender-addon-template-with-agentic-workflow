"""Blender never calls draw() in background mode. Calling it with a recording layout
proves the methods run against real context, reference real properties, and that every
setting and operator is reachable from the sidebar."""

import bpy
import pytest

READOUTS = {"last_footprint", "last_warnings"}  # shown as labels, never as editable fields


def _all_settings(addon) -> set[str]:
    rna = addon.properties.OBLIQUE_RIG_Settings.bl_rna.properties
    return {p.identifier for p in rna if p.identifier not in {"rna_type", "name"}}


def _panels(addon) -> list[type]:
    return [cls for cls in addon.ui.CLASSES if issubclass(cls, bpy.types.Panel)]


def _draw(panel_cls, layout) -> list:
    fake_panel = type("FakePanel", (), {"layout": layout})()
    panel_cls.draw(fake_panel, bpy.context)
    return layout.calls


def _draw_all(addon, layout) -> list:
    for panel_cls in _panels(addon):
        _draw(panel_cls, layout)
    return layout.calls


def _props(calls) -> set[str]:
    return {call[1][1] for call in calls if call[0] == "prop"}


def _operators(calls) -> set[str]:
    return {call[1][0] for call in calls if call[0] in {"operator", "operator_menu_enum"}}


def _labels(calls) -> list[str]:
    return [call[2].get("text", call[1][0] if call[1] else "") for call in calls if call[0] == "label"]


def test_every_setting_is_drawn(addon, recording_layout) -> None:
    settings = addon.properties.get_settings(bpy.context)
    _draw_all(addon, recording_layout)  # pixel-exact: depth px pair
    settings.pixel_exact = False
    _draw_all(addon, recording_layout)  # float mode: slope controls
    settings.inner_lines = "EDGES"
    _draw_all(addon, recording_layout)  # sharp-edge lines: crease angle and marked sharp
    assert _props(recording_layout.calls) == _all_settings(addon) - READOUTS


@pytest.mark.parametrize("mode", ["NONE", "OBJECTS", "MATERIALS"])
def test_edge_settings_only_in_edges_mode(addon, recording_layout, mode) -> None:
    settings = addon.properties.get_settings(bpy.context)
    settings.inner_lines = mode
    drawn = _props(_draw(addon.ui.OBLIQUE_RIG_PT_output, recording_layout))
    assert not drawn & {"crease_angle", "edge_marked_sharp"}
    settings.inner_lines = "EDGES"
    recording_layout.calls.clear()
    drawn = _props(_draw(addon.ui.OBLIQUE_RIG_PT_output, recording_layout))
    assert {"crease_angle", "edge_marked_sharp"} <= drawn


def test_pixel_exact_hides_the_float_slope_controls(addon, recording_layout) -> None:
    drawn = _props(_draw(addon.ui.OBLIQUE_RIG_PT_projection, recording_layout))
    assert {"depth_px_right", "depth_px_up"} <= drawn
    assert not drawn & {"slope_run", "slope_rise", "depth_scale"}


def test_every_operator_is_drawn(addon, recording_layout) -> None:
    drawn = _operators(_draw_all(addon, recording_layout))
    assert drawn == {cls.bl_idname for cls in addon.operators.CLASSES} | {
        "oblique_rig.render_guides",
        "oblique_rig.render_turnaround",
    }


def test_preset_menus_use_the_enum(addon, recording_layout) -> None:
    calls = _draw_all(addon, recording_layout)
    menus = {call[1] for call in calls if call[0] == "operator_menu_enum"}
    assert menus == {
        ("oblique_rig.apply_slope_preset", "preset"),
        ("oblique_rig.apply_resolution_preset", "preset"),
    }


def test_depth_readout(addon, recording_layout) -> None:
    labels = " ".join(_labels(_draw(addon.ui.OBLIQUE_RIG_PT_projection, recording_layout)))
    assert "1 unit depth = 16 px right, 8 px up" in labels


def test_invalid_projection_draws_a_message(addon, recording_layout) -> None:
    settings = addon.properties.get_settings(bpy.context)
    settings.depth_px_right = 0
    settings.depth_px_up = 0
    calls = _draw(addon.ui.OBLIQUE_RIG_PT_projection, recording_layout)
    assert any(call[0] == "label" and call[2].get("icon") == "ERROR" for call in calls)


def test_readouts_are_labels(addon, recording_layout) -> None:
    settings = addon.properties.get_settings(bpy.context)
    before = _labels(_draw(addon.ui.OBLIQUE_RIG_PT_frame, recording_layout))
    settings.last_footprint = "48 x 72 px"
    settings.last_warnings = "A / B overlap in depth"
    recording_layout.calls.clear()
    after = " ".join(_labels(_draw(addon.ui.OBLIQUE_RIG_PT_frame, recording_layout)))
    assert not any("48 x 72" in label for label in before)
    assert "48 x 72 px" in after and "A / B" in after


def test_status_label_follows_rig(addon, recording_layout) -> None:
    root = addon.ui.OBLIQUE_RIG_PT_sidebar
    before = " ".join(_labels(_draw(root, recording_layout)))
    bpy.ops.oblique_rig.build()
    recording_layout.calls.clear()
    after = " ".join(_labels(_draw(root, recording_layout)))
    assert before and after and before != after


def test_root_panel_is_only_status_and_view(addon, recording_layout) -> None:
    calls = _draw(addon.ui.OBLIQUE_RIG_PT_sidebar, recording_layout)
    assert _props(calls) == {"view_mode"}
    assert _operators(calls) == set()


def test_panel_metadata(addon) -> None:
    root = addon.ui.OBLIQUE_RIG_PT_sidebar
    assert not hasattr(root, "bl_parent_id") or not root.bl_parent_id
    for panel_cls in _panels(addon):
        assert panel_cls.bl_space_type == "VIEW_3D"
        assert panel_cls.bl_region_type == "UI"
        assert panel_cls.bl_category == "Oblique Rig"
        assert panel_cls.bl_idname == panel_cls.__name__
        assert panel_cls.bl_idname.startswith("OBLIQUE_RIG_PT_")
        assert panel_cls.is_registered
        if panel_cls is not root:
            assert panel_cls.bl_parent_id == root.bl_idname
    names = [cls.__name__ for cls in _panels(addon)]
    assert names[0] == root.__name__, "the parent registers before its sub-panels"
    orders = [cls.bl_order for cls in _panels(addon)[1:]]
    assert orders == sorted(orders) and len(set(orders)) == len(orders)


@pytest.mark.parametrize("pixel_exact", [True, False])
def test_panels_poll_headless(addon, pixel_exact) -> None:
    addon.properties.get_settings(bpy.context).pixel_exact = pixel_exact
    for panel_cls in _panels(addon):
        poll = getattr(panel_cls, "poll", None)
        if poll is not None:
            assert poll(bpy.context) in {True, False}


def test_preferences_draw(addon, recording_layout) -> None:
    prefs = addon.preferences.get_prefs(bpy.context)
    fake = type("FakePrefs", (), {"layout": recording_layout})()
    addon.preferences.OBLIQUE_RIG_Preferences.draw(fake, bpy.context)
    assert any(call[0] == "prop" and call[1][1] == "report_results" for call in recording_layout.calls)
    assert prefs is not None
