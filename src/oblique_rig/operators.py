# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: read settings, call ``rig``, report. No maths here.

Conventions enforced by tools/lint_addon.py: class names contain ``_OT_``,
``bl_idname`` is ``category.name`` in lowercase with exactly one dot, and every
operator declares ``bl_options`` (``'UNDO'`` whenever it writes to bpy.data).
Never keep references to Blender objects between calls; store names.
"""

import bpy
from bpy.props import BoolProperty
from bpy.types import Operator

from . import rig
from .core import oblique
from .preferences import get_prefs
from .properties import get_settings


class OBLIQUE_RIG_OT_build(Operator):
    bl_idname = "oblique_rig.build"
    bl_label = "Build Rig"
    bl_description = (
        "Create or update the oblique rig: source collection, shear node group, rig object, "
        "orthographic camera, sun and render settings"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        s = get_settings(context)
        try:
            oblique.shear_coefficients(s.slope_run, s.slope_rise, s.depth_scale)
        except ValueError as exc:
            cls.poll_message_set(str(exc))
            return False
        return True

    def execute(self, context: bpy.types.Context) -> set[str]:
        s = get_settings(context)
        try:
            dx, dy = oblique.screen_offset_per_depth_unit(
                s.slope_run, s.slope_rise, s.depth_scale, s.pixels_per_unit
            )
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}

        rig.build(
            context.scene,
            pixels_per_unit=s.pixels_per_unit,
            resolution_x=s.resolution_x,
            resolution_y=s.resolution_y,
            slope_run=s.slope_run,
            slope_rise=s.slope_rise,
            depth_scale=s.depth_scale,
            camera_height_fraction=s.camera_height_fraction,
        )
        if get_prefs(context).report_results:
            self.report(
                {"INFO"},
                f"Oblique rig ready: put assets in '{oblique.SOURCE_COLLECTION}'; "
                f"one unit of depth moves {dx:.2f} px right, {dy:.2f} px up",
            )
        return {"FINISHED"}


class OBLIQUE_RIG_OT_add_calibration(Operator):
    bl_idname = "oblique_rig.add_calibration"
    bl_label = "Add Calibration Objects"
    bl_description = "Add two unit cubes 3 units apart in depth and a floor to the source collection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        created = rig.add_calibration_objects(context.scene)
        if get_prefs(context).report_results:
            message = f"Added {', '.join(created)}" if created else "Calibration objects already exist"
            self.report({"INFO"}, message)
        return {"FINISHED"}


class OBLIQUE_RIG_OT_remove(Operator):
    bl_idname = "oblique_rig.remove"
    bl_label = "Remove Rig"
    bl_description = (
        "Delete the rig object, camera, sun and node group (optionally the source collection too)"
    )
    bl_options = {"REGISTER", "UNDO"}

    include_source: BoolProperty(
        name="Include Source",
        description=(
            "Also delete the source collection and the calibration objects; "
            "other objects in it are moved to the scene collection"
        ),
        default=False,
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        removed = rig.remove_rig(context.scene, include_source=self.include_source)
        if get_prefs(context).report_results:
            self.report({"INFO"}, f"Removed {', '.join(removed)}" if removed else "Nothing to remove")
        return {"FINISHED"}


CLASSES: tuple[type, ...] = (
    OBLIQUE_RIG_OT_build,
    OBLIQUE_RIG_OT_add_calibration,
    OBLIQUE_RIG_OT_remove,
)
