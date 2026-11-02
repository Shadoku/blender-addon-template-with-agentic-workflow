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

``build`` takes a ``core.oblique.RigParams`` (see ``properties.params_from_settings``)
and never reads the PropertyGroup itself, so the render code can rebuild or
inspect the rig from the same plain values.
"""

import math
from collections.abc import Iterable
from typing import Any

import bpy
from mathutils import Vector

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
    RigParams,
)

# (name, location, builder) for the calibration objects: two unit cubes 3 units
# apart in depth and a 6x5 floor under them. Every front edge sits at y = 0, the
# rig's reference plane, so the shear (which moves +Y geometry up and right)
# never pushes anything below the floor.
CALIBRATION = (
    (CALIB_FRONT, (0.0, 0.5, 0.5), lambda: primitives.cube(1.0)),
    (CALIB_BACK, (0.0, 3.5, 0.5), lambda: primitives.cube(1.0)),
    (CALIB_FLOOR, (0.0, 2.5, 0.0), lambda: primitives.plane(6.0, 5.0)),
)

# Two flat colours so a flat render of the calibration scene shows exactly two
# materials (tests/blender/test_render.py relies on these values).
CALIB_CUBE_MATERIAL = "Calib Cube"
CALIB_FLOOR_MATERIAL = "Calib Floor"
CALIB_CUBE_COLOR = (0.85, 0.35, 0.2, 1.0)
CALIB_FLOOR_COLOR = (0.3, 0.6, 0.3, 1.0)
CALIB_MATERIALS = {
    CALIB_FRONT: (CALIB_CUBE_MATERIAL, CALIB_CUBE_COLOR),
    CALIB_BACK: (CALIB_CUBE_MATERIAL, CALIB_CUBE_COLOR),
    CALIB_FLOOR: (CALIB_FLOOR_MATERIAL, CALIB_FLOOR_COLOR),
}

# Object types whose bounding box describes real geometry (for the interpenetration check).
GEOMETRY_TYPES = frozenset({"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME"})

RIG_OWNED = frozenset({RIG_NAME, CAMERA_NAME, SUN_NAME})
VIEW_MODES = ("SOURCE", "SHEARED")


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
    """(Re)build the Geometry Nodes group that pulls in a collection, turns, seats and shears it.

    Collection Info -> Realize Instances -> Transform (rotation Z = Direction)
    -> Transform (translation = Auto Seat ? seat offset : 0) -> Transform
    (shear matrix from Combine Matrix fed by normalize(run, rise, 0) * depth)
    -> Realize Instances -> Group Output.

    The seat offset is ``(-(min.x + max.x) / 2, -min.y, 0)`` of the turned
    geometry's bounding box: front edge on y = 0, centred on x = 0. The source
    is realized first because Bounding Box ignores instances. The final
    Realize keeps the rig's evaluated mesh real geometry for tests and exporters.
    Input order: Geometry, Source Collection, Slope Run, Slope Rise, Depth Scale,
    Direction, Auto Seat.
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
    s_dir = iface.new_socket("Direction", in_out="INPUT", socket_type="NodeSocketFloat")
    s_seat = iface.new_socket("Auto Seat", in_out="INPUT", socket_type="NodeSocketBool")
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    s_run.default_value = 2.0
    s_rise.default_value = 1.0
    s_run.min_value = s_rise.min_value = 0.0
    s_depth.default_value = 0.6
    s_depth.min_value = 0.0
    s_depth.max_value = 2.0
    s_dir.subtype = "ANGLE"
    s_dir.default_value = 0.0
    s_seat.default_value = True

    nodes, links = ng.nodes, ng.links

    def add(bl_idname: str, x: float, y: float, node_name: str | None = None) -> bpy.types.Node:
        node = nodes.new(bl_idname)
        node.location = (x, y)
        if node_name is not None:
            node.name = node.label = node_name
        return node

    n_in = add("NodeGroupInput", -1400, 0)
    n_out = add("NodeGroupOutput", 1300, 0)

    # Source: the collection as real geometry.
    n_coll = add("GeometryNodeCollectionInfo", -1150, 200)
    n_coll.transform_space = "RELATIVE"
    n_coll.inputs["Separate Children"].default_value = False
    n_coll.inputs["Reset Children"].default_value = False
    n_src_realize = add("GeometryNodeRealizeInstances", -950, 200, "Realize Source")

    # Direction: rotate about Z.
    n_euler = add("ShaderNodeCombineXYZ", -1150, -50, "Direction Euler")
    n_euler.inputs["X"].default_value = 0.0
    n_euler.inputs["Y"].default_value = 0.0
    n_rotation = add("FunctionNodeEulerToRotation", -950, -50)
    n_turn = add("GeometryNodeTransform", -750, 200, "Turn")

    # Auto Seat: translation from the turned bounding box, or zero.
    n_bbox = add("GeometryNodeBoundBox", -550, -50)
    n_sum = add("ShaderNodeVectorMath", -350, -50, "Min + Max")
    n_sum.operation = "ADD"
    n_centre_x = add("ShaderNodeVectorMath", -150, -50, "Centre X")
    n_centre_x.operation = "MULTIPLY"
    n_centre_x.inputs[1].default_value = (-0.5, 0.0, 0.0)
    n_front_y = add("ShaderNodeVectorMath", -150, -250, "Front Y")
    n_front_y.operation = "MULTIPLY"
    n_front_y.inputs[1].default_value = (0.0, -1.0, 0.0)
    n_seat_offset = add("ShaderNodeVectorMath", 50, -100, "Seat Offset")
    n_seat_offset.operation = "ADD"
    n_switch = add("GeometryNodeSwitch", 250, -100, "Auto Seat")
    n_switch.input_type = "VECTOR"
    n_switch.inputs["False"].default_value = (0.0, 0.0, 0.0)
    n_seat = add("GeometryNodeTransform", 450, 200, "Seat")

    # Shear matrix.
    n_dir = add("ShaderNodeCombineXYZ", -150, -450)
    n_dir.inputs["Z"].default_value = 0.0
    n_norm = add("ShaderNodeVectorMath", 50, -450)
    n_norm.operation = "NORMALIZE"
    n_scale = add("ShaderNodeVectorMath", 250, -450)
    n_scale.operation = "SCALE"
    n_sep = add("ShaderNodeSeparateXYZ", 450, -450)
    n_mat = add("FunctionNodeCombineMatrix", 650, -300)
    identity = oblique.shear_matrix_columns(0.0, 0.0)
    for index, value in enumerate(identity):
        n_mat.inputs[index].default_value = value

    n_xform = add("GeometryNodeTransform", 850, 200, "Shear")
    set_transform_mode_matrix(n_xform)
    n_realize = add("GeometryNodeRealizeInstances", 1080, 200)

    links.new(n_in.outputs["Source Collection"], n_coll.inputs["Collection"])
    links.new(n_coll.outputs["Instances"], n_src_realize.inputs["Geometry"])

    links.new(n_in.outputs["Direction"], n_euler.inputs["Z"])
    links.new(n_euler.outputs[0], n_rotation.inputs[0])
    links.new(n_src_realize.outputs["Geometry"], n_turn.inputs["Geometry"])
    links.new(n_rotation.outputs[0], n_turn.inputs["Rotation"])

    links.new(n_turn.outputs["Geometry"], n_bbox.inputs["Geometry"])
    links.new(n_bbox.outputs["Min"], n_sum.inputs[0])
    links.new(n_bbox.outputs["Max"], n_sum.inputs[1])
    links.new(n_sum.outputs[0], n_centre_x.inputs[0])
    links.new(n_bbox.outputs["Min"], n_front_y.inputs[0])
    links.new(n_centre_x.outputs[0], n_seat_offset.inputs[0])
    links.new(n_front_y.outputs[0], n_seat_offset.inputs[1])
    links.new(n_in.outputs["Auto Seat"], n_switch.inputs["Switch"])
    links.new(n_seat_offset.outputs[0], n_switch.inputs["True"])
    links.new(n_turn.outputs["Geometry"], n_seat.inputs["Geometry"])
    links.new(n_switch.outputs[0], n_seat.inputs["Translation"])

    links.new(n_in.outputs["Slope Run"], n_dir.inputs["X"])
    links.new(n_in.outputs["Slope Rise"], n_dir.inputs["Y"])
    links.new(n_dir.outputs[0], n_norm.inputs[0])
    links.new(n_norm.outputs[0], n_scale.inputs[0])
    links.new(n_in.outputs["Depth Scale"], n_scale.inputs["Scale"])
    links.new(n_scale.outputs[0], n_sep.inputs[0])
    # Column-major: index 4 is "Column 2 Row 1" (X' += a*Y), index 6 "Column 2 Row 3" (Z' += b*Y).
    links.new(n_sep.outputs["X"], n_mat.inputs[1 * 4 + 0])
    links.new(n_sep.outputs["Y"], n_mat.inputs[1 * 4 + 2])

    links.new(n_seat.outputs["Geometry"], n_xform.inputs["Geometry"])
    links.new(n_mat.outputs["Matrix"], n_xform.inputs["Transform"])
    links.new(n_xform.outputs["Geometry"], n_realize.inputs["Geometry"])
    links.new(n_realize.outputs["Geometry"], n_out.inputs["Geometry"])
    return ng


def build_rig_object(
    scene: bpy.types.Scene,
    group: bpy.types.NodeTree,
    source: bpy.types.Collection,
    params: RigParams,
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

    run, rise, depth = params.modifier_inputs()
    set_modifier_input(mod, "Source Collection", source)
    set_modifier_input(mod, "Slope Run", run)
    set_modifier_input(mod, "Slope Rise", rise)
    set_modifier_input(mod, "Depth Scale", depth)
    set_modifier_input(mod, "Direction", params.direction)
    set_modifier_input(mod, "Auto Seat", params.auto_seat)
    rig.update_tag()
    return rig


def build_camera(
    scene: bpy.types.Scene,
    resolution_x: int,
    resolution_y: int,
    pixels_per_unit: int,
    location: tuple[float, float, float],
) -> bpy.types.Object:
    """Orthographic camera at ``location`` looking straight down +Y, one unit = ``pixels_per_unit`` px."""
    cam, _ = _get_or_create_object(scene, CAMERA_NAME, lambda: bpy.data.cameras.new(CAMERA_NAME))
    data = cam.data
    data.type = "ORTHO"
    data.ortho_scale = oblique.ortho_scale(resolution_x, resolution_y, pixels_per_unit)
    data.shift_x = data.shift_y = 0.0
    data.clip_start = 0.1
    data.clip_end = 1000.0
    # Rotated 90 degrees about X: screen x = world X, screen y = world Z.
    cam.location = location
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
    r.pixel_aspect_x = r.pixel_aspect_y = 1.0
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


def build(scene: bpy.types.Scene, params: RigParams) -> bpy.types.Object:
    """Create or update every part of the rig from ``params``; return the rig object.

    In pixel-exact mode the render resolution is rounded up to even numbers
    (``params.effective_resolution()``) and the camera snapped to the pixel
    grid (``params.camera()``); the settings themselves are left as they are.
    """
    source = get_or_create_collection(scene)
    group = build_shear_nodegroup()
    rig = build_rig_object(scene, group, source, params)
    resolution_x, resolution_y = params.effective_resolution()
    build_camera(scene, resolution_x, resolution_y, params.pixels_per_unit, params.camera())
    setup_render(scene, resolution_x, resolution_y)
    build_light(scene)
    apply_view_mode(scene, params.view_mode)
    return rig


# --------------------------------------------------------------------------- measuring


def sheared_bounds(
    scene: bpy.types.Scene, rig_object: bpy.types.Object
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """World-space (min, max) of the rig's evaluated (turned, seated, sheared) mesh.

    Evaluates the active depsgraph (``scene`` must be the context scene). Returns
    ``None`` when the rig has no geometry, e.g. an empty source collection.
    """
    if scene != bpy.context.scene:
        raise ValueError(f"sheared_bounds needs the context scene, got {scene.name!r}")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    rig_eval = rig_object.evaluated_get(depsgraph)
    mesh = rig_eval.to_mesh()
    try:
        matrix = rig_eval.matrix_world
        points = [tuple(matrix @ v.co) for v in mesh.vertices]
    finally:
        rig_eval.to_mesh_clear()
    if not points:
        return None
    return oblique.bounds(points)


def source_boxes(
    scene: bpy.types.Scene,
) -> list[tuple[str, tuple[float, float, float], tuple[float, float, float]]]:
    """Per source object: ``(name, (xmin, ymin, zmin), (xmax, ymax, zmax))`` in world space.

    The box is the axis-aligned bound of the evaluated object's bounding-box
    corners after its world matrix (modifiers and parents included), before
    the rig turns, seats or shears anything: interpenetration does not depend
    on the facing. Objects without geometry (empties, cameras, lights) are
    skipped. Sorted by name so the warnings read the same on every run. Feed
    the result to ``core.overlap.overlapping_pairs``. ``scene`` must be the
    context scene (its depsgraph is evaluated).
    """
    if scene != bpy.context.scene:
        raise ValueError(f"source_boxes needs the context scene, got {scene.name!r}")
    source = bpy.data.collections.get(SOURCE_COLLECTION)
    if source is None:
        return []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    boxes = []
    for ob in sorted(source.all_objects, key=lambda ob: ob.name):
        if ob.type not in GEOMETRY_TYPES:
            continue
        ob_eval = ob.evaluated_get(depsgraph)
        matrix = ob_eval.matrix_world
        lo, hi = oblique.bounds([tuple(matrix @ Vector(c)) for c in ob_eval.bound_box])
        boxes.append((ob.name, lo, hi))
    return boxes


# --------------------------------------------------------------------------- viewport toggle


def _find_layer_collection(
    layer_collection: bpy.types.LayerCollection, name: str
) -> bpy.types.LayerCollection | None:
    if layer_collection.collection.name == name:
        return layer_collection
    for child in layer_collection.children:
        found = _find_layer_collection(child, name)
        if found is not None:
            return found
    return None


def apply_view_mode(scene: bpy.types.Scene, view_mode: str) -> None:
    """Show either the source objects or the sheared rig in every view layer, never both.

    Uses the per-view-layer eye toggles (``LayerCollection.hide_viewport`` and
    ``Object.hide_set``) rather than the global "disable in viewports" flags:
    eye-hidden objects stay in the depsgraph, so Collection Info keeps feeding
    the rig while the originals are out of sight. Rendering is unaffected; the
    source collection always has ``hide_render`` set.
    """
    if view_mode not in VIEW_MODES:
        raise ValueError(f"view_mode must be one of {VIEW_MODES}, got {view_mode!r}")
    show_sheared = view_mode == "SHEARED"
    source = bpy.data.collections.get(SOURCE_COLLECTION)
    rig = bpy.data.objects.get(RIG_NAME)
    for view_layer in scene.view_layers:
        if source is not None:
            layer_coll = _find_layer_collection(view_layer.layer_collection, source.name)
            if layer_coll is not None:
                layer_coll.hide_viewport = show_sheared
        if rig is not None and rig.name in view_layer.objects:
            rig.hide_set(not show_sheared, view_layer=view_layer)


# --------------------------------------------------------------------------- adding assets


def eligible_for_rig(objects: Iterable[bpy.types.Object]) -> list[bpy.types.Object]:
    """The objects that may be added to the rig: anything but the rig's own objects."""
    return [ob for ob in objects if ob.name not in RIG_OWNED]


def _move_to_collection(ob: bpy.types.Object, target: bpy.types.Collection) -> None:
    for coll in list(ob.users_collection):
        if coll != target:
            coll.objects.unlink(ob)
    if ob.name not in target.objects:
        target.objects.link(ob)


def add_objects_to_rig(
    scene: bpy.types.Scene,
    objects: list[bpy.types.Object],
    depsgraph: bpy.types.Depsgraph,
    ground_by_bottom: bool = False,
) -> list[str]:
    """Move ``objects`` into the source collection and seat each at the reference plane.

    Each object's evaluated world bounding box decides the move: its front edge
    goes to y = 0 and its origin (or lowest point, with ``ground_by_bottom``) to
    z = 0; x is kept. Objects whose parent is also being added are only
    relinked, since the parent carries them. Returns the names processed.
    """
    source = get_or_create_collection(scene)
    objects = eligible_for_rig(objects)
    moving = set(ob.name for ob in objects)
    offsets: dict[str, Vector] = {}
    for ob in objects:
        if ob.parent is not None and ob.parent.name in moving:
            continue
        corners = [tuple(ob.matrix_world @ Vector(c)) for c in ob.evaluated_get(depsgraph).bound_box]
        lo, _ = oblique.bounds(corners)
        offsets[ob.name] = Vector(
            oblique.placement_offset(lo, ob.matrix_world.translation.z, ground_by_bottom)
        )

    for ob in objects:
        offset = offsets.get(ob.name)
        if offset is not None:
            matrix = ob.matrix_world.copy()
            matrix.translation += offset
            ob.matrix_world = matrix
        _move_to_collection(ob, source)
    return [ob.name for ob in objects]


def calibration_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    """The named calibration material; created with ``color`` once, then reused as the user left it."""
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = color
    return mat


def add_calibration_objects(scene: bpy.types.Scene) -> list[str]:
    """Add the calibration cubes and floor to the source collection; return the names created.

    The cubes share the material ``CALIB_CUBE_MATERIAL`` and the floor has
    ``CALIB_FLOOR_MATERIAL``, so a flat render shows exactly two colours.
    """
    source = get_or_create_collection(scene)
    created = []
    for name, location, make in CALIBRATION:
        if bpy.data.objects.get(name) is not None:
            continue
        verts, faces = make()
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        mesh.materials.append(calibration_material(*CALIB_MATERIALS[name]))
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
        for mat_name in (CALIB_CUBE_MATERIAL, CALIB_FLOOR_MATERIAL):
            mat = bpy.data.materials.get(mat_name)
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)
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
