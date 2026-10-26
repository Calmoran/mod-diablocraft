#!/usr/bin/env python3
"""The Monk's Spirit orb fill: the Wizard's Arcane Power fill, colour-shifted to tan/white.

The designer (card q-1013-23, diablocraft-9k91n): "can we color shift the resource orb
from the wizard to a tan/white?" Reads orb_fill_arcane_power_{1,2}.png (the designer's
own fills, diablocraft-zgjb) and writes orb_fill_spirit_{1,2}.png beside them.
Each pixel's luminance, scaled so the brightest pixel of the two sheets is 1,
picks a colour on the RAMP below (a gradient map); alpha is copied unchanged, so
the cells, discs and margins are the source's. build_ui_art.py then makes the
BLPs. RAMP is the look: the designer tunes it from the screenshot.
"""

import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = "orb_fill_arcane_power_{}.png"
TARGET = "orb_fill_spirit_{}.png"

# (luminance 0..1, RGB): deep brown in the shadows, tan in the body, white in the sparkles.
RAMP = [(0.0, (70, 52, 34)), (0.45, (196, 164, 120)), (0.75, (232, 214, 184)), (1.0, (255, 252, 244))]


def ramp_colour(t: float) -> tuple[int, ...]:
    for (t0, c0), (t1, c1) in zip(RAMP, RAMP[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return RAMP[-1][1]


def main() -> int:
    sources = [Image.open(HERE / SOURCE.format(n)).convert("RGBA") for n in (1, 2)]
    lmax = max(image.convert("L").getextrema()[1] for image in sources)
    lut = [ramp_colour(min(1.0, value / lmax)) for value in range(256)]
    for n, image in zip((1, 2), sources):
        luma = image.convert("L")
        channels = [luma.point([colour[i] for colour in lut]) for i in range(3)]
        out = Image.merge("RGBA", channels + [image.getchannel("A")])
        assert out.getchannel("A").tobytes() == image.getchannel("A").tobytes()
        out.save(HERE / TARGET.format(n))
        print(f"{TARGET.format(n)} {out.width}x{out.height} from {SOURCE.format(n)} (luminance max {lmax})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
