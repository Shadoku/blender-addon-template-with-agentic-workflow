# SPDX-License-Identifier: GPL-3.0-or-later
"""Maths and names for the oblique (2:1 pixel-art) projection rig.

The rig shears the scene so that a straight-on orthographic camera looking down
+Y shows depth as a diagonal on screen::

    X' = X + a * Y
    Y' = Y
    Z' = Z + b * Y

with ``(a, b) = depth_scale * normalize(slope_run, slope_rise)``. Y is left
untouched, so depth sorting and occlusion stay correct.

Matrix layout: Geometry Nodes' ``FunctionNodeCombineMatrix`` has 16 float
inputs in column-major order. With 0-based ``column`` and ``row`` the input
index is ``column * 4 + row``; Blender labels the sockets 1-based
(``Column C Row R``). The shear puts ``a`` in socket "Column 2 Row 1"
(index 4) and ``b`` in "Column 2 Row 3" (index 6); everything else is the
identity.

Pure Python: no bpy, no mathutils.
"""

import math

SOURCE_COLLECTION = "Oblique_Source"
RIG_NAME = "Oblique Rig"
NODEGROUP_NAME = "ObliqueShear"
CAMERA_NAME = "Oblique Camera"
SUN_NAME = "Oblique Sun"
MODIFIER_NAME = "Oblique"

CALIB_FRONT = "Calib Cube Front"
CALIB_BACK = "Calib Cube Back"
CALIB_FLOOR = "Calib Floor"

CAMERA_DISTANCE = 100.0
"""How far in front of the origin (along -Y) the camera sits."""


def shear_coefficients(slope_run: float, slope_rise: float, depth_scale: float) -> tuple[float, float]:
    """Return ``(a, b) = depth_scale * normalize(slope_run, slope_rise)``.

    ``a`` is how far X moves per unit of depth (Y), ``b`` how far Z moves.

    Raises:
        ValueError: if run and rise are both 0 (no direction) or depth_scale < 0.
    """
    if depth_scale < 0:
        raise ValueError(f"depth_scale must be >= 0, got {depth_scale}")
    length = math.hypot(slope_run, slope_rise)
    if length == 0:
        raise ValueError("slope_run and slope_rise cannot both be 0")
    return depth_scale * slope_run / length, depth_scale * slope_rise / length


def shear_matrix_columns(a: float, b: float) -> list[float]:
    """Return the 16 inputs of ``FunctionNodeCombineMatrix`` for the shear.

    Column-major (index = column * 4 + row, 0-based): the identity with
    index 4 (socket "Column 2 Row 1") = ``a`` and index 6 ("Column 2 Row 3")
    = ``b``, i.e. ``X' = X + a*Y`` and ``Z' = Z + b*Y``.
    """
    values = [1.0 if column == row else 0.0 for column in range(4) for row in range(4)]
    values[1 * 4 + 0] = a
    values[1 * 4 + 2] = b
    return values


def shear_point(point: tuple[float, float, float], a: float, b: float) -> tuple[float, float, float]:
    """Apply the shear to one point: ``(x + a*y, y, z + b*y)``."""
    x, y, z = point
    return x + a * y, y, z + b * y


def ortho_scale(resolution_x: int, resolution_y: int, pixels_per_unit: int) -> float:
    """Orthographic camera scale so one Blender unit spans ``pixels_per_unit`` pixels.

    Blender's ``ortho_scale`` covers the larger side of the frame, so this is
    ``max(resolution_x, resolution_y) / pixels_per_unit``.

    Raises:
        ValueError: if any argument is not positive.
    """
    if resolution_x <= 0 or resolution_y <= 0 or pixels_per_unit <= 0:
        raise ValueError(
            "resolution and pixels_per_unit must be positive, got "
            f"{resolution_x}x{resolution_y} at {pixels_per_unit} px/unit"
        )
    return max(resolution_x, resolution_y) / pixels_per_unit


def camera_location(
    resolution_y: int, pixels_per_unit: int, height_fraction: float
) -> tuple[float, float, float]:
    """Camera position ``(0, -100, (resolution_y / pixels_per_unit) * height_fraction)``.

    The camera looks straight down +Y; ``height_fraction`` is the share of the
    frame height (in units) that it sits above z = 0.

    Raises:
        ValueError: if pixels_per_unit is not positive.
    """
    if pixels_per_unit <= 0:
        raise ValueError(f"pixels_per_unit must be positive, got {pixels_per_unit}")
    return 0.0, -CAMERA_DISTANCE, (resolution_y / pixels_per_unit) * height_fraction


def screen_offset_per_depth_unit(
    slope_run: float, slope_rise: float, depth_scale: float, pixels_per_unit: float
) -> tuple[float, float]:
    """Pixels right and up that one unit of depth moves on screen.

    For run=2, rise=1, depth=1, ppu=16 this is ``(32/sqrt(5), 16/sqrt(5))``.

    Raises:
        ValueError: as :func:`shear_coefficients`.
    """
    a, b = shear_coefficients(slope_run, slope_rise, depth_scale)
    return a * pixels_per_unit, b * pixels_per_unit
