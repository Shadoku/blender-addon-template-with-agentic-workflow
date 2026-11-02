# SPDX-License-Identifier: GPL-3.0-or-later
"""Common oblique slopes and frame sizes, applied in one click.

Slopes are stored as fractions of ``pixels_per_unit`` so a preset means the
same angle at any pixel density; :func:`slope_preset` turns one into the
whole-pixel ``(depth_px_right, depth_px_up)`` pair. Both tables are tuples of
named tuples, so they unpack like plain ``(identifier, label, ...)`` tuples.

Pure Python: no bpy.
"""

import math
from typing import NamedTuple


class SlopePreset(NamedTuple):
    """One unit of depth moves ``right_per_unit * ppu`` px right and ``up_per_unit * ppu`` px up."""

    identifier: str
    label: str
    right_per_unit: float
    up_per_unit: float


class ResolutionPreset(NamedTuple):
    """Frame size and pixel density."""

    identifier: str
    label: str
    resolution_x: int
    resolution_y: int
    pixels_per_unit: int


SLOPE_PRESETS: tuple[SlopePreset, ...] = (
    SlopePreset("PIXEL_2_1", "2:1 cavalier", 1.0, 0.5),
    SlopePreset("CABINET_2_1", "2:1 cabinet", 0.5, 0.25),
    SlopePreset("PIXEL_1_1", "1:1", 0.5, 0.5),
    SlopePreset("PIXEL_3_2", "3:2", 0.75, 0.5),
    SlopePreset("PIXEL_1_2", "1:2 (steep)", 0.5, 1.0),
)

RESOLUTION_PRESETS: tuple[ResolutionPreset, ...] = (
    ResolutionPreset("R320_200_16", "320 x 200, 16 px/unit", 320, 200, 16),
    ResolutionPreset("R640_360_16", "640 x 360, 16 px/unit", 640, 360, 16),
    ResolutionPreset("R256_256_16", "256 x 256, 16 px/unit", 256, 256, 16),
    ResolutionPreset("R128_128_8", "128 x 128, 8 px/unit", 128, 128, 8),
    ResolutionPreset("R512_288_32", "512 x 288, 32 px/unit", 512, 288, 32),
)


def _whole_pixels(fraction: float, pixels_per_unit: int) -> int:
    """``fraction * ppu`` rounded half up, at least 1 when the fraction is non-zero."""
    if fraction == 0:
        return 0
    value = math.floor(abs(fraction) * pixels_per_unit + 0.5)
    return int(math.copysign(max(value, 1), fraction))


def slope_preset(identifier: str, pixels_per_unit: int) -> tuple[int, int]:
    """``(depth_px_right, depth_px_up)`` for a slope preset at ``pixels_per_unit``.

    Raises:
        ValueError: for an unknown identifier or ``pixels_per_unit`` < 1.
    """
    if pixels_per_unit < 1:
        raise ValueError(f"pixels_per_unit must be positive, got {pixels_per_unit}")
    for preset in SLOPE_PRESETS:
        if preset.identifier == identifier:
            return (
                _whole_pixels(preset.right_per_unit, pixels_per_unit),
                _whole_pixels(preset.up_per_unit, pixels_per_unit),
            )
    raise ValueError(f"unknown slope preset {identifier!r}")


def resolution_preset(identifier: str) -> ResolutionPreset:
    """Look up a resolution preset by identifier.

    Raises:
        ValueError: for an unknown identifier.
    """
    for preset in RESOLUTION_PRESETS:
        if preset.identifier == identifier:
            return preset
    raise ValueError(f"unknown resolution preset {identifier!r}")
