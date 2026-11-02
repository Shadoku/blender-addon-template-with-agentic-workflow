"""Unit tests for core/oblique.py: the shear maths behind the oblique rig.

Imported by file path so they run under plain Python with no Blender and no
bl_ext package machinery."""

import importlib.util
import math
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


oblique = load_core_module("oblique")

SQRT5 = math.sqrt(5.0)


def test_names_are_strings() -> None:
    assert oblique.SOURCE_COLLECTION == "Oblique_Source"
    assert oblique.RIG_NAME == "Oblique Rig"
    assert oblique.NODEGROUP_NAME == "ObliqueShear"
    assert oblique.CAMERA_NAME == "Oblique Camera"
    assert oblique.SUN_NAME == "Oblique Sun"
    assert oblique.MODIFIER_NAME == "Oblique"
    calib = {oblique.CALIB_FRONT, oblique.CALIB_BACK, oblique.CALIB_FLOOR}
    assert len(calib) == 3
    assert all(isinstance(n, str) and n for n in calib)


def test_two_to_one_direction_scaled_by_depth() -> None:
    a, b = oblique.shear_coefficients(2.0, 1.0, 0.6)
    assert a == pytest.approx(0.6 * 2.0 / SQRT5)
    assert b == pytest.approx(0.6 * 1.0 / SQRT5)


def test_cavalier_depth_has_unit_length() -> None:
    a, b = oblique.shear_coefficients(2.0, 1.0, 1.0)
    assert math.hypot(a, b) == pytest.approx(1.0)


def test_only_direction_of_slope_matters() -> None:
    assert oblique.shear_coefficients(4.0, 2.0, 0.5) == pytest.approx(
        oblique.shear_coefficients(2.0, 1.0, 0.5)
    )


def test_zero_depth_is_no_shear() -> None:
    assert oblique.shear_coefficients(2.0, 1.0, 0.0) == pytest.approx((0.0, 0.0))


@pytest.mark.parametrize(("run", "rise", "depth"), [(0.0, 0.0, 1.0), (2.0, 1.0, -0.1)])
def test_shear_coefficients_rejects_bad_input(run: float, rise: float, depth: float) -> None:
    with pytest.raises(ValueError):
        oblique.shear_coefficients(run, rise, depth)


def test_matrix_layout_is_column_major_with_shear_in_column_two() -> None:
    cols = oblique.shear_matrix_columns(0.25, 0.75)
    assert len(cols) == 16
    assert cols[4] == 0.25  # Column 2 Row 1 -> X' += a*Y
    assert cols[6] == 0.75  # Column 2 Row 3 -> Z' += b*Y
    for index, value in enumerate(cols):
        if index in (4, 6):
            continue
        column, row = divmod(index, 4)
        assert value == (1.0 if column == row else 0.0), index


def test_matrix_and_shear_point_agree() -> None:
    a, b = 0.3, -0.2
    cols = oblique.shear_matrix_columns(a, b)
    point = (1.5, 2.0, -0.5)
    homogeneous = (*point, 1.0)
    # M[row][col] = cols[col*4 + row]
    result = tuple(sum(cols[c * 4 + r] * homogeneous[c] for c in range(4)) for r in range(3))
    assert result == pytest.approx(oblique.shear_point(point, a, b))


def test_shear_point_moves_depth_and_keeps_y() -> None:
    a, b = oblique.shear_coefficients(2.0, 1.0, 0.6)
    x, y, z = oblique.shear_point((0.0, 3.0, 0.0), a, b)
    assert (x, y, z) == pytest.approx((3 * a, 3.0, 3 * b))


def test_shear_point_leaves_depth_zero_alone() -> None:
    assert oblique.shear_point((1.0, 0.0, 2.0), 0.5, 0.5) == pytest.approx((1.0, 0.0, 2.0))


def test_ortho_scale_uses_the_larger_side() -> None:
    assert oblique.ortho_scale(320, 200, 16) == 20
    assert oblique.ortho_scale(200, 320, 16) == 20
    assert oblique.ortho_scale(64, 64, 32) == 2


@pytest.mark.parametrize(("rx", "ry", "ppu"), [(0, 200, 16), (320, -1, 16), (320, 200, 0)])
def test_ortho_scale_rejects_non_positive(rx: int, ry: int, ppu: int) -> None:
    with pytest.raises(ValueError):
        oblique.ortho_scale(rx, ry, ppu)


def test_camera_location() -> None:
    x, y, z = oblique.camera_location(200, 16, 0.35)
    assert (x, y) == (0.0, -100.0)
    assert z == pytest.approx(12.5 * 0.35)


def test_camera_location_rejects_zero_ppu() -> None:
    with pytest.raises(ValueError):
        oblique.camera_location(200, 0, 0.35)


def test_screen_offset_per_depth_unit() -> None:
    dx, dy = oblique.screen_offset_per_depth_unit(2.0, 1.0, 1.0, 16)
    assert dx == pytest.approx(32 / SQRT5)
    assert dy == pytest.approx(16 / SQRT5)


def test_screen_offset_scales_with_depth() -> None:
    dx, dy = oblique.screen_offset_per_depth_unit(2.0, 1.0, 0.5, 16)
    assert (dx, dy) == pytest.approx((16 / SQRT5, 8 / SQRT5))


def test_bounds_of_points() -> None:
    lo, hi = oblique.bounds([(1.0, -2.0, 3.0), (-1.0, 4.0, 0.5), (0.0, 0.0, 9.0)])
    assert lo == pytest.approx((-1.0, -2.0, 0.5))
    assert hi == pytest.approx((1.0, 4.0, 9.0))


def test_bounds_rejects_empty() -> None:
    with pytest.raises(ValueError):
        oblique.bounds([])


def test_placement_offset_puts_front_edge_at_zero_and_origin_on_floor() -> None:
    # Object spans y -2..1 and z 1..4, origin at z = 2.5: pull y forward by 2, drop origin by 2.5.
    offset = oblique.placement_offset(bbox_min=(5.0, -2.0, 1.0), origin_z=2.5)
    assert offset == pytest.approx((0.0, 2.0, -2.5))


def test_placement_offset_can_ground_by_bottom() -> None:
    offset = oblique.placement_offset(bbox_min=(5.0, 3.0, -1.5), origin_z=0.0, ground_by_bottom=True)
    assert offset == pytest.approx((0.0, -3.0, 1.5))
