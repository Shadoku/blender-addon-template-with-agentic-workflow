# SPDX-License-Identifier: GPL-3.0-or-later
"""Depth-sort warning: which source objects genuinely interpenetrate.

Two objects are reported when their world-space bounding boxes (before the
shear) overlap by more than a hair on all three axes: then the objects push
into each other, neither is entirely in front, and the painter has to check
the 3D scene to know which part covers which. Boxes that only touch, such as a
cube standing on a floor plane or two crates side by side, are not reported;
one box entirely behind another is not either, since the shear keeps depth
order intact.

Pure Python: no bpy.
"""

from collections.abc import Sequence

Vec3 = Sequence[float]

_EPS = 1e-9


def _overlap(lo_a: float, hi_a: float, lo_b: float, hi_b: float) -> bool:
    return min(hi_a, hi_b) - max(lo_a, lo_b) > _EPS


def overlapping_pairs(items: Sequence[tuple[str, Vec3, Vec3]]) -> list[tuple[str, str]]:
    """Pairs ``(name_i, name_j)``, ``i < j`` in input order, whose boxes overlap on all three axes.

    Each item is ``(name, (xmin, ymin, zmin), (xmax, ymax, zmax))``: an
    object's axis-aligned bounding box in world space, unsheared (see
    ``rig.source_boxes``). An overlap of 1e-9 or less on any axis counts as
    touching, not overlapping.
    """
    pairs: list[tuple[str, str]] = []
    for i, (name_a, lo_a, hi_a) in enumerate(items):
        for name_b, lo_b, hi_b in items[i + 1 :]:
            if all(_overlap(lo_a[k], hi_a[k], lo_b[k], hi_b[k]) for k in range(3)):
                pairs.append((name_a, name_b))
    return pairs


def format_warnings(pairs: Sequence[tuple[str, str]]) -> str:
    """One line for ``last_warnings``: ``"A / B overlap in depth; C / D overlap in depth"`` ("" if none)."""
    return "; ".join(f"{a} / {b} overlap in depth" for a, b in pairs)
