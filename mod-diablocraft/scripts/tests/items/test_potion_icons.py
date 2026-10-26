"""Potion icons (diablocraft-71scy): every potion row has an icon in the patch, and each potion item wears its own.

    python3 mod-diablocraft/scripts/tests/items/test_potion_icons.py

Every legendary_potions.csv row names an icon whose BLP (holding its committed crop) is in client-patch/art and in
the committed patch-4.MPQ, and so does the plain Health Potion's DC_Potion_HealthPotion. Every row is an item
(potion_icons.csv; diablocraft-0knhj built the other ten after Regeneration, 102200) with a display row naming its
row's icon in ItemDisplayInfo.dbc, that display on its Item.dbc row and in the migration, and nothing else wears
DC_Potion_. The migration's item, base and tooltip rows are read back against the sheet, and no loot, vendor or kit
file names a potion: they drop through the world's legendary pool alone (diablocraft-pymfu, as D3's legendary potions):
each base row, read back from the migration, is driven through the production pool rules (dc_roll_class.h InDropPool and
DropEligible) for every class of class_map.csv, and Kadala sells none (D3's Kadala has no potion).

Not run here: the client's own decoding of a BLP (no client; the payload is compared to what build_ui_art.py
writes), the crop from the designer's sheets (they live in the brief's scratch folder; the crops are the committed source),
and the bar's potion slot, which is a spell button and keeps its spell icon (diablocraft-g8jnj).
"""
from __future__ import annotations

import csv
import importlib.util
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
KIT = ROOT / "client-patch/source/potions"
DBC = ROOT / "client-patch/dbc"
POTIONS = ROOT / "mod-diablocraft/data/d3/legendary_potions.csv"

sys.path.insert(0, str(KIT))
import draw_potion_icons as art  # noqa: E402  (also puts the vendored Pillow on sys.path)
import generate_potion_icons as gen  # noqa: E402
from dbc_store import Store, schema  # noqa: E402
from PIL import Image  # noqa: E402


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sheet_icons() -> dict[str, str]:
    with POTIONS.open(encoding="utf-8-sig", newline="") as stream:
        return {row["d3_id"]: row["icon"] for row in csv.DictReader(stream)}


class TheIcons(unittest.TestCase):
    """Every potion row and the plain Health Potion have their own icon, crop and BLP."""

    def test_every_potion_row_has_its_own_icon(self):
        icons = sheet_icons()
        self.assertEqual(len(icons), 11)
        for d3_id, icon in icons.items():
            self.assertEqual(icon, f"DC_Potion_{d3_id}")
        self.assertEqual(set(art.POTIONS), set(icons) | {"HealthPotion"}, "a sheet cell for every potion")
        self.assertEqual({path.stem for path in art.PNG.glob("*.png")},
                         set(icons.values()) | {"DC_Potion_HealthPotion"}, "a crop for every icon and no other")

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
                             f"{png.stem}.blp does not hold its PNG - rerun draw_potion_icons.py")


class TheClientRows(unittest.TestCase):
    """The item points at the display, the display names its row's icon, and the server gets the same displayid."""

    @classmethod
    def setUpClass(cls):
        cls.potions = gen.rows()
        cls.items = Store((DBC / "Item.dbc").read_bytes(), schema(ROOT, "item_dbc"))
        cls.displays = Store((DBC / "ItemDisplayInfo.dbc").read_bytes(), schema(ROOT, "itemdisplayinfo_dbc"))

    def test_every_sheet_row_is_an_item_with_its_rows_icon(self):
        icons = sheet_icons()
        self.assertEqual(len(self.potions), len(icons))
        self.assertEqual({p["d3_id"] for p in self.potions}, set(icons))
        for p in self.potions:
            self.assertEqual(p["icon"], icons[p["d3_id"]])
        regeneration = next(p for p in self.potions if p["d3_id"] == "HealthPotionLegendary_03")
        self.assertEqual((regeneration["entry"], regeneration["display"]), (102200, 90300), "Regeneration keeps its ids")

    def test_each_potion_item_shows_its_icon(self):
        for p in self.potions:
            entry, display, icon = p["entry"], p["display"], p["icon"]
            self.assertEqual(self.items.decode(entry), {"ID": entry, "ClassID": 0, "SubclassID": 1,
                                                        "Sound_Override_Subclassid": -1, "Material": 3,
                                                        "DisplayInfoID": display, "InventoryType": 0,
                                                        "SheatheType": 0}, "a potion row, the server's class")
            row = self.displays.decode(display)
            self.assertEqual(row["InventoryIcon_1"], icon, display)
            self.assertEqual(row["ModelName_1"], "", "an inventory icon only, no model")

    def test_the_display_rows_are_exactly_the_potion_items(self):
        ours = {key for key in self.displays.rows
                if self.displays.decode(key)["InventoryIcon_1"].startswith("DC_Potion_")}
        self.assertEqual(ours, {p["display"] for p in self.potions})

    def test_the_committed_files_are_the_generators_render(self):
        item_dbc, display_dbc = gen.client_dbcs(self.potions)
        self.assertEqual((DBC / "Item.dbc").read_bytes(), item_dbc, "Item.dbc is stale - rerun generate_potion_icons.py")
        self.assertEqual((DBC / "ItemDisplayInfo.dbc").read_bytes(), display_dbc)
        self.assertEqual(gen.MIGRATION.read_text(encoding="utf-8"), gen.world_sql(self.potions))

    def test_a_render_from_build_items_row_gives_the_committed_files(self):
        # build_item.py appends Regeneration with display 24152, and the other ten have no row before the
        # generator: it must set ours over the first and append the rest.
        build_item = load(DBC / "build_item.py", "build_item")
        items = Store((DBC / "Item.dbc").read_bytes(), schema(ROOT, "item_dbc"))
        for p in self.potions:
            if p["entry"] in build_item.HAND_WRITTEN:
                items.encode({**items.decode(p["entry"]), "DisplayInfoID": build_item.HAND_WRITTEN[p["entry"]][4]})
            else:
                del items.rows[p["entry"]]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Item.dbc").write_bytes(items.bytes())
            (Path(tmp) / "ItemDisplayInfo.dbc").write_bytes((DBC / "ItemDisplayInfo.dbc").read_bytes())
            client, gen.CLIENT = gen.CLIENT, Path(tmp)
            try:
                item_dbc, _ = gen.client_dbcs(self.potions)
            finally:
                gen.CLIENT = client
        # Rows, not file order: the generator leaves a row where it is and appends the new ones, so the committed file
        # keeps the order the beads appended in (the ten potions, then the Monk caches 101146-51 and 102013), while this
        # render, which removed the potion rows first, appends them last.
        schema_item = schema(ROOT, "item_dbc")
        rendered, committed = Store(item_dbc, schema_item), Store((DBC / "Item.dbc").read_bytes(), schema_item)
        self.assertEqual(rendered.rows, committed.rows)
        self.assertEqual(rendered.block, committed.block)

    def test_the_migration_runs_after_the_item_is_written(self):
        # The core applies updates in filename order; a later INSERT of the item would put display 24152 back.
        entries = "|".join(str(p["entry"]) for p in self.potions)
        for path in gen.MIGRATION.parent.glob("*.sql"):
            text = path.read_text(encoding="utf-8")
            if (path != gen.MIGRATION and re.search(r"(INSERT|REPLACE) INTO `?item_template", text)
                    and re.search(rf"\b({entries})\b", text)):
                self.assertLess(path.name, gen.MIGRATION.name, f"{path.name} writes a potion item after the icons")

    def test_the_migration_writes_each_sheet_row(self):
        # Read back from the committed SQL, not from the generator's own values.
        sql = gen.MIGRATION.read_text(encoding="utf-8")
        with POTIONS.open(encoding="utf-8-sig", newline="") as stream:
            sheet = {row["d3_id"]: row for row in csv.DictReader(stream)}
        for p in self.potions:
            row, entry = sheet[p["d3_id"]], p["entry"]
            item = re.search(rf"^\({entry}, 0, 1, '((?:[^']|'')*)', {p['display']}, 5, 0, 1, 0, 0, 0, 0, 1, 3, 0, "
                             rf"{row['required_level']}, {row['required_level']}, ", sql, re.M)
            self.assertIsNotNone(item, f"{entry}: a legendary potion item, level {row['required_level']}")
            self.assertEqual(item[1].replace("''", "'"), row["name"])
            base = re.search(rf"^\({entry}, '{p['d3_id']}', '[^\n]*', 'potion', 'Potion', 'legendary', "
                             rf"'', {row['required_level']}, {row['required_level']}, NULL, NULL, NULL, '', '', "
                             rf"'legendary_potions.csv', 'yes', '', 'no'\)[,;]$", sql, re.M)
            self.assertIsNotNone(base, f"{entry}: dc_base_item slot 'potion', pool_version 'yes'")
            tooltip = re.search(rf"^\('{p['d3_id']}', '', ((?:'(?:[^']|'')*'|CONVERT\(X'[0-9a-f]*' USING utf8mb4\))), ",
                                sql, re.M)
            self.assertIsNotNone(tooltip, f"{p['d3_id']}: its tooltip row")
            power = row["power_text"].replace("%%", "%")
            if row["roll_min"]:
                power = power.replace("%d", f"{row['roll_min']}–{row['roll_max']}")
            self.assertNotIn("%d", power)
            self.assertEqual(tooltip[1], f"'{power.replace(chr(39), chr(39) * 2)}'", "the power line with its range")
        self.assertIn("Increases Armor by 10–20% for 5 seconds.", sql)
        self.assertIn("Restores an additional 75000–100000 Life over 5 seconds.", sql)

    def test_every_potion_drops_from_the_world_legendary_pool(self):
        # diablocraft-pymfu: the pool rules every drop source reads (dc_loot.cpp loads dc_base_item through InDropPool and
        # picks through DropEligible), compiled as they are and fed each potion's base row as the migration writes it.
        sql = gen.MIGRATION.read_text(encoding="utf-8")
        block = re.search(r"INSERT INTO `dc_base_item`\s*\((.*?)\)\s*VALUES\s*(.*?);\n", sql, re.S)
        columns = [c.strip().strip("`") for c in block[1].split(",")]
        rows = {}
        for line in block[2].splitlines():
            values = next(csv.reader([line.strip().rstrip(",")[1:-1]], quotechar="'", skipinitialspace=True))
            rows[int(values[0])] = dict(zip(columns, (v.strip() for v in values)))
        self.assertEqual(sorted(rows), sorted(p["entry"] for p in self.potions))
        with (ROOT / "mod-diablocraft/data/d3/class_map.csv").open(encoding="utf-8-sig", newline="") as stream:
            classes = [r["d3_class"].lower() for r in csv.DictReader(stream)]
        self.assertTrue(classes)
        header = (ROOT / "mod-diablocraft/src/items/dc_roll_class.h").read_text(encoding="utf-8")
        signature = header[header.index("inline bool InDropPool("):]
        cache = ', "no"' if signature[:signature.index(")")].count(",") == 3 else ""   # nightly's fourth: the cache's own
        calls = []
        for entry, row in sorted(rows.items()):
            calls.append(f'std::printf("%d", DC::RollClass::InDropPool("{row["rarity"]}", "{row["pool_version"]}", '
                         f'"{row["craft_only"]}"{cache}) ? 1 : 0);')
            calls += [f'std::printf("%d", DC::RollClass::DropEligible("{row["usable_by"]}", "{row["designated_class"]}", '
                      f'"{row["set_name"]}", "{c}") ? 1 : 0);' for c in classes]
        code = ('#include "dc_roll_class.h"\n#include <cstdio>\nint main()\n{\n    ' + "\n    ".join(calls) + '\n}\n')
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pool.cpp").write_text(code, encoding="utf-8")
            built = subprocess.run(["c++", "-std=c++17", "-I", str(ROOT / "mod-diablocraft/src/items"), "pool.cpp", "-o", "pool"],
                                   cwd=tmp, capture_output=True, text=True)
            self.assertEqual(0, built.returncode, built.stderr[-3000:])
            ran = harness_env.run([str(Path(tmp) / "pool")], capture_output=True, text=True)
        self.assertEqual(ran.stdout, "1" * len(rows) * (1 + len(classes)), "a potion the pool or a class cannot drop")
        for entry, row in rows.items():   # legendary, the sheet's level (the drop's level gate reads item_level)
            self.assertEqual((row["rarity"], row["slot"]), ("legendary", "potion"), entry)
        kadala = "".join((ROOT / "mod-diablocraft/data/d3" / name).read_text(encoding="utf-8").lower()
                         for name in ("kadala.csv", "kadala_entries.csv"))
        self.assertNotIn("potion", kadala, "Kadala sells no potion in D3")

    def test_no_loot_vendor_or_kit_file_names_a_potion(self):
        # No route of its own: the legendary pool above is the only way in (the generator's own files, the frozen
        # Regeneration migrations and the tests aside).
        allowed = {gen.MIGRATION.name, "items_0015_bottomless_potion.sql", "items_0023_potion_icons.sql",
                   "potion_icons.csv", "dc_potion.h", "dc_potion_table.h", "build_item.py", "generate/items/generate_potion_icons.py",
                   "tests/items/test_potion_icons.py", "tests/items/test_bottomless_potion.py", "tests/items/test_bottomless_potion.lua"}
        entries = re.compile(r"\b(" + "|".join(str(p["entry"]) for p in self.potions) + r")\b")
        for path in (ROOT / "mod-diablocraft").rglob("*"):
            if (path.is_file() and path.name not in allowed and not path.name.startswith("test_")
                    and path.suffix in (".sql", ".csv", ".lua", ".cpp", ".h", ".py", ".json")):
                found = entries.search(path.read_text(encoding="utf-8", errors="ignore"))
                self.assertIsNone(found, f"{path.relative_to(ROOT)} names potion {found and found[0]}")

    def test_the_committed_archive_carries_the_display_rows_and_the_icons(self):
        icons = [f"Interface/Icons/{path.stem}.blp" for path in sorted(art.PNG.glob("*.png"))]
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["smpq", "-x", str(ROOT / "client-patch/patch-4.MPQ"), "DBFilesClient/ItemDisplayInfo.dbc", *icons],
                           cwd=tmp, check=True, capture_output=True)   # Item.dbc in the archive is test_kadala_client_rows's check
            for name in ("ItemDisplayInfo.dbc",):
                self.assertEqual((Path(tmp) / "DBFilesClient" / name).read_bytes(), (DBC / name).read_bytes(), name)
            for icon in icons:
                self.assertEqual((Path(tmp) / icon).read_bytes(), (ROOT / "client-patch/art" / icon).read_bytes(), icon)


if __name__ == "__main__":
    unittest.main()
