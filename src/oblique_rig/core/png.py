# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal PNG writer and reader: zlib + struct, no PIL.

Writing is byte-exact (no colour management): 8-bit RGBA, non-interlaced,
filter type 0 on every scanline. Reading handles what Blender writes: 8-bit
greyscale, grey + alpha, RGB and RGBA, non-interlaced, all five scanline
filter types, IDAT split over several chunks; everything is returned as RGBA
(opaque alpha where the file has none).

Arrays are numpy ``(height, width, 4)`` uint8. With ``bottom_up=True`` (the
default, Blender's order) array row 0 is the bottom of the image, i.e. the
last PNG scanline. numpy is only used to hold the pixels; the PNG format work
is the standard library.
"""

import struct
import zlib

import numpy as np

SIGNATURE = b"\x89PNG\r\n\x1a\n"

_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
"""Colour type -> samples per pixel (8-bit): grey, RGB, grey + alpha, RGBA."""


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def encode_rgba(pixels: np.ndarray, bottom_up: bool = True, level: int = 6) -> bytes:
    """PNG file bytes for a ``(h, w, 4)`` uint8 RGBA array.

    ``bottom_up``: array row 0 is the bottom of the image (written last).
    ``level`` is the zlib compression level.

    Raises:
        ValueError: if the array is not a non-empty ``(h, w, 4)``.
    """
    array = np.asarray(pixels)
    if array.ndim != 3 or array.shape[2] != 4 or array.shape[0] == 0 or array.shape[1] == 0:
        raise ValueError(f"expected a non-empty (h, w, 4) RGBA array, got shape {array.shape}")
    array = np.clip(array, 0, 255).astype(np.uint8) if array.dtype != np.uint8 else array
    height, width = array.shape[:2]
    rows = array[::-1] if bottom_up else array
    raw = np.zeros((height, width * 4 + 1), dtype=np.uint8)  # leading 0 = filter "None"
    raw[:, 1:] = rows.reshape(height, width * 4)
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw.tobytes(), level))
        + _chunk(b"IEND", b"")
    )


def write_png(path: str, pixels: np.ndarray, bottom_up: bool = True) -> None:
    """Write :func:`encode_rgba` output to ``path`` (the directory must exist)."""
    data = encode_rgba(pixels, bottom_up=bottom_up)
    with open(path, "wb") as handle:
        handle.write(data)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> bytearray:
    """Undo the per-scanline filters; returns ``height * stride`` bytes, top row first."""
    if len(raw) < height * (stride + 1):
        raise ValueError("PNG image data is truncated")
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ftype = raw[pos]
        cur = bytearray(raw[pos + 1 : pos + 1 + stride])
        pos += stride + 1
        if ftype == 0:
            pass
        elif ftype == 1:  # Sub
            for i in range(bpp, stride):
                cur[i] = (cur[i] + cur[i - bpp]) & 0xFF
        elif ftype == 2:  # Up
            cur = bytearray(((np.frombuffer(cur, np.uint8) + np.frombuffer(prev, np.uint8)) & 0xFF).tobytes())
        elif ftype == 3:  # Average
            for i in range(stride):
                left = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                if i >= bpp:
                    cur[i] = (cur[i] + _paeth(cur[i - bpp], prev[i], prev[i - bpp])) & 0xFF
                else:
                    cur[i] = (cur[i] + prev[i]) & 0xFF
        else:
            raise ValueError(f"unknown PNG filter type {ftype} on scanline {y}")
        out[y * stride : (y + 1) * stride] = cur
        prev = cur
    return out


def decode_rgba(data: bytes, bottom_up: bool = True) -> np.ndarray:
    """Decode PNG bytes to a ``(h, w, 4)`` uint8 RGBA array.

    Supports 8-bit grey, grey + alpha, RGB and RGBA, non-interlaced, every
    filter type. ``bottom_up``: array row 0 is the bottom of the image.

    Raises:
        ValueError: on a bad signature or CRC, truncated data, or an
            unsupported format (palette, 16-bit, interlaced).
    """
    if not data.startswith(SIGNATURE):
        raise ValueError("not a PNG file (bad signature)")
    pos = len(SIGNATURE)
    header: tuple[int, ...] | None = None
    idat = bytearray()
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        body = data[pos + 8 : pos + 8 + length]
        crc_bytes = data[pos + 8 + length : pos + 12 + length]
        if len(body) != length or len(crc_bytes) != 4:
            raise ValueError(f"PNG chunk {kind!r} is truncated")
        if struct.unpack(">I", crc_bytes)[0] != zlib.crc32(kind + body):
            raise ValueError(f"PNG chunk {kind!r} has a bad CRC")
        pos += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if header is None:
        raise ValueError("PNG has no IHDR chunk")
    width, height, depth, color_type, compression, filter_method, interlace = header
    if depth != 8 or color_type not in _CHANNELS:
        raise ValueError(f"unsupported PNG format: bit depth {depth}, colour type {color_type}")
    if compression != 0 or filter_method != 0:
        raise ValueError("unsupported PNG compression or filter method")
    if interlace != 0:
        raise ValueError("interlaced PNGs are not supported")
    if width == 0 or height == 0:
        raise ValueError("PNG has zero size")
    channels = _CHANNELS[color_type]
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as e:
        raise ValueError(f"PNG image data does not decompress: {e}") from e
    pixels = _unfilter(raw, height, width * channels, channels)
    samples = np.frombuffer(bytes(pixels), dtype=np.uint8).reshape(height, width, channels)
    out = np.empty((height, width, 4), dtype=np.uint8)
    if channels >= 3:
        out[..., :3] = samples[..., :3]
    else:
        out[..., :3] = samples[..., :1]
    out[..., 3] = samples[..., -1] if channels in (2, 4) else 255
    return np.ascontiguousarray(out[::-1]) if bottom_up else out


def read_png(path: str, bottom_up: bool = True) -> np.ndarray:
    """Read a PNG file with :func:`decode_rgba`."""
    with open(path, "rb") as handle:
        return decode_rgba(handle.read(), bottom_up=bottom_up)
