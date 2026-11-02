"""Unit tests for core/overlap.py: the depth-sort warning."""

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


def test_interleaved_depth_with_overlapping_rects_is_reported() -> None:
    items = [
        ("Front", (0.0, 0.0, 16.0, 16.0), (0.0, 1.0)),
        ("Back", (8.0, 4.0, 24.0, 20.0), (0.5, 1.5)),
    ]
    assert overlap.overlapping_pairs(items) == [("Front", "Back")]


def test_separate_depth_is_not_reported() -> None:
    items = [
        ("Front", (0.0, 0.0, 16.0, 16.0), (0.0, 1.0)),
        ("Back", (8.0, 4.0, 24.0, 20.0), (2.0, 3.0)),
    ]
    assert overlap.overlapping_pairs(items) == []


def test_touching_is_not_overlapping() -> None:
    items = [
        ("A", (0.0, 0.0, 16.0, 16.0), (0.0, 1.0)),
        ("B", (16.0, 0.0, 32.0, 16.0), (0.0, 1.0)),  # shares an edge on screen
        ("C", (0.0, 0.0, 16.0, 16.0), (1.0, 2.0)),  # shares a depth plane with A
    ]
    assert overlap.overlapping_pairs(items) == [("B", "C")] or overlap.overlapping_pairs(items) == []
    assert ("A", "B") not in overlap.overlapping_pairs(items)
    assert ("A", "C") not in overlap.overlapping_pairs(items)


def test_far_apart_on_screen_is_not_reported() -> None:
    items = [
        ("A", (0.0, 0.0, 16.0, 16.0), (0.0, 1.0)),
        ("B", (100.0, 0.0, 116.0, 16.0), (0.5, 1.5)),
    ]
    assert overlap.overlapping_pairs(items) == []


def test_pairs_keep_input_order() -> None:
    rect = (0.0, 0.0, 10.0, 10.0)
    items = [("C", rect, (0.0, 2.0)), ("A", rect, (1.0, 3.0)), ("B", rect, (1.5, 2.5))]
    assert overlap.overlapping_pairs(items) == [("C", "A"), ("C", "B"), ("A", "B")]


def test_empty_and_single() -> None:
    assert overlap.overlapping_pairs([]) == []
    assert overlap.overlapping_pairs([("A", (0.0, 0.0, 1.0, 1.0), (0.0, 1.0))]) == []


def test_format_warnings() -> None:
    assert overlap.format_warnings([]) == ""
    text = overlap.format_warnings([("A", "B"), ("C", "D")])
    assert text.count(";") == 1
    assert "A" in text and "B" in text and "D" in text
