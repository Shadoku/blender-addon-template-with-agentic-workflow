"""Unit tests for core/compose.py: straight-alpha over, layer stacks and sprite sheets."""

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


compose = load_core_module("compose")


def solid(color: tuple[int, int, int, int], height: int = 2, width: int = 3) -> np.ndarray:
    out = np.zeros((height, width, 4), dtype=np.uint8)
    out[...] = color
    return out


def test_opaque_top_wins() -> None:
    out = compose.over(solid((0, 0, 255, 255)), solid((255, 0, 0, 255)))
    assert out.dtype == np.uint8
    assert out.shape == (2, 3, 4)
    assert (out == (255, 0, 0, 255)).all()


def test_transparent_top_keeps_bottom() -> None:
    bottom = solid((10, 20, 30, 77))
    assert np.array_equal(compose.over(bottom, solid((255, 255, 255, 0))), bottom)


def test_both_transparent_is_zero() -> None:
    out = compose.over(solid((10, 20, 30, 0)), solid((40, 50, 60, 0)))
    assert (out == 0).all()


def test_half_alpha_over_opaque() -> None:
    out = compose.over(solid((0, 0, 255, 255)), solid((255, 0, 0, 128)))
    assert out[0, 0].tolist() == [128, 0, 127, 255]


def test_half_alpha_over_transparent_keeps_colour() -> None:
    out = compose.over(solid((0, 0, 0, 0)), solid((200, 100, 50, 128)))
    assert out[0, 0].tolist() == [200, 100, 50, 128]


def test_half_over_half() -> None:
    out = compose.over(solid((0, 0, 255, 128)), solid((255, 0, 0, 128)))
    a_t = a_b = 128 / 255
    a = a_t + a_b * (1 - a_t)
    expected_r = round(255 * a_t / a)
    expected_b = round(255 * a_b * (1 - a_t) / a)
    assert out[0, 0].tolist() == [expected_r, 0, expected_b, round(a * 255)]


def test_over_does_not_modify_inputs() -> None:
    bottom, top = solid((0, 0, 255, 255)), solid((255, 0, 0, 128))
    before = bottom.copy(), top.copy()
    compose.over(bottom, top)
    assert np.array_equal(bottom, before[0]) and np.array_equal(top, before[1])


def test_over_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        compose.over(solid((0, 0, 0, 255)), solid((0, 0, 0, 255), width=4))


def test_stack_is_over_left_to_right_and_skips_none() -> None:
    a = solid((0, 0, 255, 255))
    b = solid((255, 0, 0, 128))
    c = np.zeros_like(a)
    c[0, 0] = (0, 255, 0, 255)
    out = compose.stack([a, None, b, c])
    assert np.array_equal(out[1, 1], compose.over(a, b)[1, 1])
    assert out[0, 0].tolist() == [0, 255, 0, 255]
    assert np.array_equal(compose.stack([a]), a)


def test_stack_rejects_empty() -> None:
    with pytest.raises(ValueError):
        compose.stack([])
    with pytest.raises(ValueError):
        compose.stack([None])


def frame(value: int, height: int = 2, width: int = 3) -> np.ndarray:
    return solid((value, value, value, 255), height, width)


def test_sheet_is_one_row_by_default() -> None:
    out = compose.sheet([frame(1), frame(2), frame(3)])
    assert out.shape == (2, 9, 4)
    assert out[0, 0, 0] == 1 and out[1, 3, 0] == 2 and out[0, 8, 0] == 3


def test_sheet_wraps_rows_top_down() -> None:
    out = compose.sheet([frame(1), frame(2), frame(3)], columns=2)
    assert out.shape == (4, 6, 4)
    # Row 0 of the array is the bottom: the first sheet row sits on top.
    assert out[2, 0, 0] == 1 and out[3, 5, 0] == 2
    assert out[0, 0, 0] == 3
    assert (out[0:2, 3:6] == 0).all()


def test_sheet_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        compose.sheet([])
    with pytest.raises(ValueError):
        compose.sheet([frame(1), frame(2, width=4)])
    with pytest.raises(ValueError):
        compose.sheet([frame(1)], columns=0)


def test_rgba8() -> None:
    assert compose.rgba8((0.0, 0.5, 1.0, 1.0)) == (0, 128, 255, 255)
    assert compose.rgba8((0, 128, 255, 255)) == (0, 128, 255, 255)
    assert compose.rgba8((1.5, -0.2, 0.0, 1.0)) == (255, 0, 0, 255)
    assert compose.rgba8((0.2, 0.4, 0.6)) == (51, 102, 153, 255)
