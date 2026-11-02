# SPDX-License-Identifier: GPL-3.0-or-later
"""Whole-pixel outlines on boolean masks, for pixel-art reference passes.

Arrays follow Blender's image layout: ``(height, width)`` masks and
``(height, width, 4)`` uint8 RGBA images with row 0 at the bottom. A pixel is
part of a shape when its alpha is at least :data:`ALPHA_THRESHOLD` (128); the
Workbench flat pass has no partially transparent pixels, so the threshold only
matters for hand-made input.

Morphology is done one step at a time with array shifts: a 4-connected step
uses the cross (plus) kernel, which grows a pixel into a diamond (the usual
pixel-art outline); ``corners=True`` uses the 3x3 square kernel. Pixels
outside the canvas count as background for :func:`dilate` and as shape for
:func:`erode` (``erode(m) == ~dilate(~m)``), so neither outline position draws
a line along the frame edge.

Pure Python + numpy: no bpy.
"""

from collections.abc import Sequence

import numpy as np

ALPHA_THRESHOLD = 128
"""Alpha at or above this counts as opaque (part of the shape)."""

POSITIONS = ("OUTSIDE", "INSIDE")


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


def _check_steps(steps: int) -> None:
    if steps < 0:
        raise ValueError(f"steps must be >= 0, got {steps}")


def _grow_once(mask: np.ndarray, corners: bool) -> np.ndarray:
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    if corners:
        out[1:, 1:] |= mask[:-1, :-1]
        out[1:, :-1] |= mask[:-1, 1:]
        out[:-1, 1:] |= mask[1:, :-1]
        out[:-1, :-1] |= mask[1:, 1:]
    return out


def dilate(mask: np.ndarray, steps: int, corners: bool = False) -> np.ndarray:
    """Grow a bool mask by ``steps`` pixels (4-connected, or 8-connected with ``corners``).

    Returns a new array; ``steps == 0`` returns a copy.

    Raises:
        ValueError: if ``steps`` is negative.
    """
    _check_steps(steps)
    out = np.array(mask, dtype=bool, copy=True)
    for _ in range(steps):
        out = _grow_once(out, corners)
    return out


def erode(mask: np.ndarray, steps: int, corners: bool = False) -> np.ndarray:
    """Shrink a bool mask by ``steps`` pixels; the dual of :func:`dilate`.

    Pixels outside the canvas count as shape, so a shape cut by the frame
    edge is not eaten from that side.

    Raises:
        ValueError: if ``steps`` is negative.
    """
    _check_steps(steps)
    return ~dilate(~np.asarray(mask, dtype=bool), steps, corners)


def opaque_mask(image: np.ndarray) -> np.ndarray:
    """Shape mask of an RGBA image ``(h, w, 4)``, an alpha channel ``(h, w)`` or a bool mask.

    Alpha >= :data:`ALPHA_THRESHOLD` is opaque; bool input is returned as a copy.
    """
    array = np.asarray(image)
    if array.dtype == bool:
        return array.copy()
    if array.ndim == 3:
        array = array[..., 3]
    return array >= ALPHA_THRESHOLD


def outer_outline(
    alpha: np.ndarray, weight: int, position: str = "OUTSIDE", corners: bool = False
) -> np.ndarray:
    """Silhouette outline ``weight`` pixels wide, as a bool mask.

    ``alpha`` is an alpha channel, an RGBA image or a bool mask (see
    :func:`opaque_mask`). OUTSIDE: ``dilate(shape, weight) & ~shape`` (the
    line grows the shape); INSIDE: ``shape & ~erode(shape, weight)`` (the
    line eats into it). ``weight == 0`` gives an empty mask.

    Raises:
        ValueError: for an unknown ``position`` or a negative ``weight``.
    """
    if position not in POSITIONS:
        raise ValueError(f"position must be one of {POSITIONS}, got {position!r}")
    _check_steps(weight)
    shape = opaque_mask(alpha)
    if weight == 0:
        return np.zeros_like(shape)
    if position == "OUTSIDE":
        return dilate(shape, weight, corners) & ~shape
    return shape & ~erode(shape, weight, corners)


def label_image(rgba: np.ndarray) -> np.ndarray:
    """Region ids per pixel: each distinct opaque RGB gets an id, transparent pixels -1.

    Ids start at 0 and follow ascending ``0xRRGGBB`` order, so they are
    stable for the same set of colours. Alpha < :data:`ALPHA_THRESHOLD` is
    transparent whatever its RGB. Returns an int64 ``(h, w)`` array.
    """
    image = np.asarray(rgba)
    if image.ndim != 3 or image.shape[2] < 4:
        raise ValueError(f"expected an (h, w, 4) RGBA array, got shape {image.shape}")
    rgb = image[..., :3].astype(np.int64)
    keys = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    opaque = image[..., 3] >= ALPHA_THRESHOLD
    labels = np.full(keys.shape, -1, dtype=np.int64)
    if opaque.any():
        _, inverse = np.unique(keys[opaque], return_inverse=True)
        labels[opaque] = inverse.reshape(-1)
    return labels


def _boundaries(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(low, high): pixels on the left/lower and right/upper side of each label change."""
    lab = np.asarray(labels)
    valid = lab >= 0
    low = np.zeros(lab.shape, dtype=bool)
    high = np.zeros(lab.shape, dtype=bool)
    across = (lab[:, :-1] != lab[:, 1:]) & valid[:, :-1] & valid[:, 1:]
    low[:, :-1] |= across
    high[:, 1:] |= across
    up = (lab[:-1, :] != lab[1:, :]) & valid[:-1, :] & valid[1:, :]  # row + 1 is above
    low[:-1, :] |= up
    high[1:, :] |= up
    return low, high


def inner_lines(labels: np.ndarray, weight: int, corners: bool = False) -> np.ndarray:
    """Lines between touching regions (both labels >= 0), ``weight`` pixels wide.

    Weight 1 marks exactly the pixels whose right or upper neighbour has a
    different label. Wider lines straddle the boundary: odd weights grow that
    set by ``(weight - 1) // 2`` steps on both sides; even weights also take
    the pixels on the other side of the boundary first. Lines never leave the
    shape (labels >= 0); the silhouette edge is :func:`outer_outline`'s job.
    ``weight == 0`` gives an empty mask.

    Raises:
        ValueError: if ``weight`` is negative.
    """
    _check_steps(weight)
    lab = np.asarray(labels)
    if weight == 0:
        return np.zeros(lab.shape, dtype=bool)
    low, high = _boundaries(lab)
    seed = low | high if weight % 2 == 0 else low
    return dilate(seed, (weight - 1) // 2, corners) & (lab >= 0)


def paint(mask: np.ndarray, color_rgba: Sequence[float]) -> np.ndarray:
    """``(h, w, 4)`` uint8 layer: ``color_rgba`` where ``mask`` is set, transparent elsewhere.

    The colour is 0-255 ints, or floats in 0..1 (e.g. a Blender colour
    property), which are scaled and rounded.
    """
    m = np.asarray(mask, dtype=bool)
    out = np.zeros((*m.shape, 4), dtype=np.uint8)
    out[m] = _rgba8(color_rgba)
    return out
