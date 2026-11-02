# SPDX-License-Identifier: GPL-3.0-or-later
"""Render guide passes to disk: Workbench renders plus layers derived in Python.

Blender does the minimum: flat Workbench renders with anti-aliasing and pixel
filtering off and a transparent film, so every pixel is either fully covered or
empty and colours are exact. Everything else (silhouette, outline, grid,
composite, sprite sheets) is computed on pixel arrays by ``core`` and written by
our own PNG encoder, so the bytes on disk are exactly what core produced.

Facts this module relies on (see docs/PLAN-oblique-rig-v0.2.md, section 1):

- Workbench needs libEGL headless; without it Blender exits outright.
- ``render.engine`` accepts ``"BLENDER_WORKBENCH"`` although the enum items
  list only EEVEE.
- Under the Standard view transform the look is ``"None"``; ``"NONE"`` raises.
- After ``image.colorspace_settings.name = "Non-Color"`` an image's ``pixels``
  are the raw byte values / 255, rows bottom-up.

The ids pass needs one colour per source object, but the rig realizes the
whole source collection into a single mesh, so Workbench's RANDOM colour (one
per *object*) paints it all one colour. Instead every source object's data
temporarily gets a uniquely coloured material and the pass renders with
MATERIAL colour; the original material slots are put back afterwards.
"""

import colorsys
import math
import os
from typing import Any

import bpy
import numpy as np

from . import rig
from .core import compose, guides, outline, png
from .core.oblique import MODIFIER_NAME, RIG_NAME, SOURCE_COLLECTION

PASS_ORDER = ("flat", "shaded", "ids", "silhouette", "outline", "grid", "composite")
RENDER_KINDS = ("FLAT", "SHADED", "IDS")
DIRECTION_INPUT = "Direction"
ID_MATERIAL_PREFIX = "OBLIQUE_RIG_id_"
SILHOUETTE_COLOR = (0, 0, 0, 255)


# --------------------------------------------------------------------------- settings guard


def _rig_modifier() -> bpy.types.Modifier | None:
    ob = bpy.data.objects.get(RIG_NAME)
    if ob is None:
        return None
    mod = ob.modifiers.get(MODIFIER_NAME)
    if mod is None or mod.type != "NODES" or mod.node_group is None:
        return None
    return mod


def get_direction() -> float | None:
    """The rig modifier's "Direction" input, or None if there is no rig (or no such input)."""
    mod = _rig_modifier()
    if mod is None:
        return None
    try:
        return float(rig.get_modifier_input(mod, DIRECTION_INPUT))
    except KeyError:
        return None


def set_direction(radians: float) -> None:
    """Set the rig modifier's "Direction" input and tag the rig for re-evaluation."""
    mod = _rig_modifier()
    if mod is None:
        raise RuntimeError(f"no '{RIG_NAME}' object with a '{MODIFIER_NAME}' modifier; build the rig first")
    rig.set_modifier_input(mod, DIRECTION_INPUT, float(radians))
    mod.id_data.update_tag()


class RenderSettingsGuard:
    """Save every render setting this module touches and restore it on exit.

    Values are restored in the order they were saved: ``file_format`` before
    ``color_depth`` and ``view_transform`` before ``look``, because the valid
    values of the latter depend on the former.
    """

    RENDER_ATTRS = (
        "engine",
        "filepath",
        "filter_size",
        "film_transparent",
        "resolution_x",
        "resolution_y",
        "resolution_percentage",
        "dither_intensity",
        "use_border",
        "use_compositing",
        "use_sequencer",
    )
    IMAGE_ATTRS = ("file_format", "color_mode", "color_depth", "compression")
    SHADING_ATTRS = (
        "light",
        "color_type",
        "single_color",
        "show_object_outline",
        "show_cavity",
        "show_shadows",
        "show_xray",
    )
    VIEW_ATTRS = ("view_transform", "look")

    def __init__(self, scene: bpy.types.Scene) -> None:
        self.scene = scene
        self._saved: list[tuple[Any, str, Any]] = []
        self._direction: float | None = None

    def _owners(self) -> list[tuple[Any, tuple[str, ...]]]:
        s = self.scene
        return [
            (s.render, self.RENDER_ATTRS),
            (s.render.image_settings, self.IMAGE_ATTRS),
            (s.display, ("render_aa",)),
            (s.display.shading, self.SHADING_ATTRS),
            (s.view_settings, self.VIEW_ATTRS),
        ]

    def __enter__(self) -> "RenderSettingsGuard":
        self._saved = []
        for owner, attrs in self._owners():
            for attr in attrs:
                value = getattr(owner, attr)
                if hasattr(value, "__len__") and not isinstance(value, str):
                    value = tuple(value)
                self._saved.append((owner, attr, value))
        self._direction = get_direction()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        for owner, attr, value in self._saved:
            if getattr(owner, attr) != value:
                setattr(owner, attr, value)
        if self._direction is not None and get_direction() != self._direction:
            set_direction(self._direction)
        return False


# --------------------------------------------------------------------------- ids materials


def _srgb_to_linear(byte: int) -> float:
    c = byte / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _id_color(index: int) -> tuple[float, float, float, float]:
    """A distinct, saturated colour per index (golden-ratio hue steps, two brightness levels).

    The colour is chosen as whole sRGB bytes and returned as the linear value
    that the Standard view transform turns back into exactly those bytes, so
    the GPU's rounding noise (seen as +-1 on 4.5) cannot split one object into
    two labels.
    """
    hue = (index * 0.618033988749895) % 1.0
    value = 0.95 if index % 2 == 0 else 0.6
    rgb = colorsys.hsv_to_rgb(hue, 0.75, value)
    r, g, b = (_srgb_to_linear(round(c * 255.0)) for c in rgb)
    return r, g, b, 1.0


def merge_near_colors(rgba: np.ndarray, tolerance: int = 1) -> np.ndarray:
    """Snap colours within ``tolerance`` per channel to the most frequent one among them.

    Workbench's flat colours can differ by one step between pixels of the same
    face (Blender 4.5), which would otherwise turn every face into a patchwork
    of labels for :func:`core.outline.label_image`.
    """
    out = np.array(rgba, dtype=np.uint8, copy=True)
    opaque = out[..., 3] > 0
    if not opaque.any():
        return out
    colors, inverse, counts = np.unique(out[opaque], axis=0, return_inverse=True, return_counts=True)
    reps: list[np.ndarray] = []
    mapping = np.empty(len(colors), dtype=np.int64)
    for i in np.argsort(-counts, kind="stable"):
        c = colors[i].astype(np.int64)
        for j, rep in enumerate(reps):
            if np.abs(c - rep).max() <= tolerance:
                mapping[i] = j
                break
        else:
            mapping[i] = len(reps)
            reps.append(c)
    out[opaque] = np.array(reps, dtype=np.uint8)[mapping[inverse.reshape(-1)]]
    return out


class _IdMaterials:
    """Give every source object's data one temporary flat-coloured material; undo on exit.

    Data shared between several source objects gets the colour of the first
    one (sorted by name), so linked duplicates share an id.
    """

    def __init__(self) -> None:
        self._saved: list[tuple[Any, list]] = []
        self._materials: list[bpy.types.Material] = []

    def __enter__(self) -> "_IdMaterials":
        source = bpy.data.collections.get(SOURCE_COLLECTION)
        objects = sorted(source.all_objects, key=lambda ob: ob.name) if source is not None else []
        seen: set[int] = set()  # as_pointer() of each data block already coloured
        for ob in objects:
            data = ob.data
            slots = getattr(data, "materials", None)
            if slots is None or data.library is not None or data.as_pointer() in seen:
                continue
            seen.add(data.as_pointer())
            mat = bpy.data.materials.new(f"{ID_MATERIAL_PREFIX}{len(self._materials)}")
            mat.diffuse_color = _id_color(len(self._materials))
            self._materials.append(mat)
            self._saved.append((data, list(slots)))
            if len(slots) == 0:
                slots.append(mat)
            else:
                for i in range(len(slots)):
                    slots[i] = mat
            data.update_tag()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        for data, original in self._saved:
            slots = data.materials
            while len(slots) > len(original):
                slots.pop()
            for i, mat in enumerate(original):
                slots[i] = mat
            data.update_tag()
        for mat in self._materials:
            bpy.data.materials.remove(mat)
        self._saved, self._materials = [], []
        return False


# --------------------------------------------------------------------------- rendering


def _set_look_none(scene: bpy.types.Scene) -> None:
    try:
        scene.view_settings.look = "None"
    except TypeError:
        scene.view_settings.look = "NONE"


def render_pass(scene: bpy.types.Scene, kind: str, path: str) -> None:
    """Render one Workbench pass to ``path`` (PNG RGBA 8-bit) with exact, unfiltered pixels.

    ``kind``: FLAT (flat light, material colour), SHADED (studio light,
    material colour) or IDS (flat light, one temporary colour per source
    object). Leaves the changed settings in place; wrap calls in
    :class:`RenderSettingsGuard`.
    """
    if kind not in RENDER_KINDS:
        raise ValueError(f"kind must be one of {RENDER_KINDS}, got {kind!r}")
    if scene.camera is None:
        raise RuntimeError("the scene has no camera; build the rig first")

    r = scene.render
    r.engine = "BLENDER_WORKBENCH"
    r.filter_size = 0.0
    r.film_transparent = True
    r.dither_intensity = 0.0
    r.use_border = False
    r.use_compositing = False
    r.use_sequencer = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    r.image_settings.color_depth = "8"
    r.image_settings.compression = 15
    scene.display.render_aa = "OFF"
    shading = scene.display.shading
    shading.light = "STUDIO" if kind == "SHADED" else "FLAT"
    shading.color_type = "MATERIAL"
    shading.show_object_outline = False
    shading.show_cavity = False
    shading.show_shadows = False
    shading.show_xray = False
    scene.view_settings.view_transform = "Standard"
    _set_look_none(scene)
    r.filepath = path

    if kind == "IDS":
        with _IdMaterials():
            bpy.ops.render.render(write_still=True, scene=scene.name)
    else:
        bpy.ops.render.render(write_still=True, scene=scene.name)


def read_rgba(path: str) -> np.ndarray:
    """Load a PNG through Blender as raw bytes: ``uint8 (h, w, 4)``, row 0 at the bottom."""
    image = bpy.data.images.load(path, check_existing=False)
    try:
        image.colorspace_settings.name = "Non-Color"
        width, height = image.size
        buf = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(buf)
    finally:
        bpy.data.images.remove(image)
    return np.clip(np.rint(buf * 255.0), 0, 255).astype(np.uint8).reshape(height, width, 4)


def write_rgba(path: str, pixels: np.ndarray) -> None:
    """Write ``uint8 (h, w, 4)`` pixels (row 0 at the bottom) as a byte-exact PNG."""
    png.write_png(path, pixels, bottom_up=True)


# --------------------------------------------------------------------------- guides


def _needed_renders(settings) -> dict[str, bool]:
    inner_from_ids = (
        settings.outline_enabled and settings.inner_lines == "OBJECTS" and settings.outline_inner_px > 0
    )
    inner_from_flat = (
        settings.outline_enabled and settings.inner_lines == "MATERIALS" and settings.outline_inner_px > 0
    )
    return {
        "flat": bool(
            settings.pass_flat
            or settings.pass_silhouette
            or settings.outline_enabled
            or inner_from_flat
            or (settings.pass_composite and not settings.pass_shaded)
        ),
        "shaded": bool(settings.pass_shaded),
        "ids": bool(settings.pass_ids or inner_from_ids),
    }


def _outline_mask(settings, flat: np.ndarray, ids: np.ndarray | None) -> np.ndarray:
    corners = bool(settings.outline_corners)
    mask = outline.outer_outline(
        flat[..., 3], settings.outline_outer_px, position=settings.outline_position, corners=corners
    )
    if settings.outline_inner_px > 0 and settings.inner_lines != "NONE":
        source = ids if settings.inner_lines == "OBJECTS" else flat
        if source is not None:
            labels = outline.label_image(merge_near_colors(source))
            mask = mask | outline.inner_lines(labels, settings.outline_inner_px, corners=corners)
    return mask


def _grid(settings, params, width: int, height: int) -> np.ndarray:
    ppu = params.pixels_per_unit
    a, b = params.shear()
    cam_x, _, cam_z = params.camera()
    return guides.grid_layer(
        width,
        height,
        a * ppu,
        b * ppu,
        ppu,
        cam_x * ppu,
        cam_z * ppu,
        settings.grid_step,
        settings.grid_extent,
        compose.rgba8(tuple(settings.grid_color)),
    )


def render_guides(
    scene: bpy.types.Scene,
    settings,
    params,
    out_dir: str,
    name: str,
    direction: float | None = None,
) -> list[str]:
    """Render and derive the enabled passes; write ``<name>_<pass>.png`` files; return their paths.

    ``settings`` is read by attribute only (the PropertyGroup or any object
    with the same fields); ``params`` is a ``core.oblique.RigParams``. With
    ``direction`` the rig's "Direction" input is set for this call and
    restored afterwards, like every render setting.
    """
    os.makedirs(out_dir, exist_ok=True)

    def path_of(pass_name: str) -> str:
        return os.path.join(out_dir, f"{name}_{pass_name}.png")

    width, height = params.effective_resolution()
    needed = _needed_renders(settings)
    images: dict[str, np.ndarray] = {}
    written: dict[str, str] = {}

    with RenderSettingsGuard(scene):
        if direction is not None:
            set_direction(direction)
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100

        for pass_name, kind in (("flat", "FLAT"), ("shaded", "SHADED"), ("ids", "IDS")):
            if not needed[pass_name]:
                continue
            path = path_of(pass_name)
            render_pass(scene, kind, path)
            images[pass_name] = read_rgba(path)
            if getattr(settings, f"pass_{pass_name}"):
                written[pass_name] = path
            else:
                os.remove(path)  # rendered only to derive other passes

    flat = images.get("flat")
    layers: dict[str, np.ndarray] = {}
    if settings.pass_silhouette and flat is not None:
        layers["silhouette"] = outline.paint(flat[..., 3] >= 128, SILHOUETTE_COLOR)
    if settings.outline_enabled and flat is not None:
        mask = _outline_mask(settings, flat, images.get("ids"))
        layers["outline"] = outline.paint(mask, compose.rgba8(tuple(settings.outline_color)))
    if settings.grid_enabled:
        layers["grid"] = _grid(settings, params, width, height)
    if settings.pass_composite:
        base = images.get("shaded", flat)
        stack = [base] if base is not None else []
        stack += [layers[key] for key in ("grid", "outline") if key in layers]
        if stack:
            layers["composite"] = compose.stack(stack)

    for pass_name, pixels in layers.items():
        path = path_of(pass_name)
        write_rgba(path, pixels)
        written[pass_name] = path
    return [written[p] for p in PASS_ORDER if p in written]


def pass_name_of(path: str, name: str) -> str:
    """The pass part of ``<name>_<pass>.png``."""
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem[len(name) + 1 :] if stem.startswith(name + "_") else stem


def render_turnaround(
    scene: bpy.types.Scene,
    settings,
    params,
    out_dir: str,
    name: str,
    start: float,
    count: int,
    make_sheet: bool,
) -> list[str]:
    """``count`` facings evenly spaced from ``start`` as ``<name>_dNN_<pass>.png``, plus sheets.

    With ``make_sheet`` each pass's frames are read back and laid out left to
    right in ``<name>_sheet_<pass>.png``. The "Direction" input is restored.
    """
    written: list[str] = []
    frames: dict[str, list[str]] = {}
    with RenderSettingsGuard(scene):
        for i in range(count):
            frame_name = f"{name}_d{i:02d}"
            angle = start + i * 2.0 * math.pi / count
            paths = render_guides(scene, settings, params, out_dir, frame_name, direction=angle)
            written += paths
            for path in paths:
                frames.setdefault(pass_name_of(path, frame_name), []).append(path)
    if make_sheet:
        for pass_name in PASS_ORDER:
            paths = frames.get(pass_name)
            if not paths:
                continue
            sheet = compose.sheet([read_rgba(path) for path in paths])
            path = os.path.join(out_dir, f"{name}_sheet_{pass_name}.png")
            write_rgba(path, sheet)
            written.append(path)
    return written
