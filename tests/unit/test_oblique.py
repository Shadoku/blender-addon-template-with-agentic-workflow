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


# --- 0.2: pixel-exact depth, camera snapping, projection and fit ------------------------


def make_params(**overrides) -> "oblique.RigParams":
    """RigParams with the add-on's defaults, overridden per test."""
    values = {
        "pixels_per_unit": 16,
        "resolution_x": 320,
        "resolution_y": 200,
        "slope_run": 2.0,
        "slope_rise": 1.0,
        "depth_scale": 0.6,
        "pixel_exact": True,
        "depth_px_right": 16,
        "depth_px_up": 8,
        "camera_height_fraction": 0.35,
        "camera_offset_x": 0.0,
        "direction": 0.0,
        "auto_seat": True,
        "view_mode": "SHEARED",
    }
    values.update(overrides)
    return oblique.RigParams(**values)


def test_rig_params_defaults_match_the_settings_defaults() -> None:
    assert oblique.RigParams() == make_params()


def test_rig_params_is_frozen() -> None:
    params = make_params()
    with pytest.raises(AttributeError):
        params.pixels_per_unit = 8  # type: ignore[misc]


def test_pixel_exact_shear_is_whole_pixels_per_unit() -> None:
    a, b = make_params().shear()
    assert (a, b) == (1.0, 0.5)
    assert (a * 16, b * 16) == (16.0, 8.0)


def test_float_shear_uses_the_slope_controls() -> None:
    params = make_params(pixel_exact=False)
    assert params.shear() == pytest.approx(oblique.shear_coefficients(2.0, 1.0, 0.6))


def test_pixel_exact_shear_rejects_zero_steps() -> None:
    with pytest.raises(ValueError):
        make_params(depth_px_right=0, depth_px_up=0).shear()


def test_pixel_exact_shear_allows_one_zero_step() -> None:
    assert make_params(depth_px_right=0, depth_px_up=4).shear() == (0.0, 0.25)


@pytest.mark.parametrize(("right", "up", "ppu"), [(16, 8, 16), (7, 3, 16), (1, 0, 8), (0, 5, 32), (3, 5, 7)])
def test_modifier_inputs_reproduce_shear_through_the_node_group(right: int, up: int, ppu: int) -> None:
    params = make_params(depth_px_right=right, depth_px_up=up, pixels_per_unit=ppu)
    run, rise, depth = params.modifier_inputs()
    assert (run, rise) == (float(right), float(up))
    # The node group computes normalize(run, rise) * depth.
    a, b = oblique.shear_coefficients(run, rise, depth)
    expected = params.shear()
    assert abs(a - expected[0]) < 1e-9
    assert abs(b - expected[1]) < 1e-9


def test_modifier_inputs_in_float_mode_are_the_slope_controls() -> None:
    assert make_params(pixel_exact=False).modifier_inputs() == (2.0, 1.0, 0.6)


def test_pixel_step_to_slope() -> None:
    run, rise, depth = oblique.pixel_step_to_slope(16, 8, 16)
    assert (run, rise) == (16.0, 8.0)
    assert depth == pytest.approx(math.hypot(16, 8) / 16)
    assert oblique.shear_coefficients(run, rise, depth) == pytest.approx((1.0, 0.5))


@pytest.mark.parametrize(("right", "up", "ppu"), [(0, 0, 16), (16, 8, 0), (16, 8, -1)])
def test_pixel_step_to_slope_rejects_bad_input(right: int, up: int, ppu: int) -> None:
    with pytest.raises(ValueError):
        oblique.pixel_step_to_slope(right, up, ppu)


def test_effective_resolution_rounds_up_to_even_when_pixel_exact() -> None:
    assert make_params(resolution_x=321, resolution_y=199).effective_resolution() == (322, 200)
    assert make_params(resolution_x=320, resolution_y=200).effective_resolution() == (320, 200)
    assert make_params(resolution_x=321, resolution_y=199, pixel_exact=False).effective_resolution() == (
        321,
        199,
    )


@pytest.mark.parametrize(
    ("value", "ppu", "expected"),
    [(0.0, 16, 0.0), (1.0 / 16, 16, 1.0 / 16), (0.03, 16, 0.0), (0.04, 16, 1.0 / 16), (4.375, 16, 4.375)],
)
def test_snap_to_pixel(value: float, ppu: int, expected: float) -> None:
    assert oblique.snap_to_pixel(value, ppu) == pytest.approx(expected)


def test_snap_to_pixel_rounds_half_away_from_zero() -> None:
    assert oblique.snap_to_pixel(0.5 / 16, 16) == pytest.approx(1 / 16)
    assert oblique.snap_to_pixel(-0.5 / 16, 16) == pytest.approx(-1 / 16)
    assert oblique.snap_to_pixel(1.5, 1) == 2.0
    assert oblique.snap_to_pixel(-2.5, 1) == -3.0


def test_snap_to_pixel_rejects_zero_ppu() -> None:
    with pytest.raises(ValueError):
        oblique.snap_to_pixel(1.0, 0)


def test_camera_is_snapped_to_whole_pixels_when_pixel_exact() -> None:
    # 200 / 16 * 0.35 = 4.375 = 70 px (already whole); 0.33 -> 4.125 = 66 px.
    params = make_params(camera_height_fraction=0.333, camera_offset_x=0.51)
    x, y, z = params.camera()
    assert y == -oblique.CAMERA_DISTANCE
    assert z * 16 == pytest.approx(round(200 / 16 * 0.333 * 16))
    assert (z * 16) == pytest.approx(round(z * 16), abs=1e-9)
    assert (x * 16) == pytest.approx(round(x * 16), abs=1e-9)
    assert x == pytest.approx(8 / 16)


def test_camera_uses_effective_resolution() -> None:
    x, _, z = make_params(resolution_y=199, camera_height_fraction=0.5).camera()
    assert z == pytest.approx(200 / 16 * 0.5)
    assert x == 0.0


def test_camera_is_not_snapped_in_float_mode() -> None:
    x, y, z = make_params(pixel_exact=False, camera_height_fraction=0.333, camera_offset_x=0.51).camera()
    assert (x, y) == (0.51, -oblique.CAMERA_DISTANCE)
    assert z == pytest.approx(200 / 16 * 0.333)


def test_project_to_pixels_origin_is_frame_centre_minus_camera() -> None:
    px, py = oblique.project_to_pixels((0.0, 0.0, 0.0), 1.0, 0.5, 16, 0.0, 0.0, 64, 48)
    assert (px, py) == (32.0, 24.0)
    px, py = oblique.project_to_pixels((0.0, 0.0, 0.0), 1.0, 0.5, 16, 0.5, 1.0, 64, 48)
    assert (px, py) == (24.0, 8.0)


def test_project_to_pixels_shears_depth() -> None:
    # One unit right, two deep, one up: x' = 1 + 2*1, z' = 1 + 2*0.5.
    px, py = oblique.project_to_pixels((1.0, 2.0, 1.0), 1.0, 0.5, 16, 0.0, 0.0, 64, 48)
    assert (px, py) == (32.0 + 3 * 16, 24.0 + 2 * 16)


def test_screen_rect() -> None:
    points = [(0.0, 0.0, 0.0), (1.0, 2.0, 1.0), (-1.0, 0.0, 0.5)]
    rect = oblique.screen_rect(points, 1.0, 0.5, 16, 0.0, 0.0, 64, 48)
    assert rect == pytest.approx((16.0, 24.0, 80.0, 56.0))


def test_screen_rect_rejects_empty() -> None:
    with pytest.raises(ValueError):
        oblique.screen_rect([], 1.0, 0.5, 16, 0.0, 0.0, 64, 48)


def test_footprint_px() -> None:
    assert oblique.footprint_px((-0.5, 0.0, 0.0), (2.0, 3.0, 2.5), 16) == (40, 40)
    assert oblique.footprint_px((0.0, 0.0, 0.0), (1.01, 0.0, 0.5), 16) == (17, 8)


def test_footprint_px_ignores_float_noise() -> None:
    assert oblique.footprint_px((0.1, 0.0, 0.0), (0.1 + 0.2 + 1.2, 0.0, 0.3), 10) == (14, 3)


def test_fit_frame_on_a_known_box() -> None:
    fit = oblique.fit_frame((-0.5, 0.0, 0.0), (2.0, 3.0, 2.5), 16, 4)
    assert isinstance(fit, oblique.FitResult)
    assert (fit.resolution_x, fit.resolution_y) == (48, 48)
    assert fit.camera_offset_x == pytest.approx(0.75)
    # camera z = centre z = 1.25; frame height = 48 / 16 = 3 units.
    assert fit.camera_height_fraction == pytest.approx(1.25 / 3.0)


def test_fit_frame_round_trips_through_rig_params() -> None:
    bmin, bmax = (-0.37, 0.0, 0.02), (1.91, 4.0, 3.13)
    fit = oblique.fit_frame(bmin, bmax, 16, 3)
    assert fit.resolution_x % 2 == 0 and fit.resolution_y % 2 == 0
    params = make_params(
        resolution_x=fit.resolution_x,
        resolution_y=fit.resolution_y,
        camera_offset_x=fit.camera_offset_x,
        camera_height_fraction=fit.camera_height_fraction,
    )
    x, _, z = params.camera()
    assert x * 16 == pytest.approx(round(x * 16), abs=1e-9)
    assert z * 16 == pytest.approx(round(z * 16), abs=1e-9)
    # The whole box is inside the frame with at least the padding around it.
    left, bottom, right, top = oblique.screen_rect(
        [bmin, bmax], 0.0, 0.0, 16, x, z, fit.resolution_x, fit.resolution_y
    )
    assert left >= 3 - 1e-9 and bottom >= 3 - 1e-9
    assert right <= fit.resolution_x - 3 + 1e-9 and top <= fit.resolution_y - 3 + 1e-9


def test_fit_frame_odd_extent_without_even() -> None:
    fit = oblique.fit_frame((0.0, 0.0, 0.0), (3.0, 0.0, 1.0), 1, 1, even=False)
    assert (fit.resolution_x, fit.resolution_y) == (5, 3)
    fit = oblique.fit_frame((0.0, 0.0, 0.0), (3.0, 0.0, 1.0), 1, 1)
    assert (fit.resolution_x, fit.resolution_y) == (6, 4)


def test_fit_frame_never_clips_off_grid_content() -> None:
    # Box spans 0.5..2.5 px: two pixels wide but straddling three pixel columns.
    fit = oblique.fit_frame((0.5, 0.0, 0.5), (2.5, 0.0, 2.5), 1, 0)
    x, z = fit.camera_offset_x, fit.camera_height_fraction * fit.resolution_y
    assert x - fit.resolution_x / 2 <= 0.5 and x + fit.resolution_x / 2 >= 2.5
    assert z - fit.resolution_y / 2 <= 0.5 and z + fit.resolution_y / 2 >= 2.5
    assert x == round(x) and z == pytest.approx(round(z))


def test_fit_frame_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        oblique.fit_frame((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0, 4)
    with pytest.raises(ValueError):
        oblique.fit_frame((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 16, -1)
