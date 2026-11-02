"""Unit tests for core/png.py: a stdlib PNG writer/reader that is byte-exact for RGBA8."""

import importlib.util
import struct
import sys
import zlib
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


png = load_core_module("png")

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def random_rgba(height: int = 7, width: int = 5, seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, size=(height, width, 4), dtype=np.uint8)


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def filtered_png(rows: list[bytes], width: int, color_type: int, bpp: int, filters: list[int]) -> bytes:
    """Build a PNG by hand with the given filter type on each scanline (top row first)."""
    raw = bytearray()
    prev = bytes(len(rows[0]))
    for row, ftype in zip(rows, filters, strict=True):
        out = bytearray()
        for i, x in enumerate(row):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            predictor = [0, a, b, (a + b) // 2, paeth(a, b, c)][ftype]
            out.append((x - predictor) % 256)
        raw += bytes([ftype]) + out
        prev = row
    ihdr = struct.pack(">IIBBBBB", width, len(rows), 8, color_type, 0, 0, 0)
    idat = zlib.compress(bytes(raw))
    # Split IDAT in two to exercise multi-chunk streams.
    return (
        SIGNATURE
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat[:5])
        + chunk(b"IDAT", idat[5:])
        + chunk(b"IEND", b"")
    )


def test_signature_and_ihdr() -> None:
    data = png.encode_rgba(random_rgba(3, 4))
    assert data.startswith(SIGNATURE)
    length, kind = struct.unpack(">I4s", data[8:16])
    assert (length, kind) == (13, b"IHDR")
    width, height, depth, color_type, comp, filt, interlace = struct.unpack(">IIBBBBB", data[16:29])
    assert (width, height, depth, color_type, comp, filt, interlace) == (4, 3, 8, 6, 0, 0, 0)
    assert struct.unpack(">I", data[29:33])[0] == zlib.crc32(data[12:29])
    assert data.endswith(chunk(b"IEND", b""))


def test_round_trip_random_rgba() -> None:
    pixels = random_rgba(13, 11)
    decoded = png.decode_rgba(png.encode_rgba(pixels))
    assert decoded.dtype == np.uint8
    assert decoded.shape == (13, 11, 4)
    assert np.array_equal(decoded, pixels)


def test_bottom_up_flag_controls_row_order() -> None:
    pixels = random_rgba(4, 3)
    # Bottom-up input: array row 0 is the last PNG scanline.
    top_down = png.decode_rgba(png.encode_rgba(pixels), bottom_up=False)
    assert np.array_equal(top_down, pixels[::-1])
    assert np.array_equal(png.decode_rgba(png.encode_rgba(pixels, bottom_up=False), bottom_up=False), pixels)
    assert np.array_equal(png.decode_rgba(png.encode_rgba(pixels, bottom_up=False)), pixels[::-1])


def test_first_scanline_is_the_top_row() -> None:
    pixels = np.zeros((2, 1, 4), dtype=np.uint8)
    pixels[1, 0] = (255, 0, 0, 255)  # top row in bottom-up order
    raw = zlib.decompress(png.encode_rgba(pixels)[41 : -12 - 4])
    assert raw[:5] == bytes([0, 255, 0, 0, 255])


@pytest.mark.parametrize("ftype", [0, 1, 2, 3, 4])
def test_decode_every_filter_type(ftype: int) -> None:
    pixels = random_rgba(6, 5, seed=ftype + 10)
    rows = [bytes(r) for r in pixels.reshape(6, -1)]  # top row first (PNG order)
    data = filtered_png(rows, 5, 6, 4, [ftype] * 6)
    assert np.array_equal(png.decode_rgba(data, bottom_up=False), pixels)


def test_decode_mixed_filters_rgb() -> None:
    rgb = np.random.default_rng(7).integers(0, 256, size=(5, 4, 3), dtype=np.uint8)
    rows = [bytes(r) for r in rgb.reshape(5, -1)]
    data = filtered_png(rows, 4, 2, 3, [4, 3, 2, 1, 0])
    decoded = png.decode_rgba(data, bottom_up=False)
    assert decoded.shape == (5, 4, 4)
    assert np.array_equal(decoded[..., :3], rgb)
    assert (decoded[..., 3] == 255).all()


def test_decode_grey_and_grey_alpha() -> None:
    grey = np.arange(12, dtype=np.uint8).reshape(3, 4) * 20
    data = filtered_png([bytes(r) for r in grey], 4, 0, 1, [1, 4, 3])
    decoded = png.decode_rgba(data, bottom_up=False)
    assert np.array_equal(decoded[..., 0], grey) and np.array_equal(decoded[..., 2], grey)
    assert (decoded[..., 3] == 255).all()
    ga = np.stack([grey, 255 - grey], axis=-1)
    data = filtered_png([bytes(r) for r in ga.reshape(3, -1)], 4, 4, 2, [2, 4, 1])
    decoded = png.decode_rgba(data, bottom_up=False)
    assert np.array_equal(decoded[..., 1], grey) and np.array_equal(decoded[..., 3], 255 - grey)


def test_decode_rejects_unsupported_and_corrupt_data() -> None:
    with pytest.raises(ValueError):
        png.decode_rgba(b"not a png")
    sixteen_bit = SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 16, 6, 0, 0, 0))
    with pytest.raises(ValueError):
        png.decode_rgba(sixteen_bit + chunk(b"IDAT", zlib.compress(bytes(9))) + chunk(b"IEND", b""))
    interlaced = SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 1))
    with pytest.raises(ValueError):
        png.decode_rgba(interlaced + chunk(b"IDAT", zlib.compress(bytes(5))) + chunk(b"IEND", b""))
    good = bytearray(png.encode_rgba(random_rgba(2, 2)))
    good[20] ^= 0xFF  # corrupt IHDR, CRC no longer matches
    with pytest.raises(ValueError):
        png.decode_rgba(bytes(good))


def test_encode_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError):
        png.encode_rgba(np.zeros((2, 2, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        png.encode_rgba(np.zeros((0, 2, 4), dtype=np.uint8))


def test_write_and_read_png(tmp_path: Path) -> None:
    pixels = random_rgba(9, 6)
    target = tmp_path / "sub" / "out.png"
    target.parent.mkdir()
    png.write_png(str(target), pixels)
    assert target.read_bytes().startswith(SIGNATURE)
    assert np.array_equal(png.read_png(str(target)), pixels)
    assert np.array_equal(png.decode_rgba(target.read_bytes()), pixels)
