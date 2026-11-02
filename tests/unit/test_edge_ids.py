"""Unit tests for core/edge_ids.py: island index <-> colour encoding for the sharp-edge pass."""

import importlib.util
import itertools
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


edge_ids = load_core_module("edge_ids")


def test_first_colours() -> None:
    assert edge_ids.island_color(0) == (4, 4, 4)
    assert edge_ids.island_color(1) == (12, 4, 4)
    assert edge_ids.island_color(31) == (252, 4, 4)
    assert edge_ids.island_color(32) == (4, 12, 4)
    assert edge_ids.island_color(1024) == (4, 4, 12)
    assert edge_ids.island_color(edge_ids.ID_COUNT - 1) == (252, 252, 252)


def test_formula() -> None:
    for i in (0, 5, 77, 1000, 12345, 32767):
        r, g, b = edge_ids.island_color(i)
        assert r == (i % 32) * 8 + 4
        assert g == (i // 32 % 32) * 8 + 4
        assert b == (i // 1024 % 32) * 8 + 4


def test_round_trip_over_every_id() -> None:
    assert edge_ids.ID_COUNT == 32768
    colours = set()
    for i in range(edge_ids.ID_COUNT):
        colour = edge_ids.island_color(i)
        assert edge_ids.island_index(colour) == i
        colours.add(colour)
    assert len(colours) == edge_ids.ID_COUNT


def test_ids_wrap_like_the_node_tree() -> None:
    """The node tree takes each channel modulo 32, so ids past 32767 reuse colours."""
    assert edge_ids.island_color(edge_ids.ID_COUNT) == edge_ids.island_color(0)
    assert edge_ids.island_color(edge_ids.ID_COUNT + 33) == edge_ids.island_color(33)


@pytest.mark.parametrize("index", [0, 1, 31, 32, 1023, 1024, 20000, 32767])
def test_noise_of_three_steps_decodes_to_the_same_id(index) -> None:
    r, g, b = edge_ids.island_color(index)
    for dr, dg, db in itertools.product((-3, 0, 3), repeat=3):
        assert edge_ids.island_index((r + dr, g + dg, b + db)) == index


def test_neighbouring_ids_are_eight_steps_apart() -> None:
    """+-1 noise (merge_near_colors' tolerance) can never merge two ids."""
    for i in range(64):
        a, b = edge_ids.island_color(i), edge_ids.island_color(i + 1)
        assert max(abs(x - y) for x, y in zip(a, b, strict=True)) >= 8


def test_island_index_accepts_rgba_and_numpy_like_values() -> None:
    assert edge_ids.island_index((12, 4, 4, 255)) == 1
    assert edge_ids.island_index([12.0, 4.0, 4.0]) == 1


def test_island_index_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        edge_ids.island_index((256, 4, 4))
    with pytest.raises(ValueError):
        edge_ids.island_index((-1, 4, 4))
    with pytest.raises(ValueError):
        edge_ids.island_index((4, 4))


def test_negative_index_is_rejected() -> None:
    with pytest.raises(ValueError):
        edge_ids.island_color(-1)


def test_linear_value_is_byte_over_255() -> None:
    assert edge_ids.linear_value(0) == 0.0
    assert edge_ids.linear_value(255) == 1.0
    assert edge_ids.linear_value(4) == pytest.approx(4 / 255)
    for byte in range(256):
        assert round(edge_ids.linear_value(byte) * 255) == byte
    with pytest.raises(ValueError):
        edge_ids.linear_value(256)


def test_node_tree_constants_reproduce_the_formula() -> None:
    """The Math nodes compute floor(i / div) % 32 * STEP/255 + OFFSET/255 per channel."""
    for i in (0, 9, 33, 1025, 32767):
        expected = edge_ids.island_color(i)
        got = tuple(
            round(((i // div) % edge_ids.LEVELS * (edge_ids.STEP / 255) + edge_ids.OFFSET / 255) * 255)
            for div in edge_ids.CHANNEL_DIVISORS
        )
        assert got == expected


def test_attribute_names() -> None:
    assert edge_ids.EDGE_ID_ATTRIBUTE == "oblique_edge_id"
    assert edge_ids.SHARP_EDGE_ATTRIBUTE == "sharp_edge"
