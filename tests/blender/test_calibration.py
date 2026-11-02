import bpy
import pytest


def test_creates_three_objects_in_source(addon) -> None:
    o = addon.core.oblique
    assert bpy.ops.oblique_rig.add_calibration() == {"FINISHED"}

    source = bpy.data.collections[o.SOURCE_COLLECTION]
    assert source.name in bpy.context.scene.collection.children
    assert {ob.name for ob in source.objects} == {o.CALIB_FRONT, o.CALIB_BACK, o.CALIB_FLOOR}
    for name in (o.CALIB_FRONT, o.CALIB_BACK, o.CALIB_FLOOR):
        ob = bpy.data.objects[name]
        assert ob.type == "MESH"
        assert [c.name for c in ob.users_collection] == [o.SOURCE_COLLECTION]


def test_geometry(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.add_calibration()

    front = bpy.data.objects[o.CALIB_FRONT]
    back = bpy.data.objects[o.CALIB_BACK]
    floor = bpy.data.objects[o.CALIB_FLOOR]
    assert (len(front.data.vertices), len(front.data.polygons)) == (8, 6)
    assert (len(floor.data.vertices), len(floor.data.polygons)) == (4, 1)
    assert tuple(front.location) == pytest.approx((0.0, 0.5, 0.5)), "front edge at y = 0"
    assert tuple(back.location) == pytest.approx((0.0, 3.5, 0.5)), "3 units behind the front cube"
    assert tuple(front.dimensions) == pytest.approx((1.0, 1.0, 1.0))
    assert tuple(floor.dimensions) == pytest.approx((6.0, 5.0, 0.0))
    assert tuple(floor.location) == pytest.approx((0.0, 2.5, 0.0)), "floor spans y 0..5"


def test_idempotent(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.add_calibration()
    bpy.data.objects[o.CALIB_BACK].location.x = 4.0  # a user tweak survives a re-run
    assert bpy.ops.oblique_rig.add_calibration() == {"FINISHED"}

    names = sorted(ob.name for ob in bpy.data.objects)
    assert names == sorted([o.CALIB_FRONT, o.CALIB_BACK, o.CALIB_FLOOR])
    assert len(bpy.data.meshes) == 3
    assert bpy.data.objects[o.CALIB_BACK].location.x == pytest.approx(4.0)


def test_recreates_only_missing(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.add_calibration()
    bpy.data.objects.remove(bpy.data.objects[o.CALIB_FLOOR])
    bpy.ops.oblique_rig.add_calibration()
    assert {ob.name for ob in bpy.data.objects} == {o.CALIB_FRONT, o.CALIB_BACK, o.CALIB_FLOOR}


def test_two_flat_materials(addon) -> None:
    o = addon.core.oblique
    r = addon.rig
    bpy.ops.oblique_rig.add_calibration()

    cube_mat = bpy.data.materials[r.CALIB_CUBE_MATERIAL]
    floor_mat = bpy.data.materials[r.CALIB_FLOOR_MATERIAL]
    assert cube_mat != floor_mat
    assert tuple(cube_mat.diffuse_color) == pytest.approx(r.CALIB_CUBE_COLOR)
    assert tuple(floor_mat.diffuse_color) == pytest.approx(r.CALIB_FLOOR_COLOR)
    assert r.CALIB_CUBE_COLOR == pytest.approx((0.85, 0.35, 0.2, 1.0))
    assert r.CALIB_FLOOR_COLOR == pytest.approx((0.3, 0.6, 0.3, 1.0))
    assert list(bpy.data.objects[o.CALIB_FRONT].data.materials) == [cube_mat]
    assert list(bpy.data.objects[o.CALIB_BACK].data.materials) == [cube_mat]
    assert list(bpy.data.objects[o.CALIB_FLOOR].data.materials) == [floor_mat]


def test_materials_are_reused(addon) -> None:
    o = addon.core.oblique
    bpy.ops.oblique_rig.add_calibration()
    bpy.data.objects.remove(bpy.data.objects[o.CALIB_FRONT])
    bpy.ops.oblique_rig.add_calibration()
    assert sorted(m.name for m in bpy.data.materials) == sorted(
        [addon.rig.CALIB_CUBE_MATERIAL, addon.rig.CALIB_FLOOR_MATERIAL]
    )


def test_is_undoable(addon) -> None:
    assert addon.operators.OBLIQUE_RIG_OT_add_calibration.bl_options == {"REGISTER", "UNDO"}
