"""Unit tests for core/overlap.py: the depth-sort warning (3D interpenetration of bounding boxes)."""

import importlib.util
import sys
from pathlib import Path

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


overlap = load_core_module("overlap")


def box(name: str, lo, hi):
    return (name, tuple(float(v) for v in lo), tuple(float(v) for v in hi))


def test_interpenetrating_boxes_are_reported() -> None:
    items = [box("Front", (0, 0, 0), (1, 1, 1)), box("Back", (0, 0.5, 0.5), (1, 1.5, 1.5))]
    assert overlap.overlapping_pairs(items) == [("Front", "Back")]


def test_box_standing_on_a_floor_is_not_reported() -> None:
    """The calibration case: cubes resting on a flat floor touch it in z but do not enter it."""
    items = [
        box("Cube Front", (-0.5, 0, 0), (0.5, 1, 1)),
        box("Cube Back", (-0.5, 3, 0), (0.5, 4, 1)),
        box("Floor", (-3, 0, 0), (3, 5, 0)),
    ]
    assert overlap.overlapping_pairs(items) == []


def test_box_sunk_into_a_thick_floor_is_reported() -> None:
    items = [box("Cube", (0, 0, -0.25), (1, 1, 1)), box("Slab", (-3, 0, -1), (3, 5, 0))]
    assert overlap.overlapping_pairs(items) == [("Cube", "Slab")]


def test_one_separated_axis_is_enough() -> None:
    base = box("A", (0, 0, 0), (1, 1, 1))
    assert overlap.overlapping_pairs([base, box("X", (2, 0, 0), (3, 1, 1))]) == []
    assert overlap.overlapping_pairs([base, box("Y", (0, 2, 0), (1, 3, 1))]) == [], "one behind the other"
    assert overlap.overlapping_pairs([base, box("Z", (0, 0, 2), (1, 1, 3))]) == []


def test_touching_faces_do_not_count() -> None:
    base = box("A", (0, 0, 0), (1, 1, 1))
    for other in (
        box("X", (1, 0, 0), (2, 1, 1)),
        box("Y", (0, 1, 0), (1, 2, 1)),
        box("Z", (0, 0, 1), (1, 1, 2)),
        box("Tiny", (0, 0, 1 - 1e-12), (1, 1, 2)),
    ):
        assert overlap.overlapping_pairs([base, other]) == [], other[0]


def test_containment_is_reported() -> None:
    items = [box("Outer", (0, 0, 0), (4, 4, 4)), box("Inner", (1, 1, 1), (2, 2, 2))]
    assert overlap.overlapping_pairs(items) == [("Outer", "Inner")]


def test_pairs_keep_input_order() -> None:
    items = [
        box("C", (0, 0, 0), (2, 2, 2)),
        box("A", (1, 1, 1), (3, 3, 3)),
        box("B", (1.5, 1.5, 1.5), (2.5, 2.5, 2.5)),
    ]
    assert overlap.overlapping_pairs(items) == [("C", "A"), ("C", "B"), ("A", "B")]


def test_empty_and_single() -> None:
    assert overlap.overlapping_pairs([]) == []
    assert overlap.overlapping_pairs([box("A", (0, 0, 0), (1, 1, 1))]) == []


def test_format_warnings() -> None:
    assert overlap.format_warnings([]) == ""
    text = overlap.format_warnings([("A", "B"), ("C", "D")])
    assert text.count(";") == 1
    assert "A" in text and "B" in text and "D" in text
