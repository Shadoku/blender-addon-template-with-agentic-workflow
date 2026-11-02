# SPDX-License-Identifier: GPL-3.0-or-later
"""Panels and menus. ``draw`` only reads state and emits layout calls.

Blender never calls ``draw`` in background mode, so keep these methods thin and
free of logic; tests/blender/test_ui.py calls them with a recording layout to
at least prove they run without raising.
"""

import bpy
from bpy.types import Panel

from .core.oblique import RIG_NAME, SOURCE_COLLECTION
from .operators import (
    OBLIQUE_RIG_OT_add_calibration,
    OBLIQUE_RIG_OT_add_selected,
    OBLIQUE_RIG_OT_build,
    OBLIQUE_RIG_OT_remove,
)
from .properties import get_settings


class OBLIQUE_RIG_PT_sidebar(Panel):
    bl_idname = "OBLIQUE_RIG_PT_sidebar"
    bl_label = "Oblique Rig"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Oblique Rig"

    def draw(self, context: bpy.types.Context) -> None:
        settings = get_settings(context)
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(align=True)
        col.prop(settings, "pixels_per_unit")
        row = col.row(align=True)
        row.prop(settings, "resolution_x", text="Resolution")
        row.prop(settings, "resolution_y", text="")

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(settings, "slope_run", text="Slope")
        row.prop(settings, "slope_rise", text="")
        col.prop(settings, "depth_scale")
        col.prop(settings, "camera_height_fraction")

        col = layout.column(align=True)
        col.operator(OBLIQUE_RIG_OT_build.bl_idname, icon="MOD_LATTICE")
        col.operator(OBLIQUE_RIG_OT_add_selected.bl_idname, icon="IMPORT")
        col.operator(OBLIQUE_RIG_OT_add_calibration.bl_idname, icon="MESH_CUBE")
        col.operator(OBLIQUE_RIG_OT_remove.bl_idname, icon="TRASH")

        row = layout.row(align=True)
        row.use_property_split = False
        row.prop(settings, "view_mode", expand=True)

        if bpy.data.objects.get(RIG_NAME) is not None:
            layout.label(text=f"Rig ready; assets go in '{SOURCE_COLLECTION}'", icon="CHECKMARK")
        else:
            layout.label(text="No rig in this file", icon="INFO")


CLASSES: tuple[type, ...] = (OBLIQUE_RIG_PT_sidebar,)
