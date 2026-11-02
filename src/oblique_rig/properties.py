# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-level rig settings as a PropertyGroup.

Define properties with annotations (``name: Type()``), never ``=``. One
PointerProperty on ``bpy.types.Scene`` is attached after the group class is
registered and deleted in unregister. Read values as attributes
(``scene.oblique_rig.depth_scale``); dict access to bpy.props values stopped
working in Blender 5.0.

``rig.py`` and ``render.py`` never read this group directly: operators convert
it with :func:`params_from_settings` into the plain ``core.oblique.RigParams``.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from . import rig
from .core.oblique import RigParams

VIEW_MODE_ITEMS = (
    ("SOURCE", "Source", "Show the original objects in the source collection; hide the sheared rig"),
    ("SHEARED", "Sheared", "Show the sheared rig output; hide the source objects"),
)

OUTLINE_POSITION_ITEMS = (
    ("OUTSIDE", "Outside", "The outline grows the shape outward"),
    ("INSIDE", "Inside", "The outline eats into the shape"),
)

INNER_LINES_ITEMS = (
    ("NONE", "None", "No lines inside the silhouette"),
    ("OBJECTS", "Objects", "Lines where one object meets another (from the object ID pass)"),
    ("MATERIALS", "Materials", "Lines where one flat material colour meets another (from the flat pass)"),
)

# Attribute name on bpy.types.Scene. Keep it equal to the add-on id so it is unique.
SCENE_ATTR = "oblique_rig"


def _on_view_mode_update(self: "OBLIQUE_RIG_Settings", context: bpy.types.Context) -> None:
    scene = self.id_data if isinstance(self.id_data, bpy.types.Scene) else context.scene
    rig.apply_view_mode(scene, self.view_mode)


class OBLIQUE_RIG_Settings(PropertyGroup):
    # ------------------------------------------------------------------ frame
    pixels_per_unit: IntProperty(
        name="Pixels per Unit",
        description="Render pixels covered by one Blender unit",
        default=16,
        min=1,
        soft_max=256,
    )
    resolution_x: IntProperty(
        name="Resolution X",
        description="Render width in pixels (rounded up to even in pixel-exact mode)",
        default=320,
        min=1,
        soft_max=4096,
        subtype="PIXEL",
    )
    resolution_y: IntProperty(
        name="Resolution Y",
        description="Render height in pixels (rounded up to even in pixel-exact mode)",
        default=200,
        min=1,
        soft_max=4096,
        subtype="PIXEL",
    )
    camera_height_fraction: FloatProperty(
        name="Camera Height",
        description="Fraction of the frame height the camera sits above z = 0",
        default=0.35,
        soft_min=0.0,
        soft_max=1.0,
        subtype="FACTOR",
    )
    camera_offset_x: FloatProperty(
        name="Camera X",
        description="Horizontal camera position; snapped to whole pixels in pixel-exact mode. Set by Fit",
        default=0.0,
        unit="LENGTH",
    )
    # ------------------------------------------------------------------ projection
    pixel_exact: BoolProperty(
        name="Pixel Exact",
        description=(
            "Take the shear from whole-pixel depth steps, snap the camera to the pixel grid "
            "and force even resolutions, so every edge lands on a pixel"
        ),
        default=True,
    )
    depth_px_right: IntProperty(
        name="Depth Right",
        description="Pixels one unit of depth moves right on screen",
        default=16,
        min=0,
        soft_max=64,
        subtype="PIXEL",
    )
    depth_px_up: IntProperty(
        name="Depth Up",
        description="Pixels one unit of depth moves up on screen",
        default=8,
        min=0,
        soft_max=64,
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
    # ------------------------------------------------------------------ direction
    direction: FloatProperty(
        name="Direction",
        description="Rotation of the source about Z before the shear (the facing)",
        default=0.0,
        subtype="ANGLE",
    )
    auto_seat: BoolProperty(
        name="Auto Seat",
        description=(
            "After rotating, move the whole source so its front edge is at y = 0 and it is centred on x = 0"
        ),
        default=True,
    )
    direction_count: IntProperty(
        name="Directions",
        description="Turnaround facings, evenly spaced around the circle starting at Direction",
        default=4,
        min=1,
        max=16,
    )
    # ------------------------------------------------------------------ output
    output_dir: StringProperty(
        name="Output Folder",
        description="Folder the guide renders are written to (// is relative to the .blend file)",
        default="//guides/",
        subtype="DIR_PATH",
        options={"PATH_SUPPORTS_BLEND_RELATIVE"},
    )
    output_name: StringProperty(
        name="File Name",
        description="Base file name of the guide renders",
        default="guide",
    )
    pass_flat: BoolProperty(
        name="Flat",
        description="Unlit material colours (Workbench flat)",
        default=True,
    )
    pass_shaded: BoolProperty(
        name="Shaded",
        description="Studio-lit material colours (Workbench studio)",
        default=True,
    )
    pass_ids: BoolProperty(
        name="Object IDs",
        description="One flat colour per object",
        default=False,
    )
    pass_silhouette: BoolProperty(
        name="Silhouette",
        description="The opaque shape only, from the flat pass alpha (no extra render)",
        default=False,
    )
    pass_composite: BoolProperty(
        name="Composite",
        description="Shaded (or flat) pass with grid and outline stacked on top, for a quick look",
        default=True,
    )
    make_sheet: BoolProperty(
        name="Sprite Sheet",
        description="Turnaround: also write one horizontal sprite sheet per pass",
        default=True,
    )
    # ------------------------------------------------------------------ grid
    grid_enabled: BoolProperty(
        name="Grid",
        description="Write a floor grid, ground line and depth axis guide pass",
        default=False,
    )
    grid_step: IntProperty(
        name="Grid Step",
        description="Units between grid lines",
        default=1,
        min=1,
    )
    grid_extent: IntProperty(
        name="Grid Extent",
        description="Units drawn on each side of the origin, and in depth",
        default=8,
        min=1,
    )
    grid_color: FloatVectorProperty(
        name="Grid Color",
        description="Colour of the grid lines (the ground line is drawn fully opaque)",
        default=(0.0, 0.8, 1.0, 0.6),
        size=4,
        subtype="COLOR",
        min=0.0,
        max=1.0,
    )
    # ------------------------------------------------------------------ outline
    outline_enabled: BoolProperty(
        name="Outline",
        description="Write an outline pass with whole-pixel line weights",
        default=False,
    )
    outline_outer_px: IntProperty(
        name="Outer Weight",
        description="Width in pixels of the silhouette outline",
        default=1,
        min=0,
        max=8,
        subtype="PIXEL",
    )
    outline_inner_px: IntProperty(
        name="Inner Weight",
        description="Width in pixels of the lines between objects or materials",
        default=1,
        min=0,
        max=8,
        subtype="PIXEL",
    )
    outline_position: EnumProperty(
        name="Position",
        description="Whether the silhouette outline grows the shape or eats into it",
        items=OUTLINE_POSITION_ITEMS,
        default="OUTSIDE",
    )
    inner_lines: EnumProperty(
        name="Inner Lines",
        description="Which boundaries inside the silhouette get lines",
        items=INNER_LINES_ITEMS,
        default="OBJECTS",
    )
    outline_corners: BoolProperty(
        name="Corners",
        description="Grow lines 8-connected (square corners) instead of 4-connected (pixel-art steps)",
        default=False,
    )
    outline_color: FloatVectorProperty(
        name="Outline Color",
        description="Colour of the outline pass",
        default=(0.0, 0.0, 0.0, 1.0),
        size=4,
        subtype="COLOR",
        min=0.0,
        max=1.0,
    )
    # ------------------------------------------------------------------ viewport and readouts
    view_mode: EnumProperty(
        name="View",
        description="Which side of the rig is visible in the viewport",
        items=VIEW_MODE_ITEMS,
        default="SHEARED",
        update=_on_view_mode_update,
    )
    last_footprint: StringProperty(
        name="Footprint",
        description="Size of the sheared content in pixels, set by Build and Fit",
        default="",
    )
    last_warnings: StringProperty(
        name="Depth Warnings",
        description="Source objects whose bounding boxes interpenetrate, so their depth order is unclear",
        default="",
    )


CLASSES: tuple[type, ...] = (OBLIQUE_RIG_Settings,)


def get_settings(context: bpy.types.Context) -> OBLIQUE_RIG_Settings:
    return getattr(context.scene, SCENE_ATTR)


def params_from_settings(settings: OBLIQUE_RIG_Settings) -> RigParams:
    """Plain-value snapshot of the settings for ``rig`` and ``render``."""
    return RigParams(
        pixels_per_unit=settings.pixels_per_unit,
        resolution_x=settings.resolution_x,
        resolution_y=settings.resolution_y,
        slope_run=settings.slope_run,
        slope_rise=settings.slope_rise,
        depth_scale=settings.depth_scale,
        pixel_exact=settings.pixel_exact,
        depth_px_right=settings.depth_px_right,
        depth_px_up=settings.depth_px_up,
        camera_height_fraction=settings.camera_height_fraction,
        camera_offset_x=settings.camera_offset_x,
        direction=settings.direction,
        auto_seat=settings.auto_seat,
        view_mode=settings.view_mode,
    )


def register_scene_properties() -> None:
    setattr(bpy.types.Scene, SCENE_ATTR, PointerProperty(type=OBLIQUE_RIG_Settings))


def unregister_scene_properties() -> None:
    if hasattr(bpy.types.Scene, SCENE_ATTR):
        delattr(bpy.types.Scene, SCENE_ATTR)
