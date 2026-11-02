"""Unit tests for core/outline.py: whole-pixel outlines on numpy masks (row 0 at the bottom)."""

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


outline = load_core_module("outline")


def single_pixel(size: int = 9) -> np.ndarray:
    mask = np.zeros((size, size), dtype=bool)
    mask[size // 2, size // 2] = True
    return mask


def alpha_of(mask: np.ndarray) -> np.ndarray:
    return np.where(mask, 255, 0).astype(np.uint8)


def test_dilate_zero_steps_is_a_copy() -> None:
    mask = single_pixel()
    out = outline.dilate(mask, 0)
    assert np.array_equal(out, mask)
    assert out is not mask


def test_dilate_is_a_diamond_without_corners_and_a_square_with() -> None:
    assert outline.dilate(single_pixel(), 1).sum() == 5
    assert outline.dilate(single_pixel(), 2).sum() == 13
    assert outline.dilate(single_pixel(), 1, corners=True).sum() == 9
    assert outline.dilate(single_pixel(), 2, corners=True).sum() == 25


def test_dilate_clips_at_the_canvas_edge() -> None:
    mask = np.zeros((4, 4), dtype=bool)
    mask[0, 0] = True
    assert outline.dilate(mask, 1).sum() == 3
    assert outline.dilate(mask, 1, corners=True).sum() == 4


def test_erode_is_the_dual_of_dilate() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:8, 2:8] = True
    assert outline.erode(mask, 1).sum() == 16
    assert outline.erode(mask, 2).sum() == 4
    assert outline.erode(mask, 3).sum() == 0
    blob = outline.dilate(single_pixel(11), 2)
    assert outline.erode(blob, 1).sum() == 5
    assert outline.erode(blob, 1, corners=True).sum() == 1


def test_negative_steps_raise() -> None:
    with pytest.raises(ValueError):
        outline.dilate(single_pixel(), -1)
    with pytest.raises(ValueError):
        outline.erode(single_pixel(), -1)


def test_outer_outline_of_one_pixel() -> None:
    alpha = alpha_of(single_pixel())
    assert outline.outer_outline(alpha, 1).sum() == 4
    assert outline.outer_outline(alpha, 1, corners=True).sum() == 8
    assert outline.outer_outline(alpha, 2).sum() == 12
    ring = outline.outer_outline(alpha, 1)
    assert not ring[4, 4]
    assert ring[5, 4] and ring[3, 4] and ring[4, 5] and ring[4, 3]


def test_outer_outline_weight_zero_is_empty() -> None:
    alpha = alpha_of(single_pixel())
    assert outline.outer_outline(alpha, 0).sum() == 0
    assert outline.outer_outline(alpha, 0, "INSIDE").sum() == 0
    assert outline.outer_outline(alpha, 0).shape == alpha.shape


def test_inside_outline_of_a_square() -> None:
    mask = np.zeros((8, 8), dtype=bool)
    mask[2:6, 2:6] = True
    inside = outline.outer_outline(alpha_of(mask), 1, "INSIDE")
    assert inside.sum() == 12
    assert not (inside & ~mask).any()
    assert outline.outer_outline(alpha_of(mask), 2, "INSIDE").sum() == 16


def test_outline_accepts_rgba_and_uses_the_alpha_threshold() -> None:
    rgba = np.zeros((9, 9, 4), dtype=np.uint8)
    rgba[4, 4] = (10, 20, 30, 128)
    rgba[0, 0] = (10, 20, 30, 127)  # below the threshold: transparent
    assert outline.outer_outline(rgba, 1).sum() == 4
    assert np.array_equal(outline.opaque_mask(rgba), rgba[..., 3] >= 128)


def test_outline_rejects_unknown_position() -> None:
    with pytest.raises(ValueError):
        outline.outer_outline(alpha_of(single_pixel()), 1, "MIDDLE")


def two_colours() -> np.ndarray:
    rgba = np.zeros((6, 8, 4), dtype=np.uint8)
    rgba[1:5, 0:4] = (255, 0, 0, 255)
    rgba[1:5, 4:8] = (0, 0, 255, 255)
    return rgba


def test_label_image() -> None:
    rgba = two_colours()
    labels = outline.label_image(rgba)
    assert labels.shape == (6, 8)
    assert labels.dtype.kind == "i"
    assert (labels[0] == -1).all() and (labels[5] == -1).all()
    assert len({labels[2, 0], labels[2, 7]}) == 2
    assert set(np.unique(labels)) == {-1, 0, 1}


def test_label_image_ignores_colour_of_transparent_pixels() -> None:
    rgba = np.zeros((2, 2, 4), dtype=np.uint8)
    rgba[0, 0] = (255, 0, 0, 0)
    rgba[0, 1] = (0, 255, 0, 10)
    rgba[1, 0] = (255, 0, 0, 255)
    labels = outline.label_image(rgba)
    assert labels.tolist() == [[-1, -1], [0, -1]]


def test_inner_lines_between_two_touching_colours_is_one_column() -> None:
    labels = outline.label_image(two_colours())
    lines = outline.inner_lines(labels, 1)
    assert lines.sum() == 4
    assert lines[1:5, 3].all()


def test_inner_lines_horizontal_boundary_marks_the_lower_side() -> None:
    labels = np.full((4, 3), -1)
    labels[0:2] = 0
    labels[2:4] = 1
    lines = outline.inner_lines(labels, 1)
    assert lines.sum() == 3
    assert lines[1].all()


def test_inner_lines_ignore_the_silhouette_edge() -> None:
    labels = np.full((5, 5), -1)
    labels[1:4, 1:4] = 0
    assert outline.inner_lines(labels, 1).sum() == 0


def test_inner_lines_weight_is_the_line_width() -> None:
    labels = outline.label_image(two_colours())
    assert outline.inner_lines(labels, 0).sum() == 0
    two = outline.inner_lines(labels, 2)
    assert two[2].tolist() == [False, False, False, True, True, False, False, False]
    three = outline.inner_lines(labels, 3)
    assert three[2].tolist() == [False, False, True, True, True, False, False, False]


def test_paint() -> None:
    mask = single_pixel(3)
    layer = outline.paint(mask, (1, 2, 3, 4))
    assert layer.shape == (3, 3, 4)
    assert layer.dtype == np.uint8
    assert layer[1, 1].tolist() == [1, 2, 3, 4]
    assert layer.sum() == 10


def test_paint_accepts_float_colours() -> None:
    layer = outline.paint(single_pixel(3), (0.0, 0.5, 1.0, 1.0))
    assert layer[1, 1].tolist() == [0, 128, 255, 255]


def test_merge_near_colors_snaps_to_the_most_frequent() -> None:
    image = np.zeros((1, 6, 4), dtype=np.uint8)
    image[0, :3] = (108, 144, 203, 255)
    image[0, 3] = (108, 145, 203, 255)  # one step off: GPU rounding noise
    image[0, 4] = (20, 30, 40, 255)
    merged = outline.merge_near_colors(image)
    assert merged.dtype == np.uint8
    assert merged[0, :4].tolist() == [[108, 144, 203, 255]] * 4
    assert merged[0, 4].tolist() == [20, 30, 40, 255]
    assert merged[0, 5].tolist() == [0, 0, 0, 0], "transparent pixels are left alone"
    assert image[0, 3].tolist() == [108, 145, 203, 255], "the input is not modified"


def test_merge_near_colors_respects_the_tolerance() -> None:
    image = np.zeros((1, 3, 4), dtype=np.uint8)
    image[0, :2] = (100, 100, 100, 255)
    image[0, 2] = (102, 100, 100, 255)
    assert outline.merge_near_colors(image)[0, 2].tolist() == [102, 100, 100, 255], "two steps apart"
    assert outline.merge_near_colors(image, tolerance=2)[0, 2].tolist() == [100, 100, 100, 255]
    assert outline.merge_near_colors(image, tolerance=0).tolist() == image.tolist()


def test_merge_near_colors_then_label_gives_one_label_per_material() -> None:
    image = np.zeros((2, 4, 4), dtype=np.uint8)
    image[:, :2] = (200, 50, 50, 255)
    image[1, 1] = (201, 50, 49, 255)
    image[:, 2:] = (50, 200, 50, 255)
    image[0, 3] = (50, 199, 50, 255)
    labels = outline.label_image(outline.merge_near_colors(image))
    assert labels.tolist() == [[1, 1, 0, 0], [1, 1, 0, 0]]


def test_merge_near_colors_of_an_empty_image() -> None:
    image = np.zeros((3, 3, 4), dtype=np.uint8)
    assert np.array_equal(outline.merge_near_colors(image), image)
