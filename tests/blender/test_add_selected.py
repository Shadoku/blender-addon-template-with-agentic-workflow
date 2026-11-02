"""oblique_rig.add_selected moves the selected objects into the source collection and
places each one with its front edge at y = 0 and its origin (or bottom) at z = 0."""

import bpy
import pytest
from mathutils import Vector


def _mesh_object(addon, name: str, location, size: float = 2.0, select: bool = True):
    verts, faces = addon.core.primitives.cube(size)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    ob.select_set(select)
    return ob


def _world_bounds(ob):
    bpy.context.view_layer.update()
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return tuple(min(c[i] for c in corners) for i in range(3)), tuple(
        max(c[i] for c in corners) for i in range(3)
    )


def test_poll_needs_an_eligible_selection(addon) -> None:
    assert bpy.ops.oblique_rig.add_selected.poll() is False
    bpy.ops.oblique_rig.build()
    bpy.data.objects[addon.core.oblique.CAMERA_NAME].select_set(True)
    assert bpy.ops.oblique_rig.add_selected.poll() is False, "rig-owned objects are not candidates"
    _mesh_object(addon, "Asset", (0, 0, 0))
    assert bpy.ops.oblique_rig.add_selected.poll() is True


def test_moves_into_source_and_places_front_edge_and_origin(addon) -> None:
    o = addon.core.oblique
    ob = _mesh_object(addon, "Asset", (1.0, -2.0, 3.0))  # cube spans y -3..-1, z 2..4

    assert bpy.ops.oblique_rig.add_selected() == {"FINISHED"}

    assert [c.name for c in ob.users_collection] == [o.SOURCE_COLLECTION]
    lo, hi = _world_bounds(ob)
    assert lo[1] == pytest.approx(0.0), "front edge at y = 0"
    assert hi[1] == pytest.approx(2.0)
    assert ob.location.z == pytest.approx(0.0), "origin at z = 0"
    assert ob.location.x == pytest.approx(1.0), "x untouched"


def test_ground_by_bottom_option(addon) -> None:
    ob = _mesh_object(addon, "Asset", (0.0, 5.0, 7.0))  # z 6..8

    assert bpy.ops.oblique_rig.add_selected(ground_by_bottom=True) == {"FINISHED"}

    lo, _ = _world_bounds(ob)
    assert lo == pytest.approx((-1.0, 0.0, 0.0))
    assert ob.location.z == pytest.approx(1.0)


def test_unselected_and_rig_objects_are_left_alone(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.build()
    selected = _mesh_object(addon, "Asset", (0.0, -4.0, 0.0))
    bystander = _mesh_object(addon, "Bystander", (0.0, -4.0, 0.0), select=False)
    cam = bpy.data.objects[o.CAMERA_NAME]
    cam.select_set(True)
    cam_location = tuple(cam.location)

    assert bpy.ops.oblique_rig.add_selected() == {"FINISHED"}

    assert [c.name for c in selected.users_collection] == [o.SOURCE_COLLECTION]
    assert bystander.location.y == pytest.approx(-4.0)
    assert bystander.name in bpy.context.scene.collection.objects
    assert tuple(cam.location) == pytest.approx(cam_location)
    assert cam.name in bpy.context.scene.collection.objects


def test_added_object_appears_sheared_in_rig(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.build()
    _mesh_object(addon, "Asset", (0.0, 2.0, 0.0))  # after placement: y 0..2, z 0..2
    bpy.ops.oblique_rig.add_selected(ground_by_bottom=True)
    a, b = o.shear_coefficients(2.0, 1.0, 0.6)

    rig = bpy.data.objects[o.RIG_NAME]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    rig_eval = rig.evaluated_get(depsgraph)
    try:
        verts = [tuple(v.co) for v in rig_eval.to_mesh().vertices]
    finally:
        rig_eval.to_mesh_clear()
    assert len(verts) == 8
    assert min(v[1] for v in verts) == pytest.approx(0.0)
    assert min(v[2] for v in verts) >= -1e-6, "nothing at or behind the front plane shears below the floor"
    back_top = max(verts, key=lambda v: (v[1], v[2], v[0]))
    assert back_top[0] == pytest.approx(1.0 + 2 * a)
    assert back_top[2] == pytest.approx(2.0 + 2 * b)


def test_is_undoable(addon) -> None:
    assert addon.operators.OBLIQUE_RIG_OT_add_selected.bl_options == {"REGISTER", "UNDO"}
