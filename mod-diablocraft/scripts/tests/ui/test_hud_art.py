#!/usr/bin/env python3
"""The shipped hotbar's slot geometry lands on the art's own openings (diablocraft-lhoeu).

Cross-source: the numbers in Torment's `Diablocraft.ART["bar"]` (ArtSlots.lua) are read back into
pixels of the cut `hud_bar.png` and checked against its alpha: every well and the micro opening is a
hole framed by opaque art, each orb centre is a hole inside an opaque ring, the XP channel is opaque.
And the PNG is what cut_hotbar_art.py makes from the sheet today.

    python3 mod-diablocraft/scripts/tests/ui/test_hud_art.py
"""
from __future__ import annotations

import math
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
KIT = ROOT / "client-patch" / "art" / "ui" / "elvui"
sys.path.insert(0, str(KIT))
import cut_hotbar_art as cut  # noqa: E402  (also puts the vendored Pillow on sys.path)
from PIL import Image  # noqa: E402

LUA = ROOT / "client-patch" / "addons" / "Torment" / "ArtSlots.lua"


def bar_slot() -> str:
    source = LUA.read_text()
    start = source.index('["bar"]')
    return source[start:source.index('["bar-buttons"]', start)]


def rects(text: str) -> list[dict]:
    return [{k: float(v) for k, v in re.findall(r"(\w+) = ([\d.]+)", m)}
            for m in re.findall(r"\{(left = [^}]*)\}", text)]


def to_px(value: float, origin: int) -> float:
    return value / cut.K + origin


class HudArt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slot = bar_slot()
        cls.image = Image.open(KIT / "hud_bar.png")
        cls.alpha = cls.image.getchannel("A").load()

    def a(self, x: float, y: float) -> int:
        return self.alpha[int(x - cut.CROP[0]), int(y - cut.CROP[1])]

    def opening(self, rect: dict, grow: float, name: str):
        left = to_px(rect["left"] + grow, cut.CROP[0])
        top = to_px(rect["top"] + grow, cut.CROP[1])
        right = left + (rect["width"] - 2 * grow) / cut.K
        bottom = top + (rect["height"] - 2 * grow) / cut.K
        for fx in (0.1, 0.5, 0.9):
            for fy in (0.1, 0.5, 0.9):
                x, y = left + fx * (right - left), top + fy * (bottom - top)
                self.assertEqual(self.a(x, y), 0, f"{name}: a hole at ({x:.0f}, {y:.0f})")
        mx, my = (left + right) / 2, (top + bottom) / 2
        for x, y in ((left - 4, my), (right + 4, my), (mx, top - 4), (mx, bottom + 4)):
            self.assertEqual(self.a(x, y), 255, f"{name}: framed by opaque art at ({x:.0f}, {y:.0f})")

    def test_every_well_is_an_opening(self):
        wells = rects(self.slot[self.slot.index("wells"):self.slot.index("micro")])
        self.assertEqual(len(wells), 8)
        for index, well in enumerate(wells, 1):
            self.opening(well, cut.GROW, f"well {index}")

    def test_micro_is_an_opening(self):
        micro = rects(self.slot[self.slot.index("micro ="):self.slot.index("globeWells")])
        self.assertEqual(len(micro), 1)
        self.opening(micro[0], 0, "micro")

    def test_orbs_sit_in_their_holes(self):
        # Rim checks on the lower side clear of the figure and the shine: down-right for the health orb
        # (the demon is down-left), down-left for the power orb (the angel is down-right).
        sides = {"health": (30, 45, 90), "power": (90, 135, 150)}
        for name, angles in sides.items():
            found = re.search(name + r" *= \{centreX = ([\d.]+), centreY = ([\d.]+), diameter = ([\d.]+)\}",
                              self.slot)
            cx, cy, d = (float(v) for v in found.groups())
            x, y = to_px(cx, cut.CROP[0]), to_px(cy, cut.CROP[1])
            hole = to_px(d, 0) * cut.RING_INNER / 2 - cut.OVERLAP
            # Light-keyed inside the hole (the shine stays as a highlight), so the sheet's black is a
            # few levels of JPEG noise, not exactly 0.
            self.assertLessEqual(self.a(x, y), 8, f"{name}: the orb centre is a hole")
            self.assertEqual(self.a(x, y - hole - 4), 255, f"{name}: the ring over the hole is opaque")
            for angle in angles:
                c, s_ = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                self.assertLessEqual(self.a(x + (hole - 6) * c, y + (hole - 6) * s_), 8,
                                     f"{name}: the hole runs to the ring at {angle} degrees")
                self.assertEqual(self.a(x + (hole + 4) * c, y + (hole + 4) * s_), 255,
                                 f"{name}: the ring is opaque at {angle} degrees")

    def test_xp_channel_is_opaque(self):
        strip = rects(self.slot[self.slot.index("strip"):])[0]
        y = to_px(strip["top"] + strip["height"] / 2, cut.CROP[1])
        left = to_px(strip["left"], cut.CROP[0])
        for f in (0.05, 0.25, 0.75, 0.95):
            x = left + f * strip["width"] / cut.K
            self.assertEqual(self.a(x, y), 255, f"the XP channel is opaque at {x:.0f}")

    def test_slot_numbers_are_the_scripts(self):
        geometry = cut.geometry()
        for index, well in enumerate(rects(self.slot[self.slot.index("wells"):self.slot.index("micro")])):
            self.assertEqual(well, {k: float(v) for k, v in geometry["wells"][index].items()}, f"well {index + 1}")
        self.assertIn(f"width = {geometry['width']}, height = {geometry['height']}", self.slot)
        self.assertTrue(math.isclose(cut.K * 1332, 936))

    def test_png_is_todays_cut(self):
        fresh = cut.bar(Image.open(cut.SHEET).convert("RGB"))
        self.assertEqual(fresh.tobytes(), self.image.convert("RGBA").tobytes())


if __name__ == "__main__":
    unittest.main()
