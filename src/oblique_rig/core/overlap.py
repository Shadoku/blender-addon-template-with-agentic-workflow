# SPDX-License-Identifier: GPL-3.0-or-later
"""Depth-sort warning: which source objects cannot be ordered from the silhouette alone.

Two objects are reported when their sheared screen rectangles overlap (with
positive area) and their depth (y) ranges overlap too: then neither is
entirely in front of the other, and the painter has to check the 3D scene to
know which part covers which. Touching edges or a shared depth plane do not
count.

Pure Python: no bpy.
"""

from collections.abc import Sequence

Rect = tuple[float, float, float, float]
"""(xmin, ymin, xmax, ymax) in pixels."""

_EPS = 1e-9


def _overlap(lo_a: float, hi_a: float, lo_b: float, hi_b: float) -> bool:
    return min(hi_a, hi_b) - max(lo_a, lo_b) > _EPS


def overlapping_pairs(
    items: Sequence[tuple[str, Sequence[float], Sequence[float]]],
) -> list[tuple[str, str]]:
    """Pairs ``(name_i, name_j)``, ``i < j`` in input order, whose rects and depth ranges both overlap.

    Each item is ``(name, (xmin, ymin, xmax, ymax), (y_min, y_max))``: the
    screen rect from ``oblique.screen_rect`` and the object's depth range.
    """
    pairs: list[tuple[str, str]] = []
    for i, (name_a, rect_a, depth_a) in enumerate(items):
        for name_b, rect_b, depth_b in items[i + 1 :]:
            if (
                _overlap(rect_a[0], rect_a[2], rect_b[0], rect_b[2])
                and _overlap(rect_a[1], rect_a[3], rect_b[1], rect_b[3])
                and _overlap(depth_a[0], depth_a[1], depth_b[0], depth_b[1])
            ):
                pairs.append((name_a, name_b))
    return pairs


def format_warnings(pairs: Sequence[tuple[str, str]]) -> str:
    """One line for ``last_warnings``: ``"A / B overlap in depth; C / D overlap in depth"`` ("" if none)."""
    return "; ".join(f"{a} / {b} overlap in depth" for a, b in pairs)
