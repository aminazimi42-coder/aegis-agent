#!/usr/bin/env python3
"""Generate a small shield-style AppIcon.png using only stdlib.

Produces a 128×128 RGBA PNG — a dark rounded shield on a light
background.  No external dependencies, no network, no large binary.
"""
from __future__ import annotations

import struct
import zlib


def _make_png(pixels: list[list[tuple[int, int, int, int]]], width: int, height: int) -> bytes:
    """Encode an RGBA pixel grid into a PNG file."""
    raw = b""
    for row in pixels:
        raw += b"\x00" + b"".join(
            struct.pack("BBBB", r, g, b, a) for r, g, b, a in row
        )
    compressed = zlib.compress(raw, 9)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit, RGBA
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    return png


def _in_shield(x: int, y: int, w: int, h: int) -> bool:
    """Return True if (x, y) falls inside a shield shape."""
    mx = w / 2
    top_margin = h * 0.10
    bottom_margin = h * 0.72
    side_margin = w * 0.18

    if y < top_margin or y > h - top_margin:
        return False

    # narrowing toward the bottom point
    progress = (y - top_margin) / max(1, (bottom_margin - top_margin))
    taper = side_margin * (0.55 + 0.45 * progress)
    left = side_margin + taper * 0.3
    right = w - side_margin - taper * 0.3

    # Below the body, taper to a point
    if y > bottom_margin:
        remain = (y - bottom_margin) / max(1, (h - top_margin - bottom_margin))
        remain = min(1.0, remain)
        half = (right - left) / 2 * (1 - remain)
        left = mx - half
        right = mx + half
        if left >= right:
            return False

    return left <= x <= right


def generate() -> bytes:
    """Generate the 128×128 shield icon and return PNG bytes."""
    w, h = 128, 128
    bg = (240, 244, 248, 255)       # light slate
    shield_fill = (30, 41, 59, 255) # dark slate
    check = (125, 211, 252, 255)    # light blue check mark

    pixels: list[list[tuple[int, int, int, int]]] = []
    for y in range(h):
        row: list[tuple[int, int, int, int]] = []
        for x in range(w):
            if _in_shield(x, y, w, h):
                row.append(shield_fill)
            else:
                row.append(bg)
        pixels.append(row)

    # Draw a simple check mark inside the shield
    cx, cy = w // 2, h // 2
    points = []
    for t in range(0, 100):
        tx = t / 100.0
        # check mark: from upper-left to center-bottom, then to upper-right
        if tx <= 0.5:
            px = cx - 22 + (22 - 5) * (tx / 0.5)
            py = cy + 5 + (18 - 5) * (tx / 0.5)
        else:
            tt = (tx - 0.5) / 0.5
            px = cx - 5 + (28 + 5) * tt
            py = cy + 18 - (18 + 15) * tt
        points.append((int(px), int(py)))

    # Thick check mark by filling nearby pixels
    for y2 in range(h):
        for x2 in range(w):
            for px, py in points:
                if abs(x2 - px) <= 3 and abs(y2 - py) <= 3:
                    pixels[y2][x2] = check
                    break

    return _make_png(pixels, w, h)


if __name__ == "__main__":
    import sys

    out_path = sys.argv[1] if len(sys.argv) > 1 else "AppIcon.png"
    with open(out_path, "wb") as f:
        f.write(generate())
    print(out_path)
