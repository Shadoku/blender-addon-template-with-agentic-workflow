# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-level rig settings as a PropertyGroup.

Define properties with annotations (``name: Type()``), never ``=``. One
PointerProperty on ``bpy.types.Scene`` is attached after the group class is
registered and deleted in unregister. Read values as attributes
(``scene.oblique_rig.depth_scale``); dict access to bpy.props values stopped
working in Blender 5.0.
"""

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty
from bpy.types import PropertyGroup

from . import rig

VIEW_MODE_ITEMS = (
    ("SOURCE", "Source", "Show the original objects in the source collection; hide the sheared rig"),
    ("SHEARED", "Sheared", "Show the sheared rig output; hide the source objects"),
)

# Attribute name on bpy.types.Scene. Keep it equal to the add-on id so it is unique.
SCENE_ATTR = "oblique_rig"


def _on_view_mode_update(self: "OBLIQUE_RIG_Settings", context: bpy.types.Context) -> None:
    scene = self.id_data if isinstance(self.id_data, bpy.types.Scene) else context.scene
    rig.apply_view_mode(scene, self.view_mode)


class OBLIQUE_RIG_Settings(PropertyGroup):
    pixels_per_unit: IntProperty(
        name="Pixels per Unit",
        description="Render pixels covered by one Blender unit",
        default=16,
        min=1,
        soft_max=256,
    )
    resolution_x: IntProperty(
        name="Resolution X",
        description="Render width in pixels",
        default=320,
        min=1,
        soft_max=4096,
        subtype="PIXEL",
    )
    resolution_y: IntProperty(
        name="Resolution Y",
        description="Render height in pixels",
        default=200,
        min=1,
        soft_max=4096,
        subtype="PIXEL",
    )
    slope_run: FloatProperty(
        name="Slope Run",
        description="Horizontal part of the on-screen depth direction (2 with rise 1 is pixel-art 2:1)",
        default=2.0,
        min=0.0,
        soft_max=8.0,
    )
    slope_rise: FloatProperty(
        name="Slope Rise",
        description="Vertical part of the on-screen depth direction",
        default=1.0,
        min=0.0,
        soft_max=8.0,
    )
    depth_scale: FloatProperty(
        name="Depth Scale",
        description="Length of one unit of depth on screen: 1.0 is cavalier (true length), about 0.5 is cabinet",
        default=0.6,
        min=0.0,
        soft_max=2.0,
    )
    camera_height_fraction: FloatProperty(
        name="Camera Height",
        description="Fraction of the frame height the camera sits above z = 0",
        default=0.35,
        soft_min=0.0,
        soft_max=1.0,
        subtype="FACTOR",
    )
    view_mode: EnumProperty(
        name="View",
        description="Which side of the rig is visible in the viewport",
        items=VIEW_MODE_ITEMS,
        default="SHEARED",
        update=_on_view_mode_update,
    )


CLASSES: tuple[type, ...] = (OBLIQUE_RIG_Settings,)


def get_settings(context: bpy.types.Context) -> OBLIQUE_RIG_Settings:
    return getattr(context.scene, SCENE_ATTR)


def register_scene_properties() -> None:
    setattr(bpy.types.Scene, SCENE_ATTR, PointerProperty(type=OBLIQUE_RIG_Settings))


def unregister_scene_properties() -> None:
    if hasattr(bpy.types.Scene, SCENE_ATTR):
        delattr(bpy.types.Scene, SCENE_ATTR)
