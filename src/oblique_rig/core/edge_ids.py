# SPDX-License-Identifier: GPL-3.0-or-later
"""Island index <-> colour encoding for the sharp-edge ("EDGES") outline pass.

The rig's node group can split the source along sharp edges (Split Edges with
``Edge Angle > Crease Angle`` or the ``sharp_edge`` attribute), number the
resulting mesh islands (Mesh Island) and store each island's colour as the
corner colour attribute :data:`EDGE_ID_ATTRIBUTE`. Workbench renders that
attribute in VERTEX colour mode; under the Raw view transform a stored linear
value of ``byte / 255`` comes back as exactly ``byte``. Every pixel of the
render then names its island, and the outline code draws a line wherever two
islands meet.

Encoding: each channel holds 5 bits of the index as one of 32 levels, 8 byte
values apart and offset by 4 (``4, 12, ..., 252``)::

    r = (i % 32) * 8 + 4
    g = (i // 32 % 32) * 8 + 4
    b = (i // 1024 % 32) * 8 + 4

That gives :data:`ID_COUNT` (32768) distinct colours; larger indices wrap, as
the node tree's per-channel modulo does. Neighbouring levels are 8 apart, so
the +-1 noise Workbench sometimes adds (and that
``core.outline.merge_near_colors`` removes) can never merge two islands, and
:func:`island_index` decodes colours up to 3 steps off.

Pure Python: no bpy.
"""

from collections.abc import Sequence

EDGE_ID_ATTRIBUTE = "oblique_edge_id"
"""Corner-domain FLOAT_COLOR attribute the node group stores the island colour in."""

SHARP_EDGE_ATTRIBUTE = "sharp_edge"
"""Blender's edge attribute for edges marked sharp (Edge > Mark Sharp)."""

LEVELS = 32
"""Levels per channel (5 bits)."""

STEP = 8
"""Byte distance between neighbouring levels."""

OFFSET = 4
"""Byte value of level 0; keeps every level away from 0 and 255."""

CHANNEL_DIVISORS = (1, LEVELS, LEVELS * LEVELS)
"""Per channel (r, g, b): the index is divided by this, floored, then taken modulo LEVELS."""

ID_COUNT = LEVELS**3
"""Distinct colours before indices wrap (32768)."""


def island_color(index: int) -> tuple[int, int, int]:
    """Byte colour ``(r, g, b)`` of island ``index`` (wraps every :data:`ID_COUNT`).

    Raises:
        ValueError: if ``index`` is negative.
    """
    if index < 0:
        raise ValueError(f"island index must be >= 0, got {index}")
    r, g, b = ((index // div) % LEVELS * STEP + OFFSET for div in CHANNEL_DIVISORS)
    return r, g, b


def _level(byte: float) -> int:
    value = float(byte)
    if not 0 <= value <= 255:
        raise ValueError(f"colour channel must be in 0..255, got {byte}")
    return min(max(round((value - OFFSET) / STEP), 0), LEVELS - 1)


def island_index(rgb: Sequence[float]) -> int:
    """Island index of a rendered colour; the inverse of :func:`island_color`.

    Takes ``(r, g, b)`` or ``(r, g, b, a)`` bytes (alpha ignored) and snaps
    each channel to the nearest level, so colours up to 3 steps off decode to
    the same index.

    Raises:
        ValueError: for fewer than 3 channels or a channel outside 0..255.
    """
    values = list(rgb)
    if len(values) < 3:
        raise ValueError(f"expected (r, g, b), got {values}")
    r, g, b = (_level(c) for c in values[:3])
    return r + g * LEVELS + b * LEVELS * LEVELS


def linear_value(byte: int) -> float:
    """The linear value to store for ``byte`` so the Raw view transform renders exactly ``byte``.

    Raises:
        ValueError: if ``byte`` is outside 0..255.
    """
    if not 0 <= byte <= 255:
        raise ValueError(f"byte must be in 0..255, got {byte}")
    return byte / 255.0
