#!/usr/bin/env python3
"""Redraw the rift tracker's art (diablocraft-rift-tracker, art plan approved by the
Architect 2026-10-03; refined from the designer's full-resolution D3 shots, diablocraft-p6mg).

Every piece is REDRAWN to match the designer's own D3 screenshots
(azerothcore-wotlk/build/_agent-scratch/rift-tracker/alex-d3-rift-bar-half-and-header.png
and alex-d3-rift-complete-new.png); nothing is cropped from the video or the shots. Each
piece is drawn at 4x and downsampled for clean edges, onto a power-of-two canvas at least
twice its on-screen size, so build_ui_art.py converts it without padding.

The lettering (the "OBJECTIVES" header and the COMPLETE!/NEW!/UPDATE! flourishes) was
baked here from D3's own Exocet face until diablocraft-rift-tracker-exocet-slider (the designer
2026-10-04) moved those words to real font strings in the tracker: the shipped
Torment/fonts/Exocet.ttf (built by build_tooltip_fonts.py) draws them now, so this script
no longer paints them and the four word textures are gone. The vendored reference font in
source/ stays (see source/README.md).

    python client-patch/art/ui/rift/draw_rift_art.py   # writes the PNGs beside it
    python client-patch/build_ui_art.py                # PNG -> addon BLP

The bar's filigree, crest, end caps and the lettering are read off the full-resolution
shots, so the bar is no longer the draft drawn from the designer's 340x75 video crop.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
SS = 4  # supersampling

# Colours read off the shots (the D3 list on its dark, gold-lit ground).
LINE_GREY = (235, 232, 224, 255)   # the empty box outline
SLASH_GOLD = (255, 236, 96, 255)   # the brush-stroke X, bright yellow-gold
X_GLOW = (255, 186, 48)
RED_FACE = (150, 44, 26, 255)      # the minimise button
RED_EDGE = (66, 20, 12, 255)
RED_LIGHT = (196, 96, 60, 255)
RED_GLYPH = (240, 214, 184, 255)
STREAK_GOLD = (255, 196, 64)


def canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width * SS, height * SS), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def done(image: Image.Image, width: int, height: int) -> Image.Image:
    return image.resize((width, height), Image.LANCZOS)


def stroke(draw: ImageDraw.ImageDraw, start, end, wide: float, narrow: float, colour) -> None:
    """A brush stroke: wide at the start, tapering to `narrow` at the end."""
    (x0, y0), (x1, y1) = start, end
    length = math.hypot(x1 - x0, y1 - y0)
    nx, ny = -(y1 - y0) / length, (x1 - x0) / length
    points = [(x0 + nx * wide / 2, y0 + ny * wide / 2), (x1 + nx * narrow / 2, y1 + ny * narrow / 2),
              (x1 - nx * narrow / 2, y1 - ny * narrow / 2), (x0 - nx * wide / 2, y0 - ny * wide / 2)]
    draw.polygon(points, fill=colour)
    draw.ellipse((x0 - wide / 2, y0 - wide / 2, x0 + wide / 2, y0 + wide / 2), fill=colour)


# The box sits in the middle of a 16 px widget (10 px square, 3 px margin) so the X can
# run past it as D3's does; the canvas is 32 px, i.e. 2x.
BOX_CANVAS, BOX_SIDE, BOX_MARGIN = 32, 20, 6


def box(draw: ImageDraw.ImageDraw) -> None:
    s = SS
    inset = 2 * s
    draw.rounded_rectangle(((BOX_MARGIN * s) + inset, (BOX_MARGIN * s) + inset,
                            ((BOX_MARGIN + BOX_SIDE) * s) - inset, ((BOX_MARGIN + BOX_SIDE) * s) - inset),
                           radius=2 * s, outline=LINE_GREY, width=2 * s)


def x_mark(draw: ImageDraw.ImageDraw, size: int, scale: float = 1.0) -> None:
    """D3's X: two brush strokes, the falling one longer and tapering to the lower right.
    `size` is the box canvas the strokes are laid out on; `scale` enlarges that layout."""
    s = SS * scale
    stroke(draw, (5 * s, 3.5 * s), (size * s - 2 * s, size * s - 1.5 * s), 5.0 * s, 1.2 * s, SLASH_GOLD)
    stroke(draw, (size * s - 6 * s, 4 * s), (4 * s, size * s - 7 * s), 4.4 * s, 1.6 * s, SLASH_GOLD)


def check_empty() -> Image.Image:
    image, draw = canvas(BOX_CANVAS, BOX_CANVAS)
    box(draw)
    return done(image, BOX_CANVAS, BOX_CANVAS)


def check_crossed() -> Image.Image:
    image, draw = canvas(BOX_CANVAS, BOX_CANVAS)
    box(draw)
    x_mark(draw, BOX_CANVAS)
    glow = image.filter(ImageFilter.GaussianBlur(1.4 * SS))
    image = Image.alpha_composite(glow, image)
    return done(image, BOX_CANVAS, BOX_CANVAS)


def slash() -> Image.Image:
    # The same X at 64 px, with a soft glow: it lands from five times the box's size.
    image, draw = canvas(64, 64)
    x_mark(draw, BOX_CANVAS, 64 / BOX_CANVAS)
    glow = image.filter(ImageFilter.GaussianBlur(3 * SS))
    image = Image.alpha_composite(glow, image)
    return done(image, 64, 64)


def minimise() -> Image.Image:
    # The red button in the shots: a beveled crimson square, lit top-left, with a pale
    # bow-tie glyph (two wedges meeting at a narrow waist).
    image, draw = canvas(32, 32)
    s = SS
    draw.rounded_rectangle((2 * s, 2 * s, 30 * s, 30 * s), radius=2 * s, fill=RED_EDGE)
    draw.rounded_rectangle((3 * s, 3 * s, 29 * s, 29 * s), radius=2 * s, fill=RED_FACE)
    draw.line((4 * s, 4 * s, 28 * s, 4 * s), fill=RED_LIGHT, width=s)
    draw.line((4 * s, 4 * s, 4 * s, 28 * s), fill=RED_LIGHT, width=s)
    # The glyph: a vertical bow-tie, wedged in from left and right.
    draw.polygon([(9 * s, 9 * s), (9 * s, 23 * s), (16 * s, 16 * s)], fill=RED_GLYPH)
    draw.polygon([(23 * s, 9 * s), (23 * s, 23 * s), (16 * s, 16 * s)], fill=RED_GLYPH)
    return done(image, 32, 32)


def flourish_streak() -> Image.Image:
    # The soft gold bloom D3 draws behind a crossed or fresh line: an elongated glow,
    # brightest under the words and gone at the far left.
    width, height = 128, 32
    image = Image.new("RGBA", (width * SS, height * SS), (0, 0, 0, 0))
    pixels = image.load()
    for x in range(width * SS):
        along = (x / (width * SS - 1)) ** 2.2
        for y in range(height * SS):
            across = 1 - abs((y - (height * SS - 1) / 2) / ((height * SS - 1) / 2))
            alpha = int(150 * along * max(0.0, across) ** 1.6)
            pixels[x, y] = (*STREAK_GOLD, alpha)
    image = image.filter(ImageFilter.GaussianBlur(1.2 * SS))
    return image.resize((width, height), Image.LANCZOS)


# The bar, on screen 200x44 in the 204 px list; drawn at 2x into a 512x128 canvas,
# top-left, cropped back by SetTexCoord(0, 400/512, 0, 88/128).
BAR_W, BAR_H = 200, 44
TROUGH = (18, 12, 182, 32)          # x0, y0, x1, y1 of the dark channel the fill runs in
IRON = (40, 33, 27, 255)
IRON_LIGHT = (104, 84, 60, 255)
IRON_DARK = (18, 14, 10, 255)
BRONZE = (152, 112, 62, 255)
CAP_RED = (96, 24, 18, 255)
CAP_PALE = (206, 190, 158, 255)


def bar_frame() -> Image.Image:
    unit = 2 * SS                      # one display pixel at 2x, supersampled
    image = Image.new("RGBA", (512 * SS, 128 * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def r(x0, y0, x1, y1):
        return (x0 * unit, y0 * unit, x1 * unit, y1 * unit)

    def pts(*points):
        return [(x * unit, y * unit) for x, y in points]

    def line(points, colour, w):
        draw.line(pts(*points), fill=colour, width=max(1, int(w * unit)))

    def arc(cx, cy, radius, start, end, colour, w):
        draw.arc(r(cx - radius, cy - radius, cx + radius, cy + radius), start, end,
                 fill=colour, width=max(1, int(w * unit)))

    mid = BAR_W / 2
    x0, y0, x1, y1 = TROUGH

    # The plate: a bronze rail, a dark gap, then the iron body.
    draw.rounded_rectangle(r(8, 5, BAR_W - 8, 39), radius=2 * unit, outline=BRONZE, width=max(1, int(0.8 * unit)))
    draw.rectangle(r(9.5, 6.5, BAR_W - 9.5, 37.5), fill=IRON_DARK)
    draw.rectangle(r(11, 8, BAR_W - 11, 36), fill=IRON)
    line([(12, 8), (BAR_W - 12, 8)], IRON_LIGHT, 1)
    line([(12, 36), (BAR_W - 12, 36)], IRON_DARK, 1)

    # The crest: a tall diamond finial over two pairs of scrolls spreading along the top rail.
    for side in (-1, 1):
        for colour, w, lift in ((IRON_DARK, 2.6, 0.0), (IRON_LIGHT, 1.1, -0.4)):
            arc(mid + side * 8, 4 + lift, 5.0, 180 if side < 0 else 270, 360 if side < 0 else 450, colour, w)
            arc(mid + side * 21, 6 + lift, 3.6, 200 if side < 0 else 250, 380 if side < 0 else 430, colour, w)
            line([(mid + side * 4, 7.5 + lift), (mid + side * 32, 7.5 + lift)], colour, w)
    draw.polygon(pts((mid - 5, 10), (mid, -2.5), (mid + 5, 10)), fill=IRON, outline=BRONZE)
    draw.polygon(pts((mid - 2.2, 6.5), (mid, 0.6), (mid + 2.2, 6.5)), fill=BRONZE)

    # The pendant under the bar: a small inverted finial with its own two scrolls.
    for side in (-1, 1):
        arc(mid + side * 5, 38, 3, 0 if side < 0 else 90, 180 if side < 0 else 270, IRON_DARK, 2.0)
        arc(mid + side * 5, 38, 3, 0 if side < 0 else 90, 180 if side < 0 else 270, IRON_LIGHT, 0.8)
    draw.polygon(pts((mid - 4, 35), (mid + 4, 35), (mid, 43.5)), fill=IRON, outline=BRONZE)

    # The pointed end caps: a crimson pennant with a pale inner edge, tip outward.
    for left in (True, False):
        tip, base, step = (1.5, 13, 1) if left else (BAR_W - 1.5, BAR_W - 13, -1)
        draw.polygon(pts((tip, 22), (base, 9), (base + step * 3, 9), (base + step * 3, 35), (base, 35)),
                     fill=IRON, outline=BRONZE)
        draw.polygon(pts((tip + step * 4, 22), (base, 13.5), (base, 30.5)), fill=CAP_RED)
        draw.line(pts((tip + step * 4, 22), (base, 13.5)), fill=CAP_PALE, width=unit // 2)
        draw.line(pts((tip + step * 4, 22), (base, 30.5)), fill=CAP_PALE, width=unit // 2)

    # The bronze line hugging the channel, then the channel cut out.
    draw.rectangle(r(x0 - 2, y0 - 2, x1 + 2, y1 + 2), outline=BRONZE, width=max(1, int(0.8 * unit)))
    draw.rectangle(r(x0, y0, x1, y1), fill=(0, 0, 0, 0))
    line([(x0 + 1, y0 + 0.5), (x1 - 1, y0 + 0.5)], (210, 206, 196, 70), 0.8)
    return image.resize((512, 128), Image.LANCZOS)


def bar_fill() -> Image.Image:
    # Molten gold: dark amber at the rims, bright high, mottled.
    width, height = 256, 32
    base = Image.new("RGBA", (width, height))
    noise = Image.effect_noise((width // 4, height // 4), 64).resize((width, height), Image.BICUBIC)
    noise = noise.filter(ImageFilter.GaussianBlur(2))
    stops = [(0.0, (120, 74, 16)), (0.3, (236, 178, 56)), (0.62, (196, 132, 30)), (1.0, (92, 56, 10))]
    px, nz = base.load(), noise.load()
    for y in range(height):
        t = y / (height - 1)
        colour = stops[0][1]
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                colour = tuple(c0[i] + (c1[i] - c0[i]) * k for i in range(3))
                break
        for x in range(width):
            m = 0.8 + 0.4 * (nz[x, y] / 255 - 0.5)
            px[x, y] = tuple(max(0, min(255, int(c * m))) for c in colour) + (255,)
    return base


def bar_edge() -> Image.Image:
    # The bright leading edge, drawn additive: a white-gold core with a soft falloff.
    width, height = 16, 32
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    px = image.load()
    for x in range(width):
        d = abs(x - (width - 1) / 2) / ((width - 1) / 2)
        a = int(255 * max(0.0, 1 - d) ** 2.0)
        for y in range(height):
            px[x, y] = (255, 246, 190, a)
    return image


# -------------------------------------------------------------------------------------------------
# The lettering: no longer baked here
# -------------------------------------------------------------------------------------------------
# The "OBJECTIVES" header and the COMPLETE!/NEW!/UPDATE! flourishes were baked into
# rift_header_text.png and rift_flourish_*.png from source/exocet-blizzard-light.ttf until
# diablocraft-rift-tracker-exocet-slider (ruling 2026-10-04); the tracker draws them as real
# font strings in the shipped Torment/fonts/Exocet.ttf now, and those four textures are
# gone. The vendored face stays in source/ as the kit's pinned reference.

PIECES = {
    "rift_bar_frame.png": bar_frame,
    "rift_bar_fill.png": bar_fill,
    "rift_bar_edge.png": bar_edge,
    "rift_check_empty.png": check_empty,
    "rift_check_crossed.png": check_crossed,
    "rift_slash.png": slash,
    "rift_minimise.png": minimise,
    "rift_flourish_streak.png": flourish_streak,
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
