# SPDX-License-Identifier: GPL-3.0-or-later
"""Guide overlays drawn on pixel arrays: Bresenham lines and the floor grid.

Canvases are ``(height, width, 4)`` uint8 RGBA with row 0 at the bottom, so
``canvas[y, x]`` is the pixel ``x`` from the left and ``y`` from the bottom.
Lines overwrite pixels (no blending) and are clipped to the canvas.

Colours are 0-255 ints, or floats in 0..1 (a Blender colour property), which
are scaled and rounded.

Pure Python + numpy: no bpy.
"""

import math
from collections.abc import Sequence

import numpy as np

_EPS = 1e-6


def _rgba8(color: Sequence[float]) -> tuple[int, int, int, int]:
    """0-255 RGBA from ints (kept) or floats in 0..1 (scaled); 3 values get alpha 255."""
    values = list(color)
    if len(values) == 3:
        values.append(1.0 if any(isinstance(v, float | np.floating) for v in values) else 255)
    if len(values) != 4:
        raise ValueError(f"colour needs 3 or 4 components, got {len(values)}")
    if any(isinstance(v, float | np.floating) for v in values):
        values = [int(np.floor(float(v) * 255 + 0.5)) for v in values]
    return tuple(min(max(int(v), 0), 255) for v in values)  # type: ignore[return-value]


def line(canvas: np.ndarray, x0: int, y0: int, x1: int, y1: int, color_rgba: Sequence[float]) -> None:
    """Draw a Bresenham line from ``(x0, y0)`` to ``(x1, y1)`` in place, both ends included.

    Exactly ``max(|dx|, |dy|) + 1`` pixels before clipping; pixels outside the
    canvas are skipped.
    """
    color = np.array(_rgba8(color_rgba), dtype=np.uint8)
    height, width = canvas.shape[:2]
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    xs: list[int] = []
    ys: list[int] = []
    while True:
        if 0 <= x < width and 0 <= y < height:
            xs.append(x)
            ys.append(y)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    if xs:
        canvas[ys, xs] = color


def _pixel(value: float) -> int:
    """Pixel index containing a continuous coordinate (float noise ignored)."""
    return math.floor(value + _EPS)


def grid_layer(
    width: int,
    height: int,
    a_px: float,
    b_px: float,
    pixels_per_unit: float,
    cam_x_px: float,
    cam_z_px: float,
    step_units: int,
    extent_units: int,
    color_rgba: Sequence[float],
) -> np.ndarray:
    """Floor grid (z = 0) as a ``(height, width, 4)`` uint8 layer.

    ``a_px``/``b_px`` are the pixels one unit of depth moves right/up,
    ``cam_x_px``/``cam_z_px`` the camera position in pixels relative to the
    frame centre (``cam_x * ppu``, ``cam_z * ppu``). The world origin lands on
    ``(width/2 - cam_x_px, height/2 - cam_z_px)`` and a floor point
    ``(x, y, 0)`` on ``(origin_x + x*ppu + y*a_px, origin_y + y*b_px)``; each
    grid point is drawn in the pixel that contains it (its lower-left corner).

    Depth lines (constant y = k for k = 0, step, ... <= extent) are rows from
    x = -extent to +extent; x lines (constant x = i, i a multiple of step in
    -extent..extent) run along the depth direction from depth 0 to extent.
    Every line uses ``color_rgba`` except the ground line (k = 0), which is
    drawn last with alpha 255.

    Raises:
        ValueError: if ``step_units`` < 1, ``extent_units`` < 0 or the size is not positive.
    """
    if step_units < 1:
        raise ValueError(f"step_units must be >= 1, got {step_units}")
    if extent_units < 0:
        raise ValueError(f"extent_units must be >= 0, got {extent_units}")
    if width <= 0 or height <= 0:
        raise ValueError(f"canvas size must be positive, got {width}x{height}")
    color = _rgba8(color_rgba)
    ground = (*color[:3], 255)
    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    origin_x = width / 2 - cam_x_px
    origin_y = height / 2 - cam_z_px

    def project(x: float, y: float) -> tuple[int, int]:
        return _pixel(origin_x + x * pixels_per_unit + y * a_px), _pixel(origin_y + y * b_px)

    extent = int(extent_units)
    for i in range(-extent, extent + 1):
        if i % step_units == 0:
            line(canvas, *project(i, 0), *project(i, extent), color)
    for k in range(step_units, extent + 1, step_units):
        line(canvas, *project(-extent, k), *project(extent, k), color)
    line(canvas, *project(-extent, 0), *project(extent, 0), ground)
    return canvas
