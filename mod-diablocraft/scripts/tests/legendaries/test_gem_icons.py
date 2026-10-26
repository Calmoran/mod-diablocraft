"""Gem icons (diablocraft-fpo9l): every gem item wears its own icon, and the icon is in the patch.

    python3 mod-diablocraft/scripts/tests/legendaries/test_gem_icons.py

Kept from diablocraft-fdyr's test (never merged): the five colours and ten tiers are the game's gem table's,
the shift does what its table says without pinning the designer's numbers, the committed colour icons are what the
shift makes of the committed ruby crops, and each BLP holds its PNG. New: each gem item (gem_items.csv and
legendary_gem_items.csv, every one socketable) has an icon file, a display row naming it in ItemDisplayInfo.dbc,
that display on its Item.dbc row and in the migration, and the committed patch-4.MPQ carries all of it.

Not run here: the client's own decoding of a BLP (no client; the payload is compared to what build_ui_art.py
writes), and the crop from the designer's sheets (the sheets live in the brief's scratch folder; the crops are the
committed source).
"""
from __future__ import annotations

import colorsys
import csv
import importlib.util
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
KIT = ROOT / "client-patch/source/gems"
DBC = ROOT / "client-patch/dbc"
GEM_TABLE = ROOT / "mod-diablocraft/data/d3/gems.csv"

sys.path.insert(0, str(KIT))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import draw_gem_icons as art  # noqa: E402  (also puts the vendored Pillow on sys.path)
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_gem_icons as gen  # noqa: E402
from dbc_store import Store, schema  # noqa: E402
from PIL import Image  # noqa: E402


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hue_of(pixel) -> float:
    return colorsys.rgb_to_hls(*(channel / 255.0 for channel in pixel[:3]))[0] * 360.0


def hue_gap(left: float, right: float) -> float:
    return min((left - right) % 360.0, (right - left) % 360.0)


class TheGemTable(unittest.TestCase):
    """The five colours and ten tiers are the game's own gem table, and every gem item has a row."""

    def test_the_colours_and_tiers_are_the_tables(self):
        colours, tiers = set(), set()
        with GEM_TABLE.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["is_legendary"] == "0":
                    colours.add(row["colour"])
                    tiers.add(row["tier"])
        self.assertEqual(set(art.GEM_COLOURS), colours)
        self.assertEqual(set(art.tiers()), tiers)
        self.assertEqual(len(art.tiers()), 10, "the ruby sheet has ten cells")

    def test_every_gem_item_has_an_icon_and_its_file(self):
        gems = gen.rows()   # refuses a gem item without a row, a duplicate, or a missing BLP
        self.assertEqual(len(gems), 71)
        for entry, display, icon in gems:
            self.assertTrue((art.ICONS / f"{icon}.blp").is_file(), icon)
            self.assertTrue((art.PNG / f"{icon}.png").is_file(), icon)
        self.assertEqual({path.stem for path in art.PNG.glob("*.png")}, {icon for _, _, icon in gems},
                         "an icon no gem item wears, or a gem item with no source crop")

    def test_each_item_wears_its_own_gems_icon(self):
        icon = {entry: name for entry, _, name in gen.rows()}
        colour = {}
        with GEM_TABLE.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                colour[row["gem_id"]] = row["colour"]
        with (ROOT / "mod-diablocraft/data/gem_items.csv").open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                self.assertEqual(icon[int(row["item_entry"])], art.stat_name(colour[row["gem_id"]], row["tier"]))
        names = {gem_id: name for name, gem_id in art.legendary_ids().items()}
        with (ROOT / "mod-diablocraft/data/legendary_gem_items.csv").open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                self.assertEqual(icon[int(row["item_entry"])], f"DC_Gem_{row['gem_id']}")
                self.assertIn(names[row["gem_id"]], art.LEGENDARY, "no square on the designer's sheets")


class TheColourShift(unittest.TestCase):
    """The hue is turned, saturation and lightness scaled, and the dark ground left alone."""

    STONE = (200, 70, 40, 255)      # a lit ruby facet running orange: hue 11, lightness 0.47
    GROUND = (30, 8, 6, 255)        # the sheet's red-brown ground: lightness 0.07

    def shifted(self, pixel, hue, sat=1.0, light=1.0):
        return art.shift(Image.new("RGBA", (1, 1), pixel), hue, sat, light).getpixel((0, 0))

    def test_every_colour_turns_the_stone_by_its_own_hue(self):
        for colour, value in art.GEM_COLOURS.items():
            pixel = self.shifted(self.STONE, value["hue"], 1.0, 1.0)
            self.assertLess(hue_gap(hue_of(pixel), (hue_of(self.STONE) + value["hue"]) % 360.0), 2.0, colour)

    def test_the_ground_keeps_its_colour(self):
        for colour, value in art.GEM_COLOURS.items():
            self.assertEqual(self.shifted(self.GROUND, value["hue"], value["sat"], value["light"]), self.GROUND,
                             f"{colour} recoloured the background")

    def test_light_scales_lightness_and_saturation_scales_saturation(self):
        def hls(pixel):
            return colorsys.rgb_to_hls(*(channel / 255.0 for channel in pixel[:3]))
        self.assertLess(hls(self.shifted(self.STONE, 0, 1.0, 0.8))[1], hls(self.shifted(self.STONE, 0, 1.0, 1.3))[1])
        self.assertLess(hls(self.shifted(self.STONE, 0, 0.0, 1.0))[2], 0.02, "saturation x0 must leave grey")


class TheCommittedIcons(unittest.TestCase):
    """What is committed is what the ruby crops and the table make, and it shipped as BLP."""

    def test_every_colour_icon_is_current(self):
        for tier in art.tiers():
            ruby = Image.open(art.PNG / f"{art.stat_name('Ruby', tier)}.png")
            self.assertEqual(ruby.size, (64, 64))
            for colour, value in art.GEM_COLOURS.items():
                if colour == "Ruby":
                    continue
                committed = Image.open(art.PNG / f"{art.stat_name(colour, tier)}.png").convert("RGBA")
                fresh = art.shift(ruby, value["hue"], value["sat"], value["light"])
                self.assertEqual(fresh.tobytes(), committed.tobytes(),
                                 f"{art.stat_name(colour, tier)} is stale - rerun draw_gem_icons.py")

    def test_every_icon_shipped_a_blp_holding_it(self):
        builder = load(ROOT / "client-patch/build_ui_art.py", "build_ui_art")
        for png in sorted(art.PNG.glob("*.png")):
            data = (art.ICONS / f"{png.stem}.blp").read_bytes()
            magic, kind = struct.unpack_from("<4sI", data, 0)
            encoding, depth, alpha_type, _ = struct.unpack_from("<BBBB", data, 8)
            width, height = struct.unpack_from("<II", data, 12)
            offsets = struct.unpack_from("<16I", data, 20)
            sizes = struct.unpack_from("<16I", data, 84)
            self.assertEqual((magic, kind, encoding, depth, alpha_type, width, height),
                             (b"BLP2", 1, 2, 8, 7, 64, 64), f"{png.stem} is not a 64x64 DXT5 BLP2")
            self.assertEqual(data[offsets[0]:offsets[0] + sizes[0]], builder.dxt5(Image.open(png).convert("RGBA")),
                             f"{png.stem}.blp does not hold its PNG - rerun draw_gem_icons.py")


class TheClientRows(unittest.TestCase):
    """The item points at the display, the display names the icon, and the server gets the same displayid."""

    @classmethod
    def setUpClass(cls):
        cls.gems = gen.rows()
        cls.items = Store((DBC / "Item.dbc").read_bytes(), schema(ROOT, "item_dbc"))
        cls.displays = Store((DBC / "ItemDisplayInfo.dbc").read_bytes(), schema(ROOT, "itemdisplayinfo_dbc"))

    def test_each_gem_item_shows_its_icon(self):
        for entry, display, icon in self.gems:
            self.assertEqual(self.items.decode(entry)["DisplayInfoID"], display, entry)
            row = self.displays.decode(display)
            self.assertEqual(row["InventoryIcon_1"], icon, display)
            self.assertEqual(row["ModelName_1"], "", "an inventory icon only, no model")

    def test_the_display_rows_are_exactly_the_gems(self):
        ours = {key for key in self.displays.rows if self.displays.decode(key)["InventoryIcon_1"].startswith("DC_Gem_")}
        self.assertEqual(ours, {display for _, display, _ in self.gems})

    def test_the_committed_files_are_the_generators_render(self):
        item_dbc, display_dbc = gen.client_dbcs(self.gems)
        self.assertEqual((DBC / "Item.dbc").read_bytes(), item_dbc, "Item.dbc is stale - rerun generate_gem_icons.py")
        self.assertEqual((DBC / "ItemDisplayInfo.dbc").read_bytes(), display_dbc)
        migration = gen.MIGRATION.read_text(encoding="utf-8")
        self.assertEqual(migration, gen.world_sql(self.gems))
        updates = {(int(e), int(d)) for d, e in re.findall(r"`displayid`=(\d+) WHERE `entry`=(\d+);", migration)}
        self.assertEqual(updates, {(entry, display) for entry, display, _ in self.gems})

    def test_the_migration_runs_after_every_render_of_the_gem_rows(self):
        # The core applies updates in filename order; a donor's REPLACE after ours would put the donor look back.
        entries = "|".join(str(entry) for entry, _, _ in self.gems)
        for path in gen.MIGRATION.parent.glob("*.sql"):
            text = path.read_text(encoding="utf-8")
            if path != gen.MIGRATION and "REPLACE INTO item_template" in text and re.search(rf"\b({entries})\b", text):
                self.assertLess(path.name, gen.MIGRATION.name, f"{path.name} re-renders gem rows after the icons")

    def test_the_committed_archive_carries_the_rows_and_the_icons(self):
        icons = [f"Interface/Icons/{icon}.blp" for _, _, icon in self.gems]
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["smpq", "-x", str(ROOT / "client-patch/patch-4.MPQ"), "DBFilesClient/Item.dbc",
                            "DBFilesClient/ItemDisplayInfo.dbc", *icons], cwd=tmp, check=True, capture_output=True)
            for name in ("Item.dbc", "ItemDisplayInfo.dbc"):
                self.assertEqual((Path(tmp) / "DBFilesClient" / name).read_bytes(), (DBC / name).read_bytes(), name)
            for icon in icons:
                self.assertEqual((Path(tmp) / icon).read_bytes(), (ROOT / "client-patch/art" / icon).read_bytes(), icon)


if __name__ == "__main__":
    unittest.main()
