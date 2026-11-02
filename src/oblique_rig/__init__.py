# SPDX-License-Identifier: GPL-3.0-or-later
"""Oblique Rig: entry point.

This module only wires things together. Rules and maths live in ``core/``
(no bpy, unit-tested in milliseconds); Blender-facing code lives in ``rig`` (the
builders) and the thin ``operators``, ``properties``, ``ui``, ``preferences``
and ``handlers`` modules.

Registration order matters: PropertyGroups before the PointerProperty that uses
them, operators before the panels that reference them. ``operators_render`` holds the
render operators (Render Guides, Render Turnaround). ``unregister`` runs the
exact reverse so a disable -> enable round trip leaves nothing behind
(tests/blender/test_register.py checks that).
"""

import bpy

from . import handlers, lifecycle, operators, operators_render, preferences, properties, ui

# Every Blender class the add-on registers, in dependency order.
CLASSES: tuple[type, ...] = (
    *preferences.CLASSES,
    *properties.CLASSES,
    *operators.CLASSES,
    *operators_render.CLASSES,
    *ui.CLASSES,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    properties.register_scene_properties()
    handlers.register()


def unregister() -> None:
    handlers.unregister()
    lifecycle.cleanup()
    properties.unregister_scene_properties()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
