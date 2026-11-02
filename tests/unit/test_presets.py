"""Unit tests for core/presets.py: slope and resolution presets."""

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


presets = load_core_module("presets")


def test_slope_preset_table() -> None:
    table = {p.identifier: (p.label, p.right_per_unit, p.up_per_unit) for p in presets.SLOPE_PRESETS}
    assert table == {
        "PIXEL_2_1": ("2:1 cavalier", 1.0, 0.5),
        "CABINET_2_1": ("2:1 cabinet", 0.5, 0.25),
        "PIXEL_1_1": ("1:1", 0.5, 0.5),
        "PIXEL_3_2": ("3:2", 0.75, 0.5),
        "PIXEL_1_2": ("1:2 (steep)", 0.5, 1.0),
    }
    assert presets.SLOPE_PRESETS[0].identifier == "PIXEL_2_1"


def test_presets_unpack_as_plain_tuples() -> None:
    identifier, label, right, up = presets.SLOPE_PRESETS[0]
    assert (identifier, label, right, up) == ("PIXEL_2_1", "2:1 cavalier", 1.0, 0.5)
    identifier, label, res_x, res_y, ppu = presets.RESOLUTION_PRESETS[0]
    assert identifier == "R320_200_16" and (res_x, res_y, ppu) == (320, 200, 16)


@pytest.mark.parametrize(
    ("identifier", "ppu", "expected"),
    [
        ("PIXEL_2_1", 16, (16, 8)),
        ("CABINET_2_1", 16, (8, 4)),
        ("PIXEL_1_1", 16, (8, 8)),
        ("PIXEL_3_2", 16, (12, 8)),
        ("PIXEL_1_2", 16, (8, 16)),
        ("PIXEL_2_1", 32, (32, 16)),
        ("CABINET_2_1", 2, (1, 1)),  # 0.5 rounds up, never to zero
        ("CABINET_2_1", 1, (1, 1)),  # non-zero fractions keep at least one pixel
        ("PIXEL_3_2", 10, (8, 5)),  # 7.5 rounds half up
    ],
)
def test_slope_preset(identifier: str, ppu: int, expected: tuple[int, int]) -> None:
    result = presets.slope_preset(identifier, ppu)
    assert result == expected
    assert all(isinstance(v, int) for v in result)


def test_slope_preset_rejects_unknown_and_bad_ppu() -> None:
    with pytest.raises(ValueError):
        presets.slope_preset("NOPE", 16)
    with pytest.raises(ValueError):
        presets.slope_preset("PIXEL_2_1", 0)


def test_resolution_preset_table() -> None:
    table = {
        p.identifier: (p.resolution_x, p.resolution_y, p.pixels_per_unit) for p in presets.RESOLUTION_PRESETS
    }
    assert table == {
        "R320_200_16": (320, 200, 16),
        "R640_360_16": (640, 360, 16),
        "R256_256_16": (256, 256, 16),
        "R128_128_8": (128, 128, 8),
        "R512_288_32": (512, 288, 32),
    }
    for p in presets.RESOLUTION_PRESETS:
        assert p.label and str(p.resolution_x) in p.label
        assert p.resolution_x % 2 == 0 and p.resolution_y % 2 == 0


def test_resolution_preset_lookup() -> None:
    assert presets.resolution_preset("R128_128_8") == (
        "R128_128_8",
        presets.RESOLUTION_PRESETS[3].label,
        128,
        128,
        8,
    )
    with pytest.raises(ValueError):
        presets.resolution_preset("NOPE")


def test_identifiers_are_unique_and_enum_safe() -> None:
    for table in (presets.SLOPE_PRESETS, presets.RESOLUTION_PRESETS):
        ids = [p.identifier for p in table]
        assert len(ids) == len(set(ids))
        assert all(i.isupper() or "_" in i for i in ids)
        assert all(i.replace("_", "").isalnum() for i in ids)
