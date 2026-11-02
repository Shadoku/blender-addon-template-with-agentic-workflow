"""Edge IDs: the node group splits the source along sharp edges and stores one colour per island.

Evaluated geometry only, no rendering: with the modifier input "Edge IDs" on,
the rig's evaluated mesh carries the corner colour attribute
``core.edge_ids.EDGE_ID_ATTRIBUTE``; decoding its values with
``core.edge_ids.island_index`` counts the islands the EDGES outline pass will
draw lines between.
"""

import math

import bpy
import pytest


def _modifier(addon):
    o = addon.core.oblique
    return bpy.data.objects[o.RIG_NAME].modifiers[o.MODIFIER_NAME]


def _set(addon, **inputs) -> None:
    mod = _modifier(addon)
    for name, value in inputs.items():
        addon.rig.set_modifier_input(mod, name, value)
    mod.id_data.update_tag()


def _edge_ids_on(addon, crease_degrees: float = 30.0, marked_sharp: bool = True) -> None:
    _set(
        addon,
        **{"Edge IDs": True, "Crease Angle": math.radians(crease_degrees), "Marked Sharp": marked_sharp},
    )


def _evaluated(addon):
    """(island colours as byte tuples per corner, vertex count, active colour name) of the evaluated rig."""
    edge_ids = addon.core.edge_ids
    rig = bpy.data.objects[addon.core.oblique.RIG_NAME]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    rig_eval = rig.evaluated_get(depsgraph)
    mesh = rig_eval.to_mesh()
    try:
        attr = mesh.attributes.get(edge_ids.EDGE_ID_ATTRIBUTE)
        colours = None
        if attr is not None:
            assert (attr.domain, attr.data_type) == ("CORNER", "FLOAT_COLOR")
            colours = [tuple(round(c * 255) for c in item.color[:3]) for item in attr.data]
        active = mesh.color_attributes.active_color_name
        return colours, len(mesh.vertices), active
    finally:
        rig_eval.to_mesh_clear()


def _islands(addon) -> set[int]:
    colours, _, _ = _evaluated(addon)
    assert colours is not None, "Edge IDs on: the evaluated mesh carries the island colours"
    edge_ids = addon.core.edge_ids
    indices = {edge_ids.island_index(c) for c in colours}
    # Exact encoding: every colour is precisely island_color(index), no rounding drift.
    assert {edge_ids.island_color(i) for i in indices} == set(colours)
    return indices


def _mesh_object(addon, name: str, verts, faces, location=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    ob.location = location
    addon.rig.get_or_create_collection(bpy.context.scene).objects.link(ob)
    return ob


def _two_face_plane(addon) -> bpy.types.Object:
    """A flat 2 x 1 plane of two quads sharing the edge between vertices 1 and 4."""
    verts = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)]
    return _mesh_object(addon, "Plane", verts, [(0, 1, 4, 3), (1, 2, 5, 4)])


def _mark_middle_edge_sharp(ob) -> None:
    mesh = ob.data
    [edge] = [e for e in mesh.edges if set(e.vertices) == {1, 4}]
    edge.use_edge_sharp = True  # writes the "sharp_edge" attribute on 4.5 and 5.2
    mesh.update()
    attr = mesh.attributes["sharp_edge"]
    assert (attr.domain, attr.data_type) == ("EDGE", "BOOLEAN")
    assert [item.value for item in attr.data].count(True) == 1


def _cylinder(addon, segments: int = 24) -> bpy.types.Object:
    """A closed prism: ``segments`` side quads (360/segments degrees apart) and two n-gon caps."""
    ring = [
        (math.cos(2 * math.pi * k / segments), math.sin(2 * math.pi * k / segments)) for k in range(segments)
    ]
    verts = [(x, y, 0.0) for x, y in ring] + [(x, y, 2.0) for x, y in ring]
    sides = [(k, (k + 1) % segments, segments + (k + 1) % segments, segments + k) for k in range(segments)]
    bottom = tuple(reversed(range(segments)))
    top = tuple(range(segments, 2 * segments))
    return _mesh_object(addon, "Cylinder", verts, [*sides, bottom, top])


def test_edge_ids_off_stores_nothing(addon, source_box) -> None:
    bpy.ops.oblique_rig.build()
    source_box("Cube", (0, 0, 0), (1, 1, 1))
    colours, vertex_count, _ = _evaluated(addon)
    assert colours is None
    assert vertex_count == 8, "the rig's helper vertex never shows up in the normal output"


def test_cube_splits_into_six_islands(addon, source_box) -> None:
    bpy.ops.oblique_rig.build()
    source_box("Cube", (0, 0, 0), (1, 1, 1))
    _edge_ids_on(addon)
    assert _islands(addon) == set(range(6))
    _, vertex_count, active = _evaluated(addon)
    assert vertex_count == 24, "six separate quads, and the helper vertex is deleted"
    assert active == addon.core.edge_ids.EDGE_ID_ATTRIBUTE, "Workbench VERTEX mode renders the active one"


def test_island_attribute_wins_over_a_source_colour_attribute(addon, source_box) -> None:
    """A source mesh's own active colour attribute must not hijack the EDGES render."""
    bpy.ops.oblique_rig.build()
    cube = source_box("Cube", (0, 0, 0), (1, 1, 1))
    cube.data.color_attributes.new("Col", "BYTE_COLOR", "POINT")
    cube.data.color_attributes.active_color_name = "Col"
    _edge_ids_on(addon)
    _, _, active = _evaluated(addon)
    assert active == addon.core.edge_ids.EDGE_ID_ATTRIBUTE


def test_two_objects_are_two_islands_even_when_flat(addon, source_box) -> None:
    bpy.ops.oblique_rig.build()
    source_box("A", (0, 0, 0), (1, 1, 1))
    source_box("B", (2, 0, 0), (3, 1, 1))
    _edge_ids_on(addon, crease_degrees=180.0)  # nothing is sharper than 180 degrees
    assert len(_islands(addon)) == 2


def test_marked_sharp_edge_splits_a_flat_plane(addon) -> None:
    bpy.ops.oblique_rig.build()
    _mark_middle_edge_sharp(_two_face_plane(addon))
    _edge_ids_on(addon)
    assert len(_islands(addon)) == 2


def test_marked_sharp_off_ignores_the_mark(addon) -> None:
    bpy.ops.oblique_rig.build()
    _mark_middle_edge_sharp(_two_face_plane(addon))
    _edge_ids_on(addon, marked_sharp=False)
    assert len(_islands(addon)) == 1


def test_unmarked_flat_plane_is_one_island(addon) -> None:
    bpy.ops.oblique_rig.build()
    _two_face_plane(addon)
    _edge_ids_on(addon)
    assert len(_islands(addon)) == 1


@pytest.mark.parametrize(("crease_degrees", "islands"), [(30.0, 3), (10.0, 26)])
def test_cylinder_crease_angle(addon, crease_degrees, islands) -> None:
    """24 segments meet at 15 degrees: one smooth side at 30, every side face its own island at 10."""
    bpy.ops.oblique_rig.build()
    _cylinder(addon)
    _edge_ids_on(addon, crease_degrees=crease_degrees)
    assert len(_islands(addon)) == islands


def test_angles_are_measured_before_the_shear(addon, source_box) -> None:
    """A strong shear bends the cube's 90-degree corners, but not the edge angles used for the split."""
    settings = addon.properties.get_settings(bpy.context)
    settings.depth_px_right = 64
    settings.depth_px_up = 64
    bpy.ops.oblique_rig.build()
    source_box("Cube", (0, 0, 0), (1, 1, 1))
    _edge_ids_on(addon, crease_degrees=89.0)
    assert len(_islands(addon)) == 6
    _edge_ids_on(addon, crease_degrees=91.0)
    assert len(_islands(addon)) == 1


def test_build_settings_reach_the_modifier(addon) -> None:
    settings = addon.properties.get_settings(bpy.context)
    settings.crease_angle = math.radians(45)
    settings.edge_marked_sharp = False
    bpy.ops.oblique_rig.build()
    mod = _modifier(addon)
    assert addon.rig.get_modifier_input(mod, "Crease Angle") == pytest.approx(math.radians(45))
    assert addon.rig.get_modifier_input(mod, "Marked Sharp") is False
    assert addon.rig.get_modifier_input(mod, "Edge IDs") is False, "only the EDGES render pass turns it on"
