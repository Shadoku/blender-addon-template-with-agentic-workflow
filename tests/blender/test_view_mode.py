"""The View toggle shows either the source objects or the sheared rig, never both."""

import bpy


def _layer_collection(name: str):
    def find(lc):
        if lc.collection.name == name:
            return lc
        for child in lc.children:
            found = find(child)
            if found is not None:
                return found
        return None

    return find(bpy.context.view_layer.layer_collection)


def _rig_vertex_count(addon) -> int:
    rig = bpy.data.objects[addon.core.oblique.RIG_NAME]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    rig_eval = rig.evaluated_get(depsgraph)
    try:
        return len(rig_eval.to_mesh().vertices)
    finally:
        rig_eval.to_mesh_clear()


def test_default_is_sheared(addon) -> None:
    assert addon.properties.get_settings(bpy.context).view_mode == "SHEARED"


def test_build_hides_source_when_sheared(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.build()
    bpy.ops.oblique_rig.add_calibration()

    assert _layer_collection(o.SOURCE_COLLECTION).hide_viewport is True
    assert bpy.data.objects[o.RIG_NAME].hide_get() is False
    assert _rig_vertex_count(addon) == 20, "hiding the source with the eye icon keeps it in the depsgraph"


def test_toggle_to_source_shows_source_and_hides_rig(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.build()
    bpy.ops.oblique_rig.add_calibration()
    settings = addon.properties.get_settings(bpy.context)

    settings.view_mode = "SOURCE"
    assert _layer_collection(o.SOURCE_COLLECTION).hide_viewport is False
    assert bpy.data.objects[o.RIG_NAME].hide_get() is True

    settings.view_mode = "SHEARED"
    assert _layer_collection(o.SOURCE_COLLECTION).hide_viewport is True
    assert bpy.data.objects[o.RIG_NAME].hide_get() is False


def test_build_applies_current_mode(addon) -> None:
    o = addon.core.oblique
    addon.properties.get_settings(bpy.context).view_mode = "SOURCE"
    bpy.ops.oblique_rig.build()
    assert _layer_collection(o.SOURCE_COLLECTION).hide_viewport is False
    assert bpy.data.objects[o.RIG_NAME].hide_get() is True


def test_toggle_without_rig_is_harmless(addon) -> None:
    settings = addon.properties.get_settings(bpy.context)
    settings.view_mode = "SOURCE"
    settings.view_mode = "SHEARED"
    assert len(bpy.data.objects) == 0


def test_source_never_renders(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.build()
    for mode in ("SOURCE", "SHEARED"):
        addon.properties.get_settings(bpy.context).view_mode = mode
        assert bpy.data.collections[o.SOURCE_COLLECTION].hide_render is True
        assert bpy.data.objects[o.RIG_NAME].hide_render is False
