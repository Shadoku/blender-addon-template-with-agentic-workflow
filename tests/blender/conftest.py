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
    """The live add-on package, e.g. ``addon.operators.MY_ADDON_OT_space_evenly``."""
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
