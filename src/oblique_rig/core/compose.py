# SPDX-License-Identifier: GPL-3.0-or-later
"""Layer compositing and sprite sheets on RGBA pixel arrays.

Images are ``(height, width, 4)`` uint8 RGBA with straight (unpremultiplied)
alpha and row 0 at the bottom. Results are rounded half up to integers.

Pure Python + numpy: no bpy.
"""

import math
from collections.abc import Sequence

import numpy as np


def rgba8(color: Sequence[float]) -> tuple[int, int, int, int]:
    """0-255 RGBA tuple from a colour.

    Ints are kept (clamped to 0..255); if any component is a float, all are
    treated as 0..1 (a Blender colour property) and scaled with rounding.
    Three components get an opaque alpha.

    Raises:
        ValueError: for anything but 3 or 4 components.
    """
    values = list(color)
    floats = any(isinstance(v, float | np.floating) for v in values)
    if len(values) == 3:
        values.append(1.0 if floats else 255)
    if len(values) != 4:
        raise ValueError(f"colour needs 3 or 4 components, got {len(values)}")
    if floats:
        values = [math.floor(float(v) * 255 + 0.5) for v in values]
    return tuple(min(max(int(v), 0), 255) for v in values)  # type: ignore[return-value]


def _check_rgba(image: np.ndarray, what: str) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim != 3 or array.shape[2] != 4:
        raise ValueError(f"{what} must be an (h, w, 4) RGBA array, got shape {array.shape}")
    return array


def over(bottom: np.ndarray, top: np.ndarray) -> np.ndarray:
    """Straight-alpha Porter-Duff "over": ``top`` composited onto ``bottom``.

    ``a = a_t + a_b * (1 - a_t)``; ``c = (c_t*a_t + c_b*a_b*(1 - a_t)) / a``
    (0 where ``a`` is 0). Returns a new uint8 array; inputs are untouched.

    Raises:
        ValueError: if the shapes differ or are not ``(h, w, 4)``.
    """
    b = _check_rgba(bottom, "bottom").astype(np.float64) / 255.0
    t = _check_rgba(top, "top").astype(np.float64) / 255.0
    if b.shape != t.shape:
        raise ValueError(f"layer shapes differ: {b.shape} vs {t.shape}")
    a_t = t[..., 3:4]
    a_b = b[..., 3:4] * (1.0 - a_t)
    alpha = a_t + a_b
    with np.errstate(divide="ignore", invalid="ignore"):
        rgb = np.where(alpha > 0, (t[..., :3] * a_t + b[..., :3] * a_b) / alpha, 0.0)
    out = np.concatenate([rgb, alpha], axis=-1)
    return np.clip(np.floor(out * 255.0 + 0.5), 0, 255).astype(np.uint8)


def stack(layers: Sequence[np.ndarray | None]) -> np.ndarray:
    """Composite layers bottom (first) to top (last) with :func:`over`; ``None`` entries are skipped.

    Raises:
        ValueError: if no layer is given, or shapes differ.
    """
    present = [layer for layer in layers if layer is not None]
    if not present:
        raise ValueError("stack() needs at least one layer")
    result = np.array(_check_rgba(present[0], "layer"), dtype=np.uint8, copy=True)
    for layer in present[1:]:
        result = over(result, layer)
    return result


def sheet(frames: Sequence[np.ndarray], columns: int | None = None) -> np.ndarray:
    """Lay equal-sized frames out left to right, wrapping after ``columns`` (default: one row).

    The first row of the sheet is at the top of the image (the highest array
    rows, since row 0 is the bottom). Unused cells are transparent.

    Raises:
        ValueError: if ``frames`` is empty, sizes differ, or ``columns`` < 1.
    """
    if not frames:
        raise ValueError("sheet() needs at least one frame")
    arrays = [_check_rgba(frame, "frame") for frame in frames]
    shape = arrays[0].shape
    if any(a.shape != shape for a in arrays):
        raise ValueError(f"frames must share one size, got {sorted({a.shape for a in arrays})}")
    count = len(arrays)
    cols = count if columns is None else int(columns)
    if cols < 1:
        raise ValueError(f"columns must be >= 1, got {columns}")
    cols = min(cols, count)
    rows = math.ceil(count / cols)
    height, width = shape[:2]
    out = np.zeros((rows * height, cols * width, 4), dtype=np.uint8)
    for index, frame in enumerate(arrays):
        row, col = divmod(index, cols)
        bottom = (rows - 1 - row) * height
        out[bottom : bottom + height, col * width : (col + 1) * width] = frame
    return out
