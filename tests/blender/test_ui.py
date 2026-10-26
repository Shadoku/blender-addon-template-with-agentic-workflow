"""Blender never calls draw() in background mode. Calling it with a recording layout
at least proves the method runs against real context and references real properties."""

import bpy


def test_sidebar_panel_draws(addon, recording_layout) -> None:
    panel_cls = addon.ui.MY_ADDON_PT_sidebar
    fake_panel = type("FakePanel", (), {"layout": recording_layout})()

    panel_cls.draw(fake_panel, bpy.context)

    names = [call[0] for call in recording_layout.calls]
    assert "prop" in names and "operator" in names
    props_drawn = {call[1][1] for call in recording_layout.calls if call[0] == "prop"}
    assert props_drawn == {"axis", "gap"}
    operators_drawn = {call[1][0] for call in recording_layout.calls if call[0] == "operator"}
    assert operators_drawn == {addon.operators.MY_ADDON_OT_space_evenly.bl_idname}


def test_panel_metadata(addon) -> None:
    panel_cls = addon.ui.MY_ADDON_PT_sidebar
    assert panel_cls.bl_space_type == "VIEW_3D"
    assert panel_cls.bl_region_type == "UI"
    assert panel_cls.bl_idname == panel_cls.__name__


def test_preferences_draw(addon, recording_layout) -> None:
    prefs = addon.preferences.get_prefs(bpy.context)
    fake = type("FakePrefs", (), {"layout": recording_layout})()
    addon.preferences.MY_ADDON_Preferences.draw(fake, bpy.context)
    assert any(call[0] == "prop" and call[1][1] == "report_results" for call in recording_layout.calls)
    assert prefs is not None
