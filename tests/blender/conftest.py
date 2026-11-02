"""Fixtures for tests that run inside headless Blender (launched by tools/check.py).

tools/blender_bootstrap.py has already enabled the add-on and exported its module
name in ADDON_MODULE (``bl_ext.dev.<id>``). Never hard-code that path in tests.
"""

import os
import sys
from types import ModuleType

import bpy
import pytest

ADDON_MODULE = os.environ.get("ADDON_MODULE")
if ADDON_MODULE is None:
    pytest.skip("tests/blender must run through tools/check.py (ADDON_MODULE unset)", allow_module_level=True)


@pytest.fixture
def addon() -> ModuleType:
    """The live add-on package, e.g. ``addon.operators.OBLIQUE_RIG_OT_build``."""
    return sys.modules[ADDON_MODULE]


@pytest.fixture(autouse=True)
def clean_scene(addon: ModuleType) -> None:
    """Reset data and add-on settings between tests WITHOUT reloading a file.

    A file reload (read_homefile / read_factory_settings) re-syncs add-ons from
    preferences and can drop a session-enabled add-on; deleting data keeps the
    registration state untouched and is much faster. The scene itself survives,
    so the add-on's PropertyGroup is reset to defaults explicitly.
    """
    _wipe_data()
    _reset_settings(addon)
    yield
    _wipe_data()


def _reset_settings(addon: ModuleType) -> None:
    settings = addon.properties.get_settings(bpy.context)
    for prop in settings.bl_rna.properties:
        if prop.identifier != "rna_type":
            settings.property_unset(prop.identifier)


def _wipe_data() -> None:
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    scene_children = bpy.context.scene.collection.children
    for coll in list(scene_children):
        scene_children.unlink(coll)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for group in list(bpy.data.node_groups):
        bpy.data.node_groups.remove(group)
    for collection in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.curves,
        bpy.data.lights,
        bpy.data.cameras,
        bpy.data.images,
    ):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)
    # Removing objects leaves stale entries in view_layer.objects until the layer is re-synced.
    bpy.context.view_layer.update()


@pytest.fixture
def make_object():
    """Create an empty at a location, linked to the active collection and selected."""

    def _make(name: str, location=(0.0, 0.0, 0.0), select: bool = True) -> bpy.types.Object:
        ob = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = location
        ob.select_set(select)
        return ob

    return _make


@pytest.fixture
def rig_vertices(addon):
    """World-space vertices of the rig's evaluated mesh (empty list when there is no geometry)."""

    def _vertices() -> list[tuple[float, float, float]]:
        rig = bpy.data.objects[addon.core.oblique.RIG_NAME]
        depsgraph = bpy.context.evaluated_depsgraph_get()
        rig_eval = rig.evaluated_get(depsgraph)
        mesh = rig_eval.to_mesh()
        try:
            return [tuple(rig_eval.matrix_world @ v.co) for v in mesh.vertices]
        finally:
            rig_eval.to_mesh_clear()

    return _vertices


@pytest.fixture
def source_box(addon):
    """A box mesh object spanning ``lo``..``hi`` (world space) linked into the source collection."""

    def _make(name: str, lo, hi) -> bpy.types.Object:
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        verts = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        ob = bpy.data.objects.new(name, mesh)
        addon.rig.get_or_create_collection(bpy.context.scene).objects.link(ob)
        return ob

    return _make


class RecordingLayout:
    """Stand-in for bpy.types.UILayout: records every call so draw() code can be exercised headless."""

    def __init__(self, calls: list | None = None) -> None:
        self.calls = calls if calls is not None else []

    def __getattr__(self, name: str):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return RecordingLayout(self.calls)

        return method


@pytest.fixture
def recording_layout() -> RecordingLayout:
    return RecordingLayout()
