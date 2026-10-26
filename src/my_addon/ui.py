# SPDX-License-Identifier: GPL-3.0-or-later
"""Panels and menus. ``draw`` only reads state and emits layout calls.

Blender never calls ``draw`` in background mode, so keep these methods thin and
free of logic; tests/blender/test_ui.py calls them with a recording layout to
at least prove they run without raising.
"""

import bpy
from bpy.types import Panel

from .operators import MY_ADDON_OT_space_evenly
from .properties import get_settings


class MY_ADDON_PT_sidebar(Panel):
    bl_idname = "MY_ADDON_PT_sidebar"
    bl_label = "My Addon"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "My Addon"

    def draw(self, context: bpy.types.Context) -> None:
        settings = get_settings(context)
        layout = self.layout
        col = layout.column(align=True)
        col.prop(settings, "axis", expand=True)
        col.prop(settings, "gap")
        layout.operator(MY_ADDON_OT_space_evenly.bl_idname, icon="ARROW_LEFTRIGHT")


CLASSES: tuple[type, ...] = (MY_ADDON_PT_sidebar,)
