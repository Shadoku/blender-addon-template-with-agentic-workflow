import bpy


def _rig_names(o) -> set[str]:
    return {
        o.SOURCE_COLLECTION,
        o.RIG_NAME,
        o.NODEGROUP_NAME,
        o.CAMERA_NAME,
        o.SUN_NAME,
        o.CALIB_FRONT,
        o.CALIB_BACK,
        o.CALIB_FLOOR,
    }


def _leftovers(o) -> dict[str, list[str]]:
    names = _rig_names(o)
    out = {}
    for attr in ("objects", "collections", "node_groups", "cameras", "lights", "meshes"):
        found = [block.name for block in getattr(bpy.data, attr) if block.name in names]
        if found:
            out[attr] = found
    return out


def _build_everything():
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    assert bpy.ops.oblique_rig.add_calibration() == {"FINISHED"}


def test_remove_everything(addon) -> None:
    o = addon.core.oblique
    _build_everything()
    assert bpy.ops.oblique_rig.remove(include_source=True) == {"FINISHED"}
    assert _leftovers(o) == {}
    assert bpy.context.scene.camera is None
    assert addon.rig.CALIB_CUBE_MATERIAL not in bpy.data.materials
    assert addon.rig.CALIB_FLOOR_MATERIAL not in bpy.data.materials


def test_remove_keeps_source_by_default(addon) -> None:
    o = addon.core.oblique
    _build_everything()
    assert bpy.ops.oblique_rig.remove() == {"FINISHED"}

    left = _leftovers(o)
    assert set(left["objects"]) == {o.CALIB_FRONT, o.CALIB_BACK, o.CALIB_FLOOR}
    assert left["collections"] == [o.SOURCE_COLLECTION]
    assert "node_groups" not in left and "cameras" not in left and "lights" not in left
    assert set(left["meshes"]) == {o.CALIB_FRONT, o.CALIB_BACK, o.CALIB_FLOOR}


def test_remove_source_keeps_user_assets(addon, make_object) -> None:
    o = addon.core.oblique
    _build_everything()
    asset = make_object("My Asset")
    bpy.context.scene.collection.objects.unlink(asset)
    bpy.data.collections[o.SOURCE_COLLECTION].objects.link(asset)

    bpy.ops.oblique_rig.remove(include_source=True)

    assert "My Asset" in bpy.data.objects
    assert asset.name in bpy.context.scene.collection.objects, "user asset moved out, not orphaned"


def test_remove_source_keeps_user_child_collections(addon) -> None:
    o = addon.core.oblique
    _build_everything()
    child = bpy.data.collections.new("My Props")
    bpy.data.collections[o.SOURCE_COLLECTION].children.link(child)

    bpy.ops.oblique_rig.remove(include_source=True)

    assert "My Props" in bpy.context.scene.collection.children


def test_remove_leaves_unrelated_data(addon, make_object) -> None:
    _build_everything()
    make_object("Bystander")
    bpy.ops.oblique_rig.remove(include_source=True)
    assert [ob.name for ob in bpy.data.objects] == ["Bystander"]


def test_remove_on_empty_scene(addon) -> None:
    assert bpy.ops.oblique_rig.remove(include_source=True) == {"FINISHED"}


def test_rebuild_after_remove(addon) -> None:
    o = addon.core.oblique
    _build_everything()
    bpy.ops.oblique_rig.remove(include_source=True)
    _build_everything()
    assert o.RIG_NAME in bpy.data.objects
    assert o.CALIB_FRONT in bpy.data.objects


def test_is_undoable(addon) -> None:
    assert addon.operators.OBLIQUE_RIG_OT_remove.bl_options == {"REGISTER", "UNDO"}
