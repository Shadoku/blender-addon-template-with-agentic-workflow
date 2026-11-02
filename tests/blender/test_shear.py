"""The test that proves the rig works: the rig's evaluated mesh is the sheared source collection."""

import bpy
import pytest


def _evaluated_vertices(rig) -> list[tuple[float, float, float]]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    rig_eval = rig.evaluated_get(depsgraph)
    mesh = rig_eval.to_mesh()
    try:
        return [tuple(v.co) for v in mesh.vertices]
    finally:
        rig_eval.to_mesh_clear()


def _centroid(points):
    n = len(points)
    return tuple(sum(p[i] for p in points) / n for i in range(3))


def _build_with_calibration(addon):
    o = addon.core.oblique
    assert bpy.ops.oblique_rig.build() == {"FINISHED"}
    assert bpy.ops.oblique_rig.add_calibration() == {"FINISHED"}
    return bpy.data.objects[o.RIG_NAME]


def test_back_cube_is_shifted_by_depth(addon) -> None:
    o = addon.core.oblique
    rig = _build_with_calibration(addon)
    a, b = o.shear_coefficients(2.0, 1.0, 0.6)

    verts = _evaluated_vertices(rig)
    assert len(verts) == 8 + 8 + 4, "two cubes and a floor, realized into one mesh"

    back = [v for v in verts if 2.5 - 1e-4 <= v[1] <= 3.5 + 1e-4]
    front = [v for v in verts if -0.5 - 1e-4 <= v[1] <= 0.5 + 1e-4 and -1.0 <= v[0] <= 1.0]
    assert len(back) == 8 and len(front) == 8

    fx, fy, fz = _centroid(front)
    bx, by, bz = _centroid(back)
    assert (fx, fy, fz) == pytest.approx((0.0, 0.0, 0.5), abs=1e-5)
    assert by - fy == pytest.approx(3.0, abs=1e-5), "depth (y) is not sheared"
    assert bx - fx == pytest.approx(3 * a, abs=1e-5)
    assert bz - fz == pytest.approx(3 * b, abs=1e-5)


def test_every_vertex_matches_core_shear(addon) -> None:
    o = addon.core.oblique
    rig = _build_with_calibration(addon)
    a, b = o.shear_coefficients(2.0, 1.0, 0.6)

    expected = []
    for ob in bpy.data.collections[o.SOURCE_COLLECTION].all_objects:
        for v in ob.data.vertices:
            world = ob.matrix_world @ v.co
            expected.append(o.shear_point(tuple(world), a, b))

    got = sorted(_evaluated_vertices(rig))
    expected.sort()
    assert len(got) == len(expected)
    for g, e in zip(got, expected, strict=True):
        assert g == pytest.approx(e, abs=1e-5)


def test_shear_follows_settings(addon) -> None:
    o = addon.core.oblique
    settings = addon.properties.get_settings(bpy.context)
    settings.slope_run = 1.0
    settings.slope_rise = 1.0
    settings.depth_scale = 1.0
    rig = _build_with_calibration(addon)
    a, b = o.shear_coefficients(1.0, 1.0, 1.0)

    back = [v for v in _evaluated_vertices(rig) if 2.5 - 1e-4 <= v[1] <= 3.5 + 1e-4]
    bx, _, bz = _centroid(back)
    assert bx == pytest.approx(3 * a, abs=1e-5)
    assert bz == pytest.approx(0.5 + 3 * b, abs=1e-5)


def test_zero_depth_is_identity(addon) -> None:
    settings = addon.properties.get_settings(bpy.context)
    settings.depth_scale = 0.0
    rig = _build_with_calibration(addon)
    back = [v for v in _evaluated_vertices(rig) if 2.5 - 1e-4 <= v[1] <= 3.5 + 1e-4]
    assert _centroid(back) == pytest.approx((0.0, 3.0, 0.5), abs=1e-5)


def test_source_is_hidden_from_render(addon) -> None:
    o = addon.core.oblique
    _build_with_calibration(addon)
    assert bpy.data.collections[o.SOURCE_COLLECTION].hide_render is True
