# SPDX-License-Identifier: GPL-3.0-or-later
"""Panels and menus. ``draw`` only reads state and emits layout calls.

Blender never calls ``draw`` in background mode, so keep these methods thin and
free of logic; tests/blender/test_ui.py calls them with a recording layout to
prove they run and that every setting and operator is reachable.

The sidebar is one root panel (status and the Source/Sheared toggle) with
sub-panels in workflow order: Rig, Projection, Frame, Direction, Output. The
render operators live in ``operators_render`` (another module); they are
referenced here by ``bl_idname`` string only.
"""

import bpy
from bpy.types import Panel

from .core.oblique import RIG_NAME, SOURCE_COLLECTION
from .operators import (
    OBLIQUE_RIG_OT_add_calibration,
    OBLIQUE_RIG_OT_add_selected,
    OBLIQUE_RIG_OT_apply_resolution_preset,
    OBLIQUE_RIG_OT_apply_slope_preset,
    OBLIQUE_RIG_OT_build,
    OBLIQUE_RIG_OT_fit_to_content,
    OBLIQUE_RIG_OT_remove,
)
from .properties import get_settings, params_from_settings

RENDER_GUIDES_IDNAME = "oblique_rig.render_guides"
RENDER_TURNAROUND_IDNAME = "oblique_rig.render_turnaround"


def _split(layout: bpy.types.UILayout) -> bpy.types.UILayout:
    layout.use_property_split = True
    layout.use_property_decorate = False
    return layout


class OBLIQUE_RIG_PT_sidebar(Panel):
    bl_idname = "OBLIQUE_RIG_PT_sidebar"
    bl_label = "Oblique Rig"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Oblique Rig"

    def draw(self, context: bpy.types.Context) -> None:
        settings = get_settings(context)
        layout = self.layout
        if bpy.data.objects.get(RIG_NAME) is not None:
            layout.label(text=f"Rig ready; assets go in '{SOURCE_COLLECTION}'", icon="CHECKMARK")
        else:
            layout.label(text="No rig in this file", icon="INFO")
        row = layout.row(align=True)
        row.prop(settings, "view_mode", expand=True)


class _SubPanel:
    """Shared placement for the sub-panels (a plain mixin; Blender only sees the Panel subclasses)."""

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Oblique Rig"
    bl_parent_id = "OBLIQUE_RIG_PT_sidebar"


class OBLIQUE_RIG_PT_rig(_SubPanel, Panel):
    bl_idname = "OBLIQUE_RIG_PT_rig"
    bl_label = "Rig"
    bl_order = 0

    def draw(self, context: bpy.types.Context) -> None:
        col = self.layout.column(align=True)
        col.operator(OBLIQUE_RIG_OT_build.bl_idname, icon="MOD_LATTICE")
        col.operator(OBLIQUE_RIG_OT_add_selected.bl_idname, icon="IMPORT")
        col.operator(OBLIQUE_RIG_OT_add_calibration.bl_idname, icon="MESH_CUBE")
        col.operator(OBLIQUE_RIG_OT_remove.bl_idname, icon="TRASH")


class OBLIQUE_RIG_PT_projection(_SubPanel, Panel):
    bl_idname = "OBLIQUE_RIG_PT_projection"
    bl_label = "Projection"
    bl_order = 1

    def draw(self, context: bpy.types.Context) -> None:
        settings = get_settings(context)
        layout = _split(self.layout)
        layout.prop(settings, "pixel_exact")
        col = layout.column(align=True)
        if settings.pixel_exact:
            col.prop(settings, "depth_px_right", text="Depth Right")
            col.prop(settings, "depth_px_up", text="Up")
        else:
            row = col.row(align=True)
            row.prop(settings, "slope_run", text="Slope")
            row.prop(settings, "slope_rise", text="")
            col.prop(settings, "depth_scale")
        layout.operator_menu_enum(OBLIQUE_RIG_OT_apply_slope_preset.bl_idname, "preset", text="Slope Presets")

        params = params_from_settings(settings)
        try:
            a, b = params.shear()
        except ValueError as exc:
            layout.label(text=str(exc), icon="ERROR")
        else:
            ppu = params.pixels_per_unit
            layout.label(text=f"1 unit depth = {a * ppu:g} px right, {b * ppu:g} px up")


class OBLIQUE_RIG_PT_frame(_SubPanel, Panel):
    bl_idname = "OBLIQUE_RIG_PT_frame"
    bl_label = "Frame"
    bl_order = 2

    def draw(self, context: bpy.types.Context) -> None:
        settings = get_settings(context)
        layout = _split(self.layout)
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(settings, "resolution_x", text="Resolution")
        row.prop(settings, "resolution_y", text="")
        col.operator_menu_enum(
            OBLIQUE_RIG_OT_apply_resolution_preset.bl_idname, "preset", text="Resolution Presets"
        )
        col = layout.column(align=True)
        col.prop(settings, "pixels_per_unit")
        col.prop(settings, "camera_height_fraction")
        col.prop(settings, "camera_offset_x")
        layout.operator(OBLIQUE_RIG_OT_fit_to_content.bl_idname, icon="FULLSCREEN_ENTER")
        if settings.last_footprint:
            layout.label(text=f"Content: {settings.last_footprint}", icon="SELECT_SET")
        if settings.last_warnings:
            layout.label(text=f"Depth order unclear: {settings.last_warnings}", icon="ERROR")


class OBLIQUE_RIG_PT_direction(_SubPanel, Panel):
    bl_idname = "OBLIQUE_RIG_PT_direction"
    bl_label = "Direction"
    bl_order = 3

    def draw(self, context: bpy.types.Context) -> None:
        settings = get_settings(context)
        layout = _split(self.layout)
        col = layout.column(align=True)
        col.prop(settings, "direction")
        col.prop(settings, "auto_seat")
        col.prop(settings, "direction_count")


class OBLIQUE_RIG_PT_output(_SubPanel, Panel):
    bl_idname = "OBLIQUE_RIG_PT_output"
    bl_label = "Output"
    bl_order = 4

    def draw(self, context: bpy.types.Context) -> None:
        settings = get_settings(context)
        layout = _split(self.layout)
        col = layout.column(align=True)
        col.prop(settings, "output_dir")
        col.prop(settings, "output_name")

        col = layout.column(heading="Passes", align=True)
        col.prop(settings, "pass_flat")
        col.prop(settings, "pass_shaded")
        col.prop(settings, "pass_ids")
        col.prop(settings, "pass_silhouette")
        col.prop(settings, "pass_composite")
        col.prop(settings, "make_sheet")

        layout.prop(settings, "outline_enabled")
        col = layout.column(align=True)
        col.active = settings.outline_enabled
        col.prop(settings, "outline_outer_px")
        col.prop(settings, "outline_inner_px")
        col.prop(settings, "outline_position")
        col.prop(settings, "inner_lines")
        if settings.inner_lines == "EDGES":
            col.prop(settings, "crease_angle")
            col.prop(settings, "edge_marked_sharp")
        col.prop(settings, "outline_corners")
        col.prop(settings, "outline_color")

        layout.prop(settings, "grid_enabled")
        col = layout.column(align=True)
        col.active = settings.grid_enabled
        col.prop(settings, "grid_step")
        col.prop(settings, "grid_extent")
        col.prop(settings, "grid_color")

        col = layout.column(align=True)
        col.operator(RENDER_GUIDES_IDNAME, icon="RENDER_STILL")
        col.operator(RENDER_TURNAROUND_IDNAME, icon="RENDER_ANIMATION")


CLASSES: tuple[type, ...] = (
    OBLIQUE_RIG_PT_sidebar,
    OBLIQUE_RIG_PT_rig,
    OBLIQUE_RIG_PT_projection,
    OBLIQUE_RIG_PT_frame,
    OBLIQUE_RIG_PT_direction,
    OBLIQUE_RIG_PT_output,
)
