#!/usr/bin/env python3
"""Cut the designer's compass into the bounty waypoint marker (diablocraft-dm9vg.6).

The source is `source/bounty-map-icon-source.png` (1354x1356), the designer's pick for the
zone waypoint on the world map (his ruling #7; `_agent-scratch/bounties-plan-2026-10-10/bounty-map-icon.md`):
a black compass rose with a white needle, on a white field, with two corner marks (a logo bottom-left, a
"98" badge bottom-right) that are not part of the glyph. Not Blizzard art, so it ships.

The cut: the outer white field becomes transparent (a flood fill of white from the image border, so the
needle and the inner ring - white enclosed by the black disc - stay opaque); the two corner marks are
dropped (only the largest connected ink blob survives, which is the compass); the compass is cropped to
its own box and fitted, aspect kept, into a 30x30 marker centred on a 32x32 (power-of-two) transparent
canvas. 32x32 is the canvas `client-patch/build_ui_art.py` needs; the addon draws it at 30 (BountyMap.lua
WAYPOINT_SIZE, a tunable in the addon if the size is argued on dev).

    python client-patch/art/ui/bounties/cut_bounty_waypoint.py
    python client-patch/build_ui_art.py
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

try:
    from PIL import Image
except ModuleNotFoundError:                      # Pillow is vendored in the shared scratch
    sys.path.append(str(Path(__file__).resolve().parents[4] / "azerothcore-wotlk" / "build" / "_agent-scratch"
                        / "pil"))
    from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "source" / "bounty-map-icon-source.png"
OUTPUT = HERE / "bounty_waypoint.png"

WORK = 320        # the size the source is keyed at; the output is 30, so this is plenty of detail
CANVAS = 32       # power-of-two addon canvas
MARKER = 30       # the glyph as drawn (the designer's "about 30x30")
WHITE = 238       # a channel above this is field white, not ink


def keyed_alpha(image: "Image.Image") -> "Image.Image":
    """The image with the outer white field transparent and everything else opaque."""
    width, height = image.size
    pixels = image.load()
    white = bytearray(width * height)
    for y in range(height):
        base = y * width
        for x in range(width):
            r, g, b, _ = pixels[x, y]
            if r > WHITE and g > WHITE and b > WHITE:
                white[base + x] = 1

    outside = bytearray(width * height)   # field white reached from the border
    queue: deque[int] = deque()
    for x in range(width):
        for y in (0, height - 1):
            index = y * width + x
            if white[index] and not outside[index]:
                outside[index] = 1
                queue.append(index)
    for y in range(height):
        for x in (0, width - 1):
            index = y * width + x
            if white[index] and not outside[index]:
                outside[index] = 1
                queue.append(index)
    while queue:
        index = queue.popleft()
        x, y = index % width, index // width
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                neighbour = ny * width + nx
                if white[neighbour] and not outside[neighbour]:
                    outside[neighbour] = 1
                    queue.append(neighbour)

    seen = bytearray(width * height)
    largest: list[int] = []
    for start in range(width * height):
        if outside[start] or seen[start]:
            continue
        component: list[int] = []
        seen[start] = 1
        queue.append(start)
        while queue:
            index = queue.popleft()
            component.append(index)
            x, y = index % width, index // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    neighbour = ny * width + nx
                    if not outside[neighbour] and not seen[neighbour]:
                        seen[neighbour] = 1
                        queue.append(neighbour)
        if len(component) > len(largest):
            largest = component

    keep = bytearray(width * height)
    for index in largest:
        keep[index] = 1
    out = image.copy()
    out_pixels = out.load()
    for y in range(height):
        base = y * width
        for x in range(width):
            r, g, b, _ = out_pixels[x, y]
            out_pixels[x, y] = (r, g, b, 255 if keep[base + x] else 0)
    return out


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f"{SOURCE} is missing")
    source = Image.open(SOURCE).convert("RGBA").resize((WORK, WORK), Image.LANCZOS)
    keyed = keyed_alpha(source)

    box = keyed.getbbox()
    if not box:
        raise SystemExit("no ink survived the key")
    glyph = keyed.crop(box)
    scale = MARKER / max(glyph.size)
    glyph = glyph.resize((max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale))),
                         Image.LANCZOS)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(glyph, ((CANVAS - glyph.width) // 2, (CANVAS - glyph.height) // 2))
    canvas.save(OUTPUT)
    print(f"{OUTPUT.relative_to(HERE.parents[2])}: {canvas.size[0]}x{canvas.size[1]}, "
          f"glyph {glyph.size[0]}x{glyph.size[1]} from {box}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
