"""Blender never calls draw() in background mode. Calling it with a recording layout
at least proves the method runs against real context and references real properties."""

import bpy

SETTINGS = {
    "pixels_per_unit",
    "resolution_x",
    "resolution_y",
    "slope_run",
    "slope_rise",
    "depth_scale",
    "camera_height_fraction",
}


def _draw(addon, layout) -> list:
    fake_panel = type("FakePanel", (), {"layout": layout})()
    addon.ui.OBLIQUE_RIG_PT_sidebar.draw(fake_panel, bpy.context)
    return layout.calls


def test_sidebar_panel_draws_every_setting_and_operator(addon, recording_layout) -> None:
    calls = _draw(addon, recording_layout)

    props_drawn = {call[1][1] for call in calls if call[0] == "prop"}
    assert props_drawn == SETTINGS
    operators_drawn = {call[1][0] for call in calls if call[0] == "operator"}
    assert operators_drawn == {
        addon.operators.OBLIQUE_RIG_OT_build.bl_idname,
        addon.operators.OBLIQUE_RIG_OT_add_calibration.bl_idname,
        addon.operators.OBLIQUE_RIG_OT_remove.bl_idname,
    }


def _labels(calls) -> list[str]:
    return [call[2].get("text", call[1][0] if call[1] else "") for call in calls if call[0] == "label"]


def test_status_label_follows_rig(addon, recording_layout) -> None:
    before = " ".join(_labels(_draw(addon, recording_layout)))
    bpy.ops.oblique_rig.build()
    recording_layout.calls.clear()
    after = " ".join(_labels(_draw(addon, recording_layout)))
    assert before and after and before != after


def test_panel_metadata(addon) -> None:
    panel_cls = addon.ui.OBLIQUE_RIG_PT_sidebar
    assert panel_cls.bl_space_type == "VIEW_3D"
    assert panel_cls.bl_region_type == "UI"
    assert panel_cls.bl_category == "Oblique Rig"
    assert panel_cls.bl_idname == panel_cls.__name__


def test_preferences_draw(addon, recording_layout) -> None:
    prefs = addon.preferences.get_prefs(bpy.context)
    fake = type("FakePrefs", (), {"layout": recording_layout})()
    addon.preferences.OBLIQUE_RIG_Preferences.draw(fake, bpy.context)
    assert any(call[0] == "prop" and call[1][1] == "report_results" for call in recording_layout.calls)
    assert prefs is not None
