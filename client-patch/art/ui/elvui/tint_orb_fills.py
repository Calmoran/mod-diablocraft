#!/usr/bin/env python3
"""Orb fills for the class powers with no fill of their own: the Arcane Power fill, tinted to each power's colour.

Every class power's orb is the same art in its own colour, never a flat disc. For each row of
mod-diablocraft/data/tunables/class_resources.csv whose token has no hand-made fill (OWN_ART), this
reads orb_fill_arcane_power_{1,2}.png (the designer's own fills) and writes orb_fill_<token>_{1,2}.png beside
them, <token> in lower case. The colour is the row's display_colour, which P0 measured as the mean of
the brightest tenth of the lit pixels of D3's globe; so each pixel is the colour scaled by its
luminance over the source's own brightest-tenth mean, and the tinted fill's brightest tenth lands on
the sheet's colour (brighter pixels clip toward white, as the globe's highlights do). Alpha is copied
unchanged, so the cells, discs and margins are the source's. build_ui_art.py then makes the BLPs.
"""

import csv
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SHEET = HERE.parents[3] / "mod-diablocraft" / "data" / "tunables" / "class_resources.csv"
SOURCE = "orb_fill_arcane_power_{}.png"
TARGET = "orb_fill_{}_{}.png"
# Tokens whose fill is hand-made art, kept as the designer approved it: Fury and Arcane Power are the designer's own
# fills, Spirit is shift_orb_fill.py's tan/white and Maelstrom is maelstrom_orb_fill.py's blue with a purple
# edge (looks the designer chose, not the sheet's colour).
OWN_ART = {"FURY", "ARCANE_POWER", "SPIRIT", "MAELSTROM"}


def hex_colour(text: str) -> tuple[int, int, int]:
    text = text.strip().lstrip("#")
    if len(text) != 6:
        raise SystemExit(f"{SHEET.name}: display_colour {text!r} is not #RRGGBB")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def brightest_tenth(images: list[Image.Image]) -> float:
    """The mean luminance of the brightest tenth of the lit pixels: P0's measure."""
    values: list[int] = []
    for image in images:
        luma = image.convert("L").tobytes()
        alpha = image.getchannel("A").tobytes()
        values.extend(l for l, a in zip(luma, alpha) if a > 0)
    values.sort(reverse=True)
    top = values[:max(1, len(values) // 10)]
    return sum(top) / len(top)


def brightest_tenth_colour(images: list[Image.Image]) -> tuple[float, ...]:
    """The mean RGB of the brightest tenth of the lit pixels, to check a tint against its colour."""
    pixels = []
    for image in images:
        luma = image.convert("L").tobytes()
        rgba = image.tobytes()
        for i, l in enumerate(luma):
            r, g, b, a = rgba[4 * i:4 * i + 4]
            if a > 0:
                pixels.append((l, r, g, b))
    pixels.sort(reverse=True)
    top = pixels[:max(1, len(pixels) // 10)]
    return tuple(sum(p[i] for p in top) / len(top) for i in (1, 2, 3))


def main() -> int:
    sources = [Image.open(HERE / SOURCE.format(n)).convert("RGBA") for n in (1, 2)]
    reference = brightest_tenth(sources)
    with SHEET.open(newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["token"] not in OWN_ART]
    for row in rows:
        token, colour = row["token"], hex_colour(row["display_colour"])
        tinted = []
        for n, image in zip((1, 2), sources):
            luma = image.convert("L")
            channels = [luma.point([min(255, round(c * value / reference)) for value in range(256)])
                        for c in colour]
            out = Image.merge("RGBA", channels + [image.getchannel("A")])
            assert out.getchannel("A").tobytes() == image.getchannel("A").tobytes()
            out.save(HERE / TARGET.format(token.lower(), n))
            tinted.append(out)
        measured = brightest_tenth_colour(tinted)
        print(f"{TARGET.format(token.lower(), '{1,2}')} from {SOURCE.format('{1,2}')}: "
              f"#{row['display_colour'].lstrip('#')} -> brightest tenth "
              + "#" + "".join(f"{round(v):02X}" for v in measured))
    return 0


if __name__ == "__main__":
    sys.exit(main())
