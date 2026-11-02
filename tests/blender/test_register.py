"""The add-on must enable, disable and re-enable within one session leaving nothing behind."""

import os

import addon_utils
import bpy

ADDON_MODULE = os.environ["ADDON_MODULE"]


def test_every_declared_class_is_registered(addon) -> None:
    for cls in addon.CLASSES:
        assert cls.is_registered, cls.__name__


def test_disable_then_enable_round_trip(addon) -> None:
    classes = list(addon.CLASSES)
    scene_attr = addon.properties.SCENE_ATTR
    handler = addon.handlers.on_load_post

    assert addon_utils.disable(ADDON_MODULE, default_set=True) is None
    try:
        for cls in classes:
            assert not hasattr(bpy.types, cls.__name__), f"{cls.__name__} still registered after disable"
        assert not hasattr(bpy.types.Scene, scene_attr), "Scene property not deleted in unregister()"
        assert handler not in bpy.app.handlers.load_post, "load_post handler left behind"
    finally:
        assert addon_utils.enable(ADDON_MODULE, default_set=True) is not None, "re-enable failed"

    assert hasattr(bpy.types.Scene, scene_attr)
    assert handler in bpy.app.handlers.load_post
    for idname in ("build", "add_calibration", "remove"):
        assert hasattr(bpy.types, f"OBLIQUE_RIG_OT_{idname}"), idname
        assert getattr(bpy.ops.oblique_rig, idname).idname_py() == f"oblique_rig.{idname}"


def test_expected_classes(addon) -> None:
    names = {cls.__name__ for cls in addon.CLASSES}
    assert names == {
        "OBLIQUE_RIG_Preferences",
        "OBLIQUE_RIG_Settings",
        "OBLIQUE_RIG_OT_build",
        "OBLIQUE_RIG_OT_add_calibration",
        "OBLIQUE_RIG_OT_remove",
        "OBLIQUE_RIG_PT_sidebar",
    }


def test_build_works_after_round_trip(addon) -> None:
    assert addon_utils.disable(ADDON_MODULE, default_set=True) is None
    assert addon_utils.enable(ADDON_MODULE, default_set=True) is not None
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}


def test_handler_is_persistent(addon) -> None:
    # @persistent sets this attribute (to None); without it the handler vanishes on file load.
    assert hasattr(addon.handlers.on_load_post, "_bpy_persistent")


def test_preferences_resolve_through_package(addon) -> None:
    prefs = addon.preferences.get_prefs(bpy.context)
    # bl_idname is a class attribute; reading it from the RNA instance returns garbage.
    assert type(prefs).bl_idname == ADDON_MODULE
    assert prefs.report_results is True
