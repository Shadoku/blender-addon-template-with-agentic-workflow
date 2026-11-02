"""Unit tests for core/primitives.py: vertex/face data fed to mesh.from_pydata."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_core_module(name: str):
    """Import src/<id>/core/<name>.py directly (core/ must never import bpy)."""
    [addon_dir] = [p.parent for p in (ROOT / "src").glob("*/blender_manifest.toml")]
    path = addon_dir / "core" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"core_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


primitives = load_core_module("primitives")


def newell_normal(verts, face) -> tuple[float, float, float]:
    """Unnormalised polygon normal; its direction follows the winding."""
    nx = ny = nz = 0.0
    for i, current in enumerate(face):
        x0, y0, z0 = verts[current]
        x1, y1, z1 = verts[face[(i + 1) % len(face)]]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return nx, ny, nz


def bounds(verts):
    return [(min(v[i] for v in verts), max(v[i] for v in verts)) for i in range(3)]


def test_cube_counts_and_bounds() -> None:
    verts, faces = primitives.cube(1.0, (0.0, 3.0, 0.5))
    assert len(verts) == 8
    assert len(set(verts)) == 8
    assert len(faces) == 6
    assert all(len(f) == 4 for f in faces)
    assert bounds(verts) == pytest.approx([(-0.5, 0.5), (2.5, 3.5), (0.0, 1.0)])


def test_cube_default_is_unit_at_origin() -> None:
    verts, _ = primitives.cube()
    assert bounds(verts) == pytest.approx([(-0.5, 0.5)] * 3)


def test_cube_faces_point_outward() -> None:
    center = (1.0, -2.0, 0.5)
    verts, faces = primitives.cube(2.0, center)
    for face in faces:
        normal = newell_normal(verts, face)
        face_center = [sum(verts[i][k] for i in face) / 4 for k in range(3)]
        outward = [face_center[k] - center[k] for k in range(3)]
        assert sum(n * o for n, o in zip(normal, outward, strict=True)) > 0, face


def test_cube_is_closed_and_consistently_wound() -> None:
    _, faces = primitives.cube()
    edges = [(f[i], f[(i + 1) % 4]) for f in faces for i in range(4)]
    assert len(set(edges)) == 24  # no directed edge twice
    assert {(b, a) for a, b in edges} == set(edges)  # every edge has its opposite
    assert sorted({i for f in faces for i in f}) == list(range(8))


def test_plane_counts_and_extents() -> None:
    verts, faces = primitives.plane(6.0, 5.0, (0.0, 2.0, 0.0))
    assert len(verts) == 4
    assert faces == [(0, 1, 2, 3)]
    assert bounds(verts) == pytest.approx([(-3.0, 3.0), (-0.5, 4.5), (0.0, 0.0)])


def test_plane_faces_up() -> None:
    verts, faces = primitives.plane(2.0, 1.0)
    nx, ny, nz = newell_normal(verts, faces[0])
    assert nz > 0
    assert (nx, ny) == pytest.approx((0.0, 0.0))


@pytest.mark.parametrize("size", [0.0, -1.0])
def test_non_positive_sizes_rejected(size: float) -> None:
    with pytest.raises(ValueError):
        primitives.cube(size)
    with pytest.raises(ValueError):
        primitives.plane(size, 1.0)
    with pytest.raises(ValueError):
        primitives.plane(1.0, size)
