"""Unit tests for the pure logic in core/. These import the module by file path so
they run under plain Python with no Blender and no bl_ext package machinery."""

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


spacing = load_core_module("spacing")


def test_keeps_order_and_spaces_by_gap() -> None:
    assert spacing.evenly_spaced([5.0, 0.0, 2.0], 2.0) == [4.0, 0.0, 2.0]


def test_smallest_value_is_the_anchor() -> None:
    assert spacing.evenly_spaced([10.0, 7.5], 1.0) == [8.5, 7.5]


def test_ties_keep_input_order() -> None:
    assert spacing.evenly_spaced([1.0, 1.0, 1.0], 3.0) == [1.0, 4.0, 7.0]


def test_empty_and_single() -> None:
    assert spacing.evenly_spaced([], 2.0) == []
    assert spacing.evenly_spaced([3.0], 2.0) == [3.0]


def test_zero_gap_collapses() -> None:
    assert spacing.evenly_spaced([4.0, 1.0], 0.0) == [1.0, 1.0]


def test_negative_gap_rejected() -> None:
    with pytest.raises(ValueError):
        spacing.evenly_spaced([0.0, 1.0], -1.0)
