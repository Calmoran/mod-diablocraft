#!/usr/bin/env python3
"""The Shaman's Maelstrom orb fill: the Wizard's Arcane Power fill, mapped to blue with a purple edge.

The card (q-1021-157): "the Maelstrom orb is mostly blue with a purple tint, a gradient if possible: blue centre fading to a
subtle purple edge", built from the orb pieces the other classes use. Reads orb_fill_arcane_power_{1,2}.png (the same fills
the Monk's Spirit and every tinted power start from) and writes orb_fill_maelstrom_{1,2}.png beside them. Each pixel's
luminance, scaled so the brightest pixel of the two sheets is 1, picks a colour on the BLUE ramp (a gradient map) and, a
second time, on the PURPLE ramp; the two are mixed by how far the pixel is from the middle of its cell's disc, nothing in the
centre and EDGE_MIX at the rim. Alpha is copied unchanged, so the cells, discs and margins are the source's. build_ui_art.py
then makes the BLPs. The two ramps and the three numbers are the look: the designer tunes them from the screenshot.
"""

import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = "orb_fill_arcane_power_{}.png"
TARGET = "orb_fill_maelstrom_{}.png"
CELL = 170                   # a frame is 170x170 on a 6 x 5 grid; the disc is 160px with a 5px transparent margin
COLUMNS, ROWS = 6, 5
CENTRE, RADIUS = CELL / 2, 80.0
EDGE_FROM = 0.45             # the purple starts this far out (0 the middle of the disc, 1 its rim)
EDGE_MIX = 0.5               # the share of purple at the rim

# (luminance 0..1, RGB): deep navy in the shadows, electric blue in the body, pale blue in the sparkles.
BLUE = [(0.0, (6, 14, 64)), (0.45, (36, 104, 232)), (0.75, (118, 186, 255)), (1.0, (232, 246, 255))]
# The same ramp in purple, mixed in toward the rim.
PURPLE = [(0.0, (34, 8, 64)), (0.45, (128, 62, 214)), (0.75, (188, 146, 246)), (1.0, (244, 232, 255))]


def ramp_colour(ramp: list, t: float) -> tuple[int, ...]:
    for (t0, c0), (t1, c1) in zip(ramp, ramp[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return ramp[-1][1]


def edge_mix(distance: float) -> float:
    """The purple share at a distance from the disc's middle, as a share of its radius: smooth from EDGE_FROM to the rim."""
    t = min(1.0, max(0.0, (distance - EDGE_FROM) / (1.0 - EDGE_FROM)))
    return EDGE_MIX * t * t * (3 - 2 * t)


def tint(image: Image.Image, lmax: int) -> Image.Image:
    luma = image.convert("L")
    blue = [ramp_colour(BLUE, min(1.0, v / lmax)) for v in range(256)]
    purple = [ramp_colour(PURPLE, min(1.0, v / lmax)) for v in range(256)]
    out = Image.new("RGBA", image.size)
    pixels, luma_data, alpha = [], luma.tobytes(), image.getchannel("A").tobytes()
    width = image.width
    for i, value in enumerate(luma_data):
        x, y = i % width, i // width
        cx, cy = x % CELL + 0.5 - CENTRE, y % CELL + 0.5 - CENTRE
        mix = edge_mix(((cx * cx + cy * cy) ** 0.5) / RADIUS)
        b, p = blue[value], purple[value]
        pixels.append(tuple(round(b[k] + (p[k] - b[k]) * mix) for k in range(3)) + (alpha[i],))
    out.putdata(pixels)
    return out


def main() -> int:
    sources = [Image.open(HERE / SOURCE.format(n)).convert("RGBA") for n in (1, 2)]
    assert all(s.size == (1024, 1024) for s in sources)
    lmax = max(image.convert("L").getextrema()[1] for image in sources)
    for n, image in zip((1, 2), sources):
        out = tint(image, lmax)
        assert out.getchannel("A").tobytes() == image.getchannel("A").tobytes()
        out.save(HERE / TARGET.format(n))
        print(f"{TARGET.format(n)} {out.width}x{out.height} from {SOURCE.format(n)} (luminance max {lmax})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
