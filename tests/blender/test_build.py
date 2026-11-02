"""oblique_rig.build creates (or updates) every piece of the rig from the scene settings."""

import math

import bpy
import pytest


def _names(addon):
    return addon.core.oblique


def test_build_creates_rig(addon) -> None:
    o = _names(addon)
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}

    source = bpy.data.collections.get(o.SOURCE_COLLECTION)
    assert source is not None
    assert source.name in bpy.context.scene.collection.children
    assert source.hide_render is True

    rig = bpy.data.objects.get(o.RIG_NAME)
    assert rig is not None and rig.type == "MESH"
    assert rig.name in bpy.context.scene.collection.objects
    mod = rig.modifiers.get(o.MODIFIER_NAME)
    assert mod is not None and mod.type == "NODES"
    assert mod.node_group == bpy.data.node_groups[o.NODEGROUP_NAME]
    assert addon.rig.get_modifier_input(mod, "Source Collection") == source
    assert addon.rig.get_modifier_input(mod, "Slope Run") == pytest.approx(2.0)
    assert addon.rig.get_modifier_input(mod, "Slope Rise") == pytest.approx(1.0)
    assert addon.rig.get_modifier_input(mod, "Depth Scale") == pytest.approx(0.6)


def test_node_group_layout(addon) -> None:
    o = _names(addon)
    bpy.ops.oblique_rig.build()
    ng = bpy.data.node_groups[o.NODEGROUP_NAME]
    assert ng.bl_idname == "GeometryNodeTree"

    inputs = [i.name for i in ng.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"]
    outputs = [i.name for i in ng.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "OUTPUT"]
    assert inputs == ["Geometry", "Source Collection", "Slope Run", "Slope Rise", "Depth Scale"]
    assert outputs == ["Geometry"]
    depth = next(i for i in ng.interface.items_tree if i.name == "Depth Scale")
    assert (depth.min_value, depth.max_value) == pytest.approx((0.0, 2.0))

    kinds = {n.bl_idname for n in ng.nodes}
    for needed in (
        "GeometryNodeCollectionInfo",
        "GeometryNodeTransform",
        "FunctionNodeCombineMatrix",
        "GeometryNodeRealizeInstances",
    ):
        assert needed in kinds

    coll_info = next(n for n in ng.nodes if n.bl_idname == "GeometryNodeCollectionInfo")
    assert coll_info.transform_space == "RELATIVE"
    transform = next(n for n in ng.nodes if n.bl_idname == "GeometryNodeTransform")
    if "Mode" in transform.inputs:
        assert transform.inputs["Mode"].default_value == "Matrix"
    else:
        assert transform.mode == "MATRIX"

    # Transform -> Realize Instances -> Group Output
    realize = next(n for n in ng.nodes if n.bl_idname == "GeometryNodeRealizeInstances")
    out = next(n for n in ng.nodes if n.bl_idname == "NodeGroupOutput")
    assert any(link.from_node == transform and link.to_node == realize for link in ng.links)
    assert any(link.from_node == realize and link.to_node == out for link in ng.links)


def test_camera(addon) -> None:
    o = _names(addon)
    bpy.ops.oblique_rig.build()
    cam = bpy.data.objects[o.CAMERA_NAME]
    assert cam.type == "CAMERA"
    assert cam.data.type == "ORTHO"
    assert cam.data.ortho_scale == pytest.approx(20.0)
    assert cam.rotation_euler.x == pytest.approx(math.pi / 2)
    assert tuple(cam.location) == pytest.approx(o.camera_location(200, 16, 0.35))
    assert bpy.context.scene.camera == cam


def test_sun(addon) -> None:
    o = _names(addon)
    bpy.ops.oblique_rig.build()
    sun = bpy.data.objects[o.SUN_NAME]
    assert sun.type == "LIGHT"
    assert sun.data.type == "SUN"
    assert sun.name in bpy.context.scene.collection.objects


def test_render_settings(addon) -> None:
    bpy.ops.oblique_rig.build()
    scene = bpy.context.scene
    r = scene.render
    assert (r.resolution_x, r.resolution_y, r.resolution_percentage) == (320, 200, 100)
    assert r.filter_size == 0.0
    assert r.film_transparent is True
    assert r.image_settings.color_mode == "RGBA"
    assert "EEVEE" in r.engine
    assert scene.view_settings.view_transform == "Standard"
    assert scene.eevee.taa_render_samples == 1


def test_build_uses_settings(addon) -> None:
    o = _names(addon)
    settings = addon.properties.get_settings(bpy.context)
    settings.resolution_x = 640
    settings.resolution_y = 480
    settings.pixels_per_unit = 32
    settings.camera_height_fraction = 0.5

    bpy.ops.oblique_rig.build()

    r = bpy.context.scene.render
    assert (r.resolution_x, r.resolution_y) == (640, 480)
    cam = bpy.data.objects[o.CAMERA_NAME]
    assert cam.data.ortho_scale == pytest.approx(20.0)
    assert cam.location.z == pytest.approx(480 / 32 * 0.5)


def test_build_twice_is_idempotent(addon) -> None:
    o = _names(addon)
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}

    for name in (o.RIG_NAME, o.CAMERA_NAME, o.SUN_NAME):
        matches = [ob for ob in bpy.data.objects if ob.name.startswith(name)]
        assert [ob.name for ob in matches] == [name]
    assert [ng.name for ng in bpy.data.node_groups] == [o.NODEGROUP_NAME]
    assert [c.name for c in bpy.data.collections] == [o.SOURCE_COLLECTION]
    assert [c.name for c in bpy.data.cameras] == [o.CAMERA_NAME]
    assert [m.name for m in bpy.data.objects[o.RIG_NAME].modifiers] == [o.MODIFIER_NAME]


def test_rebuild_updates_modifier_inputs(addon) -> None:
    o = _names(addon)
    settings = addon.properties.get_settings(bpy.context)
    bpy.ops.oblique_rig.build()

    settings.depth_scale = 1.0
    settings.slope_run = 1.0
    bpy.ops.oblique_rig.build()

    mod = bpy.data.objects[o.RIG_NAME].modifiers[o.MODIFIER_NAME]
    assert addon.rig.get_modifier_input(mod, "Depth Scale") == pytest.approx(1.0)
    assert addon.rig.get_modifier_input(mod, "Slope Run") == pytest.approx(1.0)


def test_rebuild_keeps_user_modifiers(addon) -> None:
    o = _names(addon)
    bpy.ops.oblique_rig.build()
    rig = bpy.data.objects[o.RIG_NAME]
    rig.modifiers.new("UserWeld", "WELD")
    bpy.ops.oblique_rig.build()
    assert [m.name for m in rig.modifiers] == [o.MODIFIER_NAME, "UserWeld"]


def test_zero_slope_disables_build(addon) -> None:
    o = _names(addon)
    settings = addon.properties.get_settings(bpy.context)
    assert bpy.ops.oblique_rig.build.poll() is True
    settings.slope_run = 0.0
    settings.slope_rise = 0.0
    assert bpy.ops.oblique_rig.build.poll() is False
    settings.slope_rise = 0.5
    assert bpy.ops.oblique_rig.build.poll() is True
    settings.slope_rise = 0.0

    with pytest.raises(RuntimeError, match="poll"):
        bpy.ops.oblique_rig.build()
    assert bpy.data.objects.get(o.RIG_NAME) is None


def test_build_relinks_unlinked_source_collection(addon) -> None:
    o = _names(addon)
    bpy.ops.oblique_rig.build()
    scene_children = bpy.context.scene.collection.children
    scene_children.unlink(bpy.data.collections[o.SOURCE_COLLECTION])
    bpy.ops.oblique_rig.build()
    assert o.SOURCE_COLLECTION in scene_children


def test_build_is_undoable(addon) -> None:
    assert addon.operators.OBLIQUE_RIG_OT_build.bl_options == {"REGISTER", "UNDO"}
