#!/usr/bin/env python3
"""The Shaman's Maelstrom orb: a blue centre fading to a subtle purple edge, from the orb pieces the other classes use.

The committed fills are what maelstrom_orb_fill.py makes from the Arcane Power fill today (alpha copied unchanged); the
colour goes from blue in the middle of a frame's disc to purple at its rim, smoothly and not past EDGE_MIX; the shipped
BLPs exist for both sheets; the colour the sheet names for Maelstrom is the mean of the fill's brightest tenth; and the
tint script leaves the hand-made fill alone. A mutant (no purple, all purple, a hard step) must break the gradient check.

    python3 mod-diablocraft/scripts/tests/ui/test_maelstrom_orb_fill.py
"""
from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
KIT = ROOT / "client-patch" / "art" / "ui" / "elvui"
MEDIA = ROOT / "client-patch" / "addons" / "ElvUI_Torment" / "media"
sys.path.insert(0, str(KIT))
import maelstrom_orb_fill as fill  # noqa: E402  (also puts the vendored Pillow on sys.path)
import tint_orb_fills  # noqa: E402
from PIL import Image  # noqa: E402

SOURCES = [Image.open(KIT / fill.SOURCE.format(n)).convert("RGBA") for n in (1, 2)]
LMAX = max(image.convert("L").getextrema()[1] for image in SOURCES)


def ring_mean(image: Image.Image, low: float, high: float) -> tuple[float, float, float]:
    """The mean colour of the lit pixels between two distances from the disc's middle (shares of its radius), all 30 cells."""
    total, count = [0.0, 0.0, 0.0], 0
    for cell in range(fill.COLUMNS * fill.ROWS):
        left, top = (cell % fill.COLUMNS) * fill.CELL, (cell // fill.COLUMNS) * fill.CELL
        data = image.crop((left, top, left + fill.CELL, top + fill.CELL))
        for y in range(fill.CELL):
            for x in range(fill.CELL):
                distance = (((x + 0.5 - fill.CENTRE) ** 2 + (y + 0.5 - fill.CENTRE) ** 2) ** 0.5) / fill.RADIUS
                r, g, b, a = data.getpixel((x, y))
                if low <= distance < high and a == 255:
                    total = [total[0] + r, total[1] + g, total[2] + b]
                    count += 1
    return tuple(v / count for v in total)


def purpleness(colour: tuple[float, float, float]) -> float:
    """Red over blue: a blue is low, a purple higher."""
    return colour[0] / colour[2]


class Fill(unittest.TestCase):
    def test_the_committed_fills_are_what_the_script_makes(self):
        for n, source in zip((1, 2), SOURCES):
            made = fill.tint(source, LMAX)
            committed = Image.open(KIT / fill.TARGET.format(n)).convert("RGBA")
            self.assertEqual(made.tobytes(), committed.tobytes(), f"run maelstrom_orb_fill.py ({n})")
            self.assertEqual(committed.getchannel("A").tobytes(), source.getchannel("A").tobytes(), "alpha is the source's")

    def test_blue_in_the_middle_purple_at_the_rim_and_blue_overall(self):
        image = Image.open(KIT / fill.TARGET.format(1)).convert("RGBA")
        middle, rim = ring_mean(image, 0.0, 0.4), ring_mean(image, 0.9, 1.0)
        self.assertGreater(middle[2], middle[0] * 2, "the middle is blue: " + str(middle))
        self.assertGreater(middle[2], middle[1], "the middle is blue, not green or cyan: " + str(middle))
        self.assertGreater(purpleness(rim), purpleness(middle) * 1.25, f"the rim is purpler: {middle} -> {rim}")
        self.assertGreater(rim[2], rim[0], "the rim is still blue-leaning (a subtle purple, not magenta): " + str(rim))

    def test_the_gradient_is_smooth_and_capped(self):
        steps = [fill.edge_mix(d / 20) for d in range(0, 21)]
        self.assertEqual(steps[0], 0)
        self.assertAlmostEqual(steps[-1], fill.EDGE_MIX)
        self.assertTrue(all(a <= b for a, b in zip(steps, steps[1:])), "never less purple further out")
        self.assertTrue(all(b - a < fill.EDGE_MIX / 4 for a, b in zip(steps, steps[1:])), "no hard step")
        self.assertLessEqual(fill.EDGE_MIX, 0.6, "a subtle purple")

    def test_a_mutant_without_the_purple_or_with_all_of_it_is_caught(self):
        keep = fill.EDGE_MIX
        try:
            image = Image.open(KIT / fill.TARGET.format(1)).convert("RGBA")
            real = ring_mean(image, 0.9, 1.0)
            fill.EDGE_MIX = 0.0
            plain = fill.tint(SOURCES[0], LMAX)
            self.assertLess(purpleness(ring_mean(plain, 0.9, 1.0)), purpleness(real) / 1.2, "no purple is caught")
            fill.EDGE_MIX = 1.0
            full = fill.tint(SOURCES[0], LMAX)
            self.assertGreater(purpleness(ring_mean(full, 0.9, 1.0)), purpleness(real) * 1.2, "all purple is caught")
        finally:
            fill.EDGE_MIX = keep


class Shipped(unittest.TestCase):
    def test_both_blps_ship(self):
        for n in (1, 2):
            path = MEDIA / f"orb_fill_maelstrom_{n}.blp"
            self.assertTrue(path.is_file() and path.read_bytes()[:4] == b"BLP2", str(path))

    def test_the_sheet_colour_is_the_fills_brightest_tenth(self):
        with open(ROOT / "mod-diablocraft/data/tunables/class_resources.csv", newline="", encoding="utf-8") as handle:
            row = next(r for r in csv.DictReader(handle) if r["token"] == "MAELSTROM")
        images = [Image.open(KIT / fill.TARGET.format(n)).convert("RGBA") for n in (1, 2)]
        measured = "#" + "".join(f"{round(v):02X}" for v in tint_orb_fills.brightest_tenth_colour(images))
        self.assertEqual(row["display_colour"], measured)

    def test_the_tint_script_keeps_its_hands_off_the_hand_made_fill(self):
        self.assertIn("MAELSTROM", tint_orb_fills.OWN_ART)


if __name__ == "__main__":
    unittest.main()
