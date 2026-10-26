"""The Witch Doctor's class icon: a plain 'WD' in Witch Doctor Green on a dark tile, its own texture on the create screen.

What this proves, and how:

  * **The create screen draws its own file.** GlueXML/CharacterCreate.lua gives the Witch Doctor the whole-texture coordinates
    {0, 1, 0, 1} and names Interface\\Glues\\CharacterCreate\\Torment-WitchDoctor in CLASS_ICON_TEXTURE, the way the Monk and the
    Necromancer are (test_monk_icon.py checks the BLP is 64x64 DXT5 and rebuilt byte for byte from source/witch_doctor.png).
  * **No stock class atlas is shipped.** client-patch/art holds none of the client's three class atlases
    (UI-CharacterCreate-Classes, UI-Classes-Circles, Icons-Classes): a patch file replaces the whole file, so shipping one
    ships the client's own icons with it.
  * **The picture is the plain WD.** The icon decodes to opaque Witch Doctor Green (class_colours.csv's row) in at least a
    hundred pixels, all inside the middle of the tile, over a dark body, with transparent corners.

What it does not prove: how the icon looks in game (the test sheet's checks are the designer's), that the client loads the file, or
the in-game class icon (chat, who, raid), which reads the stock atlases and keeps the Shaman's cell as before.

    python mod-diablocraft/scripts/tests/ui/test_witch_doctor_icon.py
"""

import csv
import importlib.util
import re
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True                  # no __pycache__ beside the art source
REPO = Path(__file__).resolve().parents[4]
ART = REPO / "client-patch" / "art"
KIT = ART / "Interface" / "Glues" / "CharacterCreate" / "source"
spec = importlib.util.spec_from_file_location("build_icon", KIT / "build_icon.py")
build_icon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_icon)             # also puts the vendored Pillow on sys.path
from PIL import Image  # noqa: E402

STOCK_ATLASES = {"ui-charactercreate-classes.blp", "ui-classes-circles.blp", "icons-classes.blp"}
GREEN = (0x4C, 0xDB, 0x3E)


def create_screen():
    return (ART / "Interface" / "GlueXML" / "CharacterCreate.lua").read_text(encoding="utf-8")


class CreateScreen(unittest.TestCase):
    def test_the_witch_doctor_draws_its_own_texture_whole(self):
        text = create_screen()
        coords = re.search(r'CLASS_ICON_TCOORDS = \{(.*?)\n\};', text, re.S).group(1)
        self.assertRegex(coords, r'\["WITCHDOCTOR"\]\s*=\s*\{0, 1, 0, 1\}')
        table = text.split("CLASS_ICON_TEXTURE = {", 1)[1].split("}", 1)[0]
        self.assertRegex(table, r'\["WITCHDOCTOR"\]\s*=\s*"Interface\\\\Glues\\\\CharacterCreate\\\\Torment-WitchDoctor"')

    def test_the_texture_is_one_file_that_build_icon_writes(self):
        self.assertEqual(build_icon.out_path("witch_doctor"), KIT.parent / "Torment-WitchDoctor.blp")
        self.assertTrue(build_icon.out_path("witch_doctor").is_file())
        self.assertIn("witch_doctor", build_icon.CLASSES)


class Shipped(unittest.TestCase):
    def test_no_stock_class_atlas_is_in_the_art(self):
        shipped = {p.name.lower() for p in ART.rglob("*") if p.is_file()} & STOCK_ATLASES
        self.assertEqual(shipped, set())


class Picture(unittest.TestCase):
    def setUp(self):
        self.image = Image.open(build_icon.out_path("witch_doctor")).convert("RGBA")

    def test_the_green_is_the_class_colour(self):
        with (REPO / "mod-diablocraft/data/class_colours.csv").open(encoding="utf-8-sig", newline="") as stream:
            (row,) = [r for r in csv.DictReader(stream) if r["token"] == "WITCHDOCTOR"]
        self.assertEqual(row["hex"].lower().lstrip("#"), "%02x%02x%02x" % GREEN)

    def test_a_plain_wd_in_that_green_on_a_dark_tile(self):
        size = self.image.size[0]
        pixels = self.image.load()
        green = [(x, y) for y in range(size) for x in range(size)
                 if pixels[x, y][3] > 200 and all(abs(a - b) <= 40 for a, b in zip(pixels[x, y][:3], GREEN))]
        self.assertGreater(len(green), 100)
        for x, y in green:
            self.assertTrue(size * 0.05 <= x <= size * 0.95 and size * 0.25 <= y <= size * 0.75, f"green outside the middle at {(x, y)}")
        centre_edge = pixels[size // 2, int(size * 0.12)]
        self.assertEqual(centre_edge[3], 255)
        self.assertLess(sum(centre_edge[:3]), 150, "the tile's body is dark")
        self.assertEqual(pixels[0, 0][3], 0, "the corners are transparent")


if __name__ == "__main__":
    unittest.main()
