# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh data for simple primitives, ready for ``mesh.from_pydata(verts, [], faces)``.

Building meshes from data instead of ``bpy.ops.mesh.primitive_*_add`` works in
background mode and needs no operator context. Faces are quads wound
counter-clockwise when seen from outside, so normals point outward.
"""

Vec3 = tuple[float, float, float]


def cube(size: float = 1.0, center: Vec3 = (0.0, 0.0, 0.0)) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """Axis-aligned cube with edge length ``size`` centred on ``center``.

    Returns 8 vertices and 6 quad faces with outward normals. Vertex ``i`` has
    +X when bit 0 is set, +Y for bit 1 and +Z for bit 2.

    Raises:
        ValueError: if size is not positive.
    """
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    h = size / 2.0
    cx, cy, cz = center
    verts = [
        (cx + (h if i & 1 else -h), cy + (h if i & 2 else -h), cz + (h if i & 4 else -h)) for i in range(8)
    ]
    faces: list[tuple[int, ...]] = [
        (0, 2, 3, 1),  # -Z bottom
        (4, 5, 7, 6),  # +Z top
        (0, 1, 5, 4),  # -Y front
        (2, 6, 7, 3),  # +Y back
        (0, 4, 6, 2),  # -X left
        (1, 3, 7, 5),  # +X right
    ]
    return verts, faces


def plane(
    size_x: float, size_y: float, center: Vec3 = (0.0, 0.0, 0.0)
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """Rectangle in the XY plane, ``size_x`` by ``size_y``, centred on ``center``.

    Returns 4 vertices and 1 quad face whose normal points +Z.

    Raises:
        ValueError: if either size is not positive.
    """
    if size_x <= 0 or size_y <= 0:
        raise ValueError(f"sizes must be positive, got {size_x} x {size_y}")
    hx, hy = size_x / 2.0, size_y / 2.0
    cx, cy, cz = center
    verts = [
        (cx - hx, cy - hy, cz),
        (cx + hx, cy - hy, cz),
        (cx + hx, cy + hy, cz),
        (cx - hx, cy + hy, cz),
    ]
    return verts, [(0, 1, 2, 3)]
