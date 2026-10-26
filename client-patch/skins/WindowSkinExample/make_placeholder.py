#!/usr/bin/env python3
"""Draw the example skin's placeholder window canvas: media/mycube.tga.

A plain stand-in for a player's own window image, in Torment's palette, so the example has a
canvas to show. A real skin brings its own picture instead and never needs
this script. The layout is WindowSkinExample.lua's `anchors`, in this image's own pixels: the
outer frame, a title band, the content area the Cube's body sits on, a close spot and two button
spots below the content.

    python3 client-patch/skins/WindowSkinExample/make_placeholder.py

Writes a 256 x 512 uncompressed 32-bit TGA (the client wants power-of-two sizes); the canvas is
its top 256 x 400, the rest transparent. Byte-stable: a rerun writes the same file.
"""
from pathlib import Path
import struct

W, H, CANVAS_H = 256, 512, 400
# The same spots as WindowSkinExample.lua's anchors, {left, top, width, height}.
CONTENT = (21, 36, 214, 328)
TITLE = (21, 8, 214, 22)
CLOSE = (232, 8, 18, 18)
BUTTONS = ((78, 370, 100, 18), (200, 368, 22, 22))

GROUND = (0.09, 0.07, 0.05)      # the frame
BRONZE = (0.42, 0.32, 0.20)      # its edge (the palette's box border)
BAND = (0.16, 0.12, 0.08)        # the title band
BODY = (0.04, 0.035, 0.03)       # the content area
LINE = (0.30, 0.24, 0.14)        # the content area's edge (the palette's detail border)
SPOT = (0.22, 0.19, 0.14)        # a button spot (the button slot's colour)
RED = (0.30, 0.05, 0.05)         # the close spot


def main():
    pixels = [[(0, 0, 0, 0)] * W for _ in range(H)]

    def fill(rect, colour, edge=None, thickness=1):
        left, top, width, height = rect
        for y in range(top, top + height):
            for x in range(left, left + width):
                inner = (thickness <= x - left < width - thickness and thickness <= y - top < height - thickness)
                pixels[y][x] = tuple(round(c * 255) for c in (colour if inner or edge is None else edge)) + (255,)

    fill((0, 0, W, CANVAS_H), GROUND, BRONZE, 3)
    fill(TITLE, BAND, BRONZE)
    fill(CONTENT, BODY, LINE)
    fill(CLOSE, RED, BRONZE)
    for spot in BUTTONS:
        fill(spot, SPOT, BRONZE)

    # 18-byte header: uncompressed true-colour, 32 bits, origin top-left with 8 alpha bits.
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, W, H, 32, 0x28)
    body = bytes(b for row in pixels for (r, g, b_, a) in row for b in (b_, g, r, a))
    out = Path(__file__).resolve().parent / "media" / "mycube.tga"
    out.write_bytes(header + body)
    print(out)


if __name__ == "__main__":
    main()
