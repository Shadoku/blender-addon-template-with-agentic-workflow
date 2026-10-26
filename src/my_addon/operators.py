# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: read context, call core, write results. No maths here.

Conventions enforced by tools/lint_addon.py: class names contain ``_OT_``,
``bl_idname`` is ``category.name`` in lowercase with exactly one dot, and every
operator declares ``bl_options`` (``'UNDO'`` whenever it writes to bpy.data).
Never keep references to Blender objects between calls; store names.
"""

import bpy
from bpy.types import Operator

from . import lifecycle
from .core.spacing import evenly_spaced
from .preferences import get_prefs
from .properties import get_settings

AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def selected_objects(context: bpy.types.Context) -> list[bpy.types.Object]:
    """Selected objects in the current view layer (works in background mode too)."""
    return list(context.selected_objects)


class MY_ADDON_OT_space_evenly(Operator):
    bl_idname = "my_addon.space_evenly"
    bl_label = "Space Evenly"
    bl_description = "Move the selected objects so they sit an equal distance apart"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return len(selected_objects(context)) >= 2

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = get_settings(context)
        axis = AXIS_INDEX[settings.axis]
        objects = selected_objects(context)

        coords = [ob.location[axis] for ob in objects]
        for ob, value in zip(objects, evenly_spaced(coords, settings.gap), strict=True):
            ob.location[axis] = value

        if get_prefs(context).report_results:
            self.report({"INFO"}, f"Spaced {len(objects)} objects along {settings.axis}")
        return {"FINISHED"}


CLASSES: tuple[type, ...] = (MY_ADDON_OT_space_evenly,)


def register_keymaps() -> None:
    # keyconfigs.addon is None when Blender runs without a window manager keyconfig.
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
    kmi = km.keymap_items.new(
        MY_ADDON_OT_space_evenly.bl_idname, type="E", value="PRESS", ctrl=True, shift=True, alt=True
    )
    lifecycle.track_keymap(km, kmi)


def unregister_keymaps() -> None:
    lifecycle.remove_keymaps()
