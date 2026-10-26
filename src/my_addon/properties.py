# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-level settings as a PropertyGroup.

Define properties with annotations (``name: Type()``), never ``=``. Attach one
PointerProperty to ``bpy.types.Scene`` after the group class is registered and
delete it in unregister. Read values as attributes (``scene.my_addon.gap``);
dict access to bpy.props values stopped working in Blender 5.0.
"""

import bpy
from bpy.props import EnumProperty, FloatProperty, PointerProperty
from bpy.types import PropertyGroup

AXIS_ITEMS = (
    ("X", "X", "Distribute along the X axis"),
    ("Y", "Y", "Distribute along the Y axis"),
    ("Z", "Z", "Distribute along the Z axis"),
)

# Attribute name on bpy.types.Scene. Keep it equal to the add-on id so it is unique.
SCENE_ATTR = "my_addon"


class MY_ADDON_Settings(PropertyGroup):
    axis: EnumProperty(
        name="Axis",
        description="Axis along which selected objects are spaced",
        items=AXIS_ITEMS,
        default="X",
    )
    gap: FloatProperty(
        name="Gap",
        description="Distance between consecutive objects",
        default=2.0,
        min=0.0,
        soft_max=100.0,
        unit="LENGTH",
    )


CLASSES: tuple[type, ...] = (MY_ADDON_Settings,)


def get_settings(context: bpy.types.Context) -> MY_ADDON_Settings:
    return getattr(context.scene, SCENE_ATTR)


def register_scene_properties() -> None:
    setattr(bpy.types.Scene, SCENE_ATTR, PointerProperty(type=MY_ADDON_Settings))


def unregister_scene_properties() -> None:
    if hasattr(bpy.types.Scene, SCENE_ATTR):
        delattr(bpy.types.Scene, SCENE_ATTR)
