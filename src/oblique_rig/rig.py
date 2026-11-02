# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-facing builders for the oblique rig.

Each function creates or updates one piece of the rig by name, so every call is
idempotent: running it twice leaves one of everything. The maths (shear
coefficients, camera placement, primitive vertices) lives in ``core``; this
module only turns those numbers into datablocks.

API differences between Blender 4.5 LTS and 5.x handled here:

- The EEVEE engine identifier differs (see ``set_eevee_engine``).
- Transform Geometry's matrix mode is a node property (``node.mode``) in 4.5
  and a menu input socket (``inputs["Mode"]``) in 5.0+.
- Geometry Nodes modifier inputs are ID properties (``mod["Socket_1"]``) in 4.5;
  5.2 refuses that and exposes ``mod.properties.inputs.Socket_1.value``.
"""

import math
from typing import Any

import bpy

from .core import oblique, primitives
from .core.oblique import (
    CALIB_BACK,
    CALIB_FLOOR,
    CALIB_FRONT,
    CAMERA_NAME,
    MODIFIER_NAME,
    NODEGROUP_NAME,
    RIG_NAME,
    SOURCE_COLLECTION,
    SUN_NAME,
)

# (name, location, builder) for the calibration objects: two unit cubes 3 units
# apart in depth and a 6x5 floor under them.
CALIBRATION = (
    (CALIB_FRONT, (0.0, 0.0, 0.5), lambda: primitives.cube(1.0)),
    (CALIB_BACK, (0.0, 3.0, 0.5), lambda: primitives.cube(1.0)),
    (CALIB_FLOOR, (0.0, 2.0, 0.0), lambda: primitives.plane(6.0, 5.0)),
)


# --------------------------------------------------------------------------- version shims


def set_transform_mode_matrix(node: bpy.types.Node) -> None:
    """Switch a Transform Geometry node to matrix mode on 4.5 (property) and 5.x (menu socket)."""
    mode_input = node.inputs.get("Mode")
    if mode_input is not None:
        mode_input.default_value = "Matrix"
    else:
        node.mode = "MATRIX"


def set_eevee_engine(scene: bpy.types.Scene) -> str:
    """Set the scene to EEVEE under whichever identifier this Blender uses; return it.

    4.5 lists only the "EEVEE Next" identifier, 5.0+ only ``BLENDER_EEVEE``.
    Picking it from the enum avoids naming either spelling.
    """
    engines = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    eevee = next((engine for engine in engines if "EEVEE" in engine), None)
    if eevee is None:
        raise RuntimeError(f"no EEVEE render engine among {engines}")
    scene.render.engine = eevee
    return eevee


def _input_identifier(group: bpy.types.NodeTree, name: str) -> str:
    for item in group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            return item.identifier
    raise KeyError(f"node group {group.name!r} has no input {name!r}")


def set_modifier_input(mod: bpy.types.Modifier, name: str, value: Any) -> None:
    """Set a Geometry Nodes modifier input by its interface name."""
    identifier = _input_identifier(mod.node_group, name)
    props = getattr(mod, "properties", None)
    if props is not None:  # 5.2+
        getattr(props.inputs, identifier).value = value
    else:  # 4.5 .. 5.1
        mod[identifier] = value


def get_modifier_input(mod: bpy.types.Modifier, name: str) -> Any:
    """Read a Geometry Nodes modifier input by its interface name."""
    identifier = _input_identifier(mod.node_group, name)
    props = getattr(mod, "properties", None)
    if props is not None:
        return getattr(props.inputs, identifier).value
    return mod[identifier]


# --------------------------------------------------------------------------- helpers


def _link_to_scene(scene: bpy.types.Scene, ob: bpy.types.Object) -> None:
    if not ob.users_collection:
        scene.collection.objects.link(ob)


def _get_or_create_object(scene: bpy.types.Scene, name: str, make_data) -> tuple[bpy.types.Object, bool]:
    ob = bpy.data.objects.get(name)
    created = ob is None
    if created:
        ob = bpy.data.objects.new(name, make_data())
    _link_to_scene(scene, ob)
    return ob, created


# --------------------------------------------------------------------------- builders


def get_or_create_collection(scene: bpy.types.Scene, name: str = SOURCE_COLLECTION) -> bpy.types.Collection:
    """The source collection, linked under the scene collection if it is not in the scene yet."""
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll not in scene.collection.children_recursive:
        scene.collection.children.link(coll)
    coll.hide_render = True  # only the sheared copy renders
    return coll


def build_shear_nodegroup(name: str = NODEGROUP_NAME) -> bpy.types.NodeTree:
    """(Re)build the Geometry Nodes group that pulls in a collection and shears it.

    Collection Info -> Transform Geometry (matrix from Combine Matrix fed by
    normalize(run, rise, 0) * depth) -> Realize Instances -> Group Output.
    Realizing makes the rig's evaluated mesh real geometry, which tests and
    exporters can read.
    """
    ng = bpy.data.node_groups.get(name)
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.nodes.clear()
    ng.links.clear()
    ng.interface.clear()

    iface = ng.interface
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    iface.new_socket("Source Collection", in_out="INPUT", socket_type="NodeSocketCollection")
    s_run = iface.new_socket("Slope Run", in_out="INPUT", socket_type="NodeSocketFloat")
    s_rise = iface.new_socket("Slope Rise", in_out="INPUT", socket_type="NodeSocketFloat")
    s_depth = iface.new_socket("Depth Scale", in_out="INPUT", socket_type="NodeSocketFloat")
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    s_run.default_value = 2.0
    s_rise.default_value = 1.0
    s_run.min_value = s_rise.min_value = 0.0
    s_depth.default_value = 0.6
    s_depth.min_value = 0.0
    s_depth.max_value = 2.0

    nodes, links = ng.nodes, ng.links

    def add(bl_idname: str, x: float, y: float) -> bpy.types.Node:
        node = nodes.new(bl_idname)
        node.location = (x, y)
        return node

    n_in = add("NodeGroupInput", -900, 0)
    n_out = add("NodeGroupOutput", 900, 0)

    n_coll = add("GeometryNodeCollectionInfo", -600, 150)
    n_coll.transform_space = "RELATIVE"
    n_coll.inputs["Separate Children"].default_value = False
    n_coll.inputs["Reset Children"].default_value = False

    n_dir = add("ShaderNodeCombineXYZ", -600, -200)
    n_dir.inputs["Z"].default_value = 0.0
    n_norm = add("ShaderNodeVectorMath", -400, -200)
    n_norm.operation = "NORMALIZE"
    n_scale = add("ShaderNodeVectorMath", -200, -200)
    n_scale.operation = "SCALE"
    n_sep = add("ShaderNodeSeparateXYZ", 0, -200)

    n_mat = add("FunctionNodeCombineMatrix", 200, -200)
    identity = oblique.shear_matrix_columns(0.0, 0.0)
    for index, value in enumerate(identity):
        n_mat.inputs[index].default_value = value

    n_xform = add("GeometryNodeTransform", 450, 0)
    set_transform_mode_matrix(n_xform)
    n_realize = add("GeometryNodeRealizeInstances", 680, 0)

    links.new(n_in.outputs["Source Collection"], n_coll.inputs["Collection"])
    links.new(n_in.outputs["Slope Run"], n_dir.inputs["X"])
    links.new(n_in.outputs["Slope Rise"], n_dir.inputs["Y"])
    links.new(n_dir.outputs[0], n_norm.inputs[0])
    links.new(n_norm.outputs[0], n_scale.inputs[0])
    links.new(n_in.outputs["Depth Scale"], n_scale.inputs["Scale"])
    links.new(n_scale.outputs[0], n_sep.inputs[0])
    # Column-major: index 4 is "Column 2 Row 1" (X' += a*Y), index 6 "Column 2 Row 3" (Z' += b*Y).
    links.new(n_sep.outputs["X"], n_mat.inputs[1 * 4 + 0])
    links.new(n_sep.outputs["Y"], n_mat.inputs[1 * 4 + 2])

    links.new(n_coll.outputs["Instances"], n_xform.inputs["Geometry"])
    links.new(n_mat.outputs["Matrix"], n_xform.inputs["Transform"])
    links.new(n_xform.outputs["Geometry"], n_realize.inputs["Geometry"])
    links.new(n_realize.outputs["Geometry"], n_out.inputs["Geometry"])
    return ng


def build_rig_object(
    scene: bpy.types.Scene,
    group: bpy.types.NodeTree,
    source: bpy.types.Collection,
    slope_run: float,
    slope_rise: float,
    depth_scale: float,
) -> bpy.types.Object:
    """The object whose Geometry Nodes modifier shows the sheared source collection.

    Only the modifier named ``MODIFIER_NAME`` is touched; other modifiers the
    user added stay.
    """
    rig, _ = _get_or_create_object(scene, RIG_NAME, lambda: bpy.data.meshes.new(RIG_NAME))
    rig.location = (0.0, 0.0, 0.0)
    rig.rotation_euler = (0.0, 0.0, 0.0)
    rig.scale = (1.0, 1.0, 1.0)

    mod = rig.modifiers.get(MODIFIER_NAME)
    if mod is not None and mod.type != "NODES":
        rig.modifiers.remove(mod)
        mod = None
    if mod is None:
        mod = rig.modifiers.new(MODIFIER_NAME, "NODES")
        if len(rig.modifiers) > 1:
            rig.modifiers.move(len(rig.modifiers) - 1, 0)
    mod.node_group = group

    set_modifier_input(mod, "Source Collection", source)
    set_modifier_input(mod, "Slope Run", slope_run)
    set_modifier_input(mod, "Slope Rise", slope_rise)
    set_modifier_input(mod, "Depth Scale", depth_scale)
    rig.update_tag()
    return rig


def build_camera(
    scene: bpy.types.Scene,
    resolution_x: int,
    resolution_y: int,
    pixels_per_unit: int,
    height_fraction: float,
) -> bpy.types.Object:
    """Orthographic camera looking straight down +Y, sized so one unit is ``pixels_per_unit`` px."""
    cam, _ = _get_or_create_object(scene, CAMERA_NAME, lambda: bpy.data.cameras.new(CAMERA_NAME))
    data = cam.data
    data.type = "ORTHO"
    data.ortho_scale = oblique.ortho_scale(resolution_x, resolution_y, pixels_per_unit)
    data.clip_start = 0.1
    data.clip_end = 1000.0
    # Rotated 90 degrees about X: screen x = world X, screen y = world Z.
    cam.location = oblique.camera_location(resolution_y, pixels_per_unit, height_fraction)
    cam.rotation_euler = (math.pi / 2, 0.0, 0.0)
    scene.camera = cam
    return cam


def setup_render(scene: bpy.types.Scene, resolution_x: int, resolution_y: int) -> None:
    """Flat, unfiltered, transparent render settings for paint-over reference."""
    set_eevee_engine(scene)
    r = scene.render
    r.resolution_x = resolution_x
    r.resolution_y = resolution_y
    r.resolution_percentage = 100
    r.filter_size = 0.0  # no pixel filter -> hard edges
    r.dither_intensity = 0.0
    r.film_transparent = True
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    r.image_settings.compression = 0
    scene.eevee.taa_render_samples = 1
    scene.eevee.taa_samples = 1
    scene.view_settings.view_transform = "Standard"
    try:
        scene.view_settings.look = "NONE"
    except TypeError:
        scene.view_settings.look = "None"


def build_light(scene: bpy.types.Scene) -> bpy.types.Object:
    """A sun light. Energy and angle are only set on creation so user tweaks survive a rebuild."""

    def make() -> bpy.types.Light:
        data = bpy.data.lights.new(SUN_NAME, "SUN")
        data.energy = 3.0
        return data

    sun, created = _get_or_create_object(scene, SUN_NAME, make)
    if created:
        sun.rotation_euler = (math.radians(50), math.radians(-20), math.radians(30))
    return sun


def build(
    scene: bpy.types.Scene,
    *,
    pixels_per_unit: int,
    resolution_x: int,
    resolution_y: int,
    slope_run: float,
    slope_rise: float,
    depth_scale: float,
    camera_height_fraction: float,
) -> bpy.types.Object:
    """Create or update every part of the rig; return the rig object."""
    source = get_or_create_collection(scene)
    group = build_shear_nodegroup()
    rig = build_rig_object(scene, group, source, slope_run, slope_rise, depth_scale)
    build_camera(scene, resolution_x, resolution_y, pixels_per_unit, camera_height_fraction)
    setup_render(scene, resolution_x, resolution_y)
    build_light(scene)
    return rig


def add_calibration_objects(scene: bpy.types.Scene) -> list[str]:
    """Add the calibration cubes and floor to the source collection; return the names created."""
    source = get_or_create_collection(scene)
    created = []
    for name, location, make in CALIBRATION:
        if bpy.data.objects.get(name) is not None:
            continue
        verts, faces = make()
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        ob = bpy.data.objects.new(name, mesh)
        ob.location = location
        source.objects.link(ob)
        created.append(name)
    return created


def _remove_object(name: str) -> bool:
    ob = bpy.data.objects.get(name)
    if ob is None:
        return False
    data = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)
    return True


def remove_rig(scene: bpy.types.Scene, include_source: bool = False) -> list[str]:
    """Delete the rig object, camera, sun and node group; return the names removed.

    With ``include_source`` the calibration objects and the source collection go
    too. Other objects and child collections in the source collection are
    moved to the scene collection first, so user assets are never orphaned.
    """
    removed = [name for name in (RIG_NAME, CAMERA_NAME, SUN_NAME) if _remove_object(name)]
    group = bpy.data.node_groups.get(NODEGROUP_NAME)
    if group is not None:
        bpy.data.node_groups.remove(group)
        removed.append(NODEGROUP_NAME)

    if include_source:
        removed += [name for name in (CALIB_FRONT, CALIB_BACK, CALIB_FLOOR) if _remove_object(name)]
        source = bpy.data.collections.get(SOURCE_COLLECTION)
        if source is not None:
            for ob in list(source.objects):
                if len(ob.users_collection) == 1:
                    scene.collection.objects.link(ob)
            for child in list(source.children):
                if child.name not in scene.collection.children:
                    scene.collection.children.link(child)
            bpy.data.collections.remove(source)
            removed.append(SOURCE_COLLECTION)
    return removed
