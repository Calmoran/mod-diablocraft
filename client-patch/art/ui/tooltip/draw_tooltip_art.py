#!/usr/bin/env python3
"""Redraw the D3 tooltip's art (diablocraft-tooltip-reskin).

Two white, tintable pieces for the tooltip body. The Lua names the paths under
Interface\\AddOns\\Torment\\art\\ and tints them with SetVertexColor, so the
pixels here are white and carry only the shape and the alpha; the colour comes
from the damage element. Nothing here is baked colour, and there is no
randomness - the script writes exactly what is committed.

    dc_diamond.png  16x16   the bullet: a filled rhombus touching all four edges
    dc_glow.png     128x128 a soft DPS glow: white, alpha ~0.55 centre to 0 rim

Drawn at 8x with PIL and downscaled, as draw_rift_art.py does, so the diamond's
edges are cleanly antialiased and the glow has no hard ring.

    python client-patch/art/ui/tooltip/draw_tooltip_art.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SS = 8  # supersampling
GLOW_ALPHA = 0.55  # centre opacity, so SetVertexColor can tint without clipping


def canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width * SS, height * SS), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def done(image: Image.Image, width: int, height: int) -> Image.Image:
    return image.resize((width, height), Image.LANCZOS)


def diamond() -> Image.Image:
    # A filled rhombus: the midpoint of each edge, so the tips touch the canvas.
    size = 16
    image, draw = canvas(size, size)
    n = size * SS
    mid = n / 2
    draw.polygon([(mid, 0), (n, mid), (mid, n), (0, mid)], fill=(255, 255, 255, 255))
    return done(image, size, size)


def glow() -> Image.Image:
    # A radial falloff on a cosine curve: opaque white, alpha 0.55 at the centre
    # and 0 at the rim. Overlapping ellipses are drawn largest-first, so the
    # last one covering a pixel sets its alpha to cos(r) there - smooth, no ring.
    size = 128
    n = size * SS
    alpha = Image.new("L", (n, n), 0)
    draw = ImageDraw.Draw(alpha)
    centre = n // 2
    for radius in range(centre, 0, -1):
        t = radius / centre
        value = int(round(255 * GLOW_ALPHA * math.cos(t * math.pi / 2)))
        box = (centre - radius, centre - radius, centre + radius - 1, centre + radius - 1)
        draw.ellipse(box, fill=max(0, value))
    image = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    image.putalpha(done(alpha, size, size))
    return image


PIECES = {
    "dc_diamond.png": diamond,
    "dc_glow.png": glow,
}


def main() -> int:
    for name, draw in PIECES.items():
        image = draw()
        assert all(side & (side - 1) == 0 for side in image.size), (name, image.size)
        image.save(HERE / name)
        print(f"{name} {image.size[0]}x{image.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
