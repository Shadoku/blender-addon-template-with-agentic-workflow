# SPDX-License-Identifier: GPL-3.0-or-later
"""Render operators: write guide passes (one facing, or a turnaround) to the output folder.

Both operators only write files and restore every render setting they touch,
so they declare ``REGISTER`` without ``UNDO``. The rendering itself and the
derived layers live in ``render``; the maths in ``core``.
"""

import os

import bpy
from bpy.types import Operator

from . import render
from .core.oblique import RIG_NAME
from .preferences import get_prefs
from .properties import get_settings, params_from_settings


def _poll_rig_and_camera(cls, context: bpy.types.Context) -> bool:
    if bpy.data.objects.get(RIG_NAME) is None:
        cls.poll_message_set("Build the rig first")
        return False
    if context.scene.camera is None:
        cls.poll_message_set("The scene needs a camera; build the rig first")
        return False
    return True


def _output_dir(operator: Operator, settings) -> str | None:
    """The absolute output folder, or None (after a WARNING report) if it cannot be resolved."""
    out_dir = bpy.path.abspath(settings.output_dir)
    if not out_dir or not os.path.isabs(out_dir):
        operator.report(
            {"WARNING"},
            f"Output folder '{settings.output_dir}' is relative: save the .blend file first "
            "or choose an absolute folder",
        )
        return None
    return os.path.normpath(out_dir)


def _output_name(settings) -> str:
    return settings.output_name.strip() or "guide"


class OBLIQUE_RIG_OT_render_guides(Operator):
    bl_idname = "oblique_rig.render_guides"
    bl_label = "Render Guides"
    bl_description = (
        "Render the enabled guide passes (flat, shaded, ids, silhouette, outline, grid, composite) "
        "as PNG files into the output folder"
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return _poll_rig_and_camera(cls, context)

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = get_settings(context)
        out_dir = _output_dir(self, settings)
        if out_dir is None:
            return {"CANCELLED"}
        params = params_from_settings(settings)
        paths = render.render_guides(context.scene, settings, params, out_dir, _output_name(settings))
        if get_prefs(context).report_results:
            self.report({"INFO"}, f"Wrote {len(paths)} files to {out_dir}")
        return {"FINISHED"}


class OBLIQUE_RIG_OT_render_turnaround(Operator):
    bl_idname = "oblique_rig.render_turnaround"
    bl_label = "Render Turnaround"
    bl_description = (
        "Render the guide passes for each facing (Direction Count steps around Z from Direction) "
        "and, with Make Sheet, one sprite sheet per pass"
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return _poll_rig_and_camera(cls, context)

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = get_settings(context)
        out_dir = _output_dir(self, settings)
        if out_dir is None:
            return {"CANCELLED"}
        params = params_from_settings(settings)
        paths = render.render_turnaround(
            context.scene,
            settings,
            params,
            out_dir,
            _output_name(settings),
            start=settings.direction,
            count=max(1, settings.direction_count),
            make_sheet=settings.make_sheet,
        )
        if get_prefs(context).report_results:
            self.report({"INFO"}, f"Wrote {len(paths)} files to {out_dir}")
        return {"FINISHED"}


CLASSES: tuple[type, ...] = (
    OBLIQUE_RIG_OT_render_guides,
    OBLIQUE_RIG_OT_render_turnaround,
)
