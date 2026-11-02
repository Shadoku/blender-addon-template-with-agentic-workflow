"""Unit tests for core/guides.py: Bresenham lines and the floor grid overlay."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
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


guides = load_core_module("guides")

COLOR = (0, 200, 255, 150)


def lit(canvas: np.ndarray) -> set[tuple[int, int]]:
    """(x, y) of every pixel with non-zero alpha."""
    ys, xs = np.nonzero(canvas[..., 3])
    return set(zip(xs.tolist(), ys.tolist(), strict=True))


def blank(width: int = 16, height: int = 12) -> np.ndarray:
    return np.zeros((height, width, 4), dtype=np.uint8)


@pytest.mark.parametrize(
    ("x0", "y0", "x1", "y1"),
    [(1, 1, 10, 4), (10, 4, 1, 1), (2, 9, 5, 0), (3, 3, 3, 8), (0, 5, 15, 5), (4, 4, 4, 4), (0, 0, 11, 11)],
)
def test_line_hits_both_endpoints_and_is_connected(x0: int, y0: int, x1: int, y1: int) -> None:
    canvas = blank()
    guides.line(canvas, x0, y0, x1, y1, COLOR)
    pixels = lit(canvas)
    assert (x0, y0) in pixels and (x1, y1) in pixels
    assert len(pixels) == max(abs(x1 - x0), abs(y1 - y0)) + 1
    assert canvas[y0, x0].tolist() == list(COLOR)


def test_line_is_the_classic_bresenham_staircase() -> None:
    canvas = blank()
    guides.line(canvas, 0, 0, 4, 2, COLOR)
    assert lit(canvas) == {(0, 0), (1, 0), (2, 1), (3, 1), (4, 2)} or lit(canvas) == {
        (0, 0),
        (1, 1),
        (2, 1),
        (3, 2),
        (4, 2),
    }


def test_two_to_one_line_steps_two_right_one_up() -> None:
    canvas = blank(32, 12)
    guides.line(canvas, 0, 0, 16, 8, COLOR)
    pixels = lit(canvas)
    assert len(pixels) == 17
    rows = {}
    for x, y in pixels:
        rows.setdefault(y, []).append(x)
    assert all(len(xs) == 2 for y, xs in rows.items() if 0 < y < 8)


def test_line_clips_to_the_canvas() -> None:
    canvas = blank(8, 8)
    guides.line(canvas, -5, 2, 20, 2, COLOR)
    assert lit(canvas) == {(x, 2) for x in range(8)}
    guides.line(canvas, -10, -10, -1, -1, COLOR)
    assert len(lit(canvas)) == 8


def test_grid_depth_lines_are_rows_at_b_px_per_unit() -> None:
    # 64x64 frame, camera at the centre: origin at (32, 32); a = 16, b = 8 px per unit of depth.
    layer = guides.grid_layer(64, 64, 16.0, 8.0, 16, 0.0, 0.0, 1, 2, COLOR)
    assert layer.shape == (64, 64, 4)
    assert layer.dtype == np.uint8
    for k in range(3):
        row = 32 + 8 * k
        start = 32 - 2 * 16 + k * 16
        end = min(63, 32 + 2 * 16 + k * 16)
        assert layer[row, start : end + 1, 3].all(), k
    assert not layer[31, :, 3].any()
    assert not layer[32 + 8 * 2 + 1 :, :, 3].any()


def test_grid_ground_line_has_full_alpha() -> None:
    layer = guides.grid_layer(64, 64, 16.0, 8.0, 16, 0.0, 0.0, 1, 2, COLOR)
    assert layer[32, 0:64, 3].tolist() == [255] * 64
    assert layer[32, 10, :3].tolist() == list(COLOR[:3])
    assert layer[40, 20, 3] == COLOR[3]


def test_grid_x_lines_run_along_the_depth_direction() -> None:
    layer = guides.grid_layer(64, 64, 16.0, 8.0, 16, 0.0, 0.0, 1, 2, COLOR)
    # x = 0 runs from (32, 32) at depth 0 to (64, 48) at depth 2: (48, 40) is on it at depth 1.
    assert layer[40, 48, 3] > 0
    assert layer[36, 40, 3] > 0
    # x = -1 starts at (16, 32) and passes (24, 36).
    assert layer[36, 24, 3] > 0


def test_grid_respects_camera_offset() -> None:
    layer = guides.grid_layer(64, 64, 16.0, 8.0, 16, 8.0, -4.0, 1, 1, COLOR)
    # origin = (32 - 8, 32 + 4) = (24, 36)
    assert layer[36, :, 3].tolist().count(255) > 0
    assert layer[36, 8 : 40 + 1, 3].tolist() == [255] * 33
    assert layer[44, 24 + 16, 3] > 0


def test_grid_step_skips_lines() -> None:
    layer = guides.grid_layer(128, 128, 8.0, 4.0, 8, 0.0, 0.0, 2, 4, COLOR)
    # Depth lines at k = 0, 2, 4 only (rows 64 + 4k); other rows hold just the five x lines.
    full_rows = [y for y in range(128) if (layer[y, :, 3] > 0).sum() > 20]
    assert full_rows == [64, 72, 80]


def test_grid_rejects_bad_steps() -> None:
    with pytest.raises(ValueError):
        guides.grid_layer(64, 64, 16.0, 8.0, 16, 0.0, 0.0, 0, 2, COLOR)
    with pytest.raises(ValueError):
        guides.grid_layer(64, 64, 16.0, 8.0, 16, 0.0, 0.0, 1, -1, COLOR)


def test_grid_accepts_float_colour() -> None:
    layer = guides.grid_layer(32, 32, 4.0, 2.0, 4, 0.0, 0.0, 1, 1, (0.0, 0.8, 1.0, 0.6))
    assert layer[16, 16].tolist() == [0, 204, 255, 255]
    assert layer[18, 16 + 4 + 4, 3] == 153
