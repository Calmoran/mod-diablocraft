"""diablocraft-rclu6: Kanai's Cube never takes Ancestors' Grace (D3 marks its power `cube: false`).

D3's rule: d3planner's item data (reference/d3planner/item_neck.js, the `leg_ancestorsgrace` custom affix) carries `cube: false`, and
the power's own text is "This item is destroyed in the process", so a Cube copy has no item to destroy and the revive does nothing.
Kanai's Cube refuses it: it is not listed, cannot be chosen for a slot and cannot be extracted (the Archive refuses an unlisted
power: test_cube_extract.py). The one item list is data/d3/cube_excluded.csv, rendered by generate_cube.py into cube_0003_excluded.sql
and read by dc_cube.cpp's CubePowerItems.

What this proves:
  * Cross-source: the sheet holds exactly the items d3planner marks `cube: false` (Ancestors' Grace and Corrupted Ashbringer), read
    from the planner's own files, not from this sheet or a copy of its ids.
  * The generator: cube_0003 and its mirror are the render of the sheet, and it refuses an item that is not a legendary of
    base_items.csv, a repeat, and a row with no reason or source.
  * The query: CubePowerItems carries the exclusion (the DB replay in test_cube_grid.py runs it on the real tables and mutates it:
    Ancestors' Grace is built, so without the line it is listed in the Jewelry slot).
  * NOT covered: a Cube click in the game (the designer's Checks, docs/test-diablocraft-rclu6.md).
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_cube as G
from test_cube import CRAFTING, UPDATES, read_csv

PLANNER = G.ROOT / "reference/d3planner"


def planner_cube_false():
    """Every item id of d3planner's item files whose custom affix says `cube: false`."""
    found = set()
    for path in sorted(PLANNER.glob("item_*.js")):
        text = path.read_text(encoding="utf-8")
        starts = [(m.start(), m.group(1)) for m in re.finditer(r'^    id: "(\w+)"', text, re.M)]
        for flag in re.finditer(r"cube:\s*false", text):
            owner = [item for at, item in starts if at < flag.start()]
            found.add(owner[-1])
    return found


class Excluded(unittest.TestCase):
    def test_the_sheet_is_the_items_d3_marks_cube_false(self):
        marked = planner_cube_false()
        self.assertEqual(marked, {"Unique_Amulet_102_x1", "Unique_Sword_2H_104_x1"})  # the reading finds both, so it reads the files
        self.assertEqual({d3_id for d3_id, _ in G.excluded()}, marked)

    def test_ancestors_grace_is_a_built_pool_legendary_that_the_sheet_keeps_out(self):
        row = [r for r in read_csv(G.DATA / "base_items.csv") if r["d3_id"] == "Unique_Amulet_102_x1"]
        self.assertEqual([(r["rarity"], r["pool_version"], r["slot"]) for r in row], [("legendary", "yes", "neck")])
        built = {r["owner"] for r in read_csv(G.MODULE / "data/legendary_powers.csv") if not r["pieces"]}
        self.assertIn("Unique_Amulet_102_x1", built)  # the exclusion is not vacuous: without it the Cube would list the power
        self.assertIn("Unique_Amulet_102_x1", {d3_id for d3_id, _ in G.excluded()})

    def test_the_migration_is_the_render_and_its_mirror(self):
        sql = G.render_excluded()
        self.assertEqual((UPDATES / G.EXCLUDED).read_text(encoding="utf-8"), sql)
        self.assertEqual((G.MODULE / "data/generated" / G.EXCLUDED).read_text(encoding="utf-8"), sql)
        self.assertEqual(re.findall(r"^\('(\w+)'\)", sql, re.M), ["Unique_Amulet_102_x1", "Unique_Sword_2H_104_x1"])
        names = sorted(p.name for p in UPDATES.glob("*.sql"))
        self.assertGreater(names.index(G.EXCLUDED), names.index(G.AUGMENT))

    def test_the_power_query_skips_the_table(self):
        body = CRAFTING[CRAFTING.index("constexpr char const* CubePowerItems ="):CRAFTING.index("// The account and mode the extracted powers")]
        self.assertIn("NOT EXISTS(SELECT 1 FROM dc_cube_excluded x WHERE x.d3_id=b.d3_id)", body)
        # every Cube query that reads powers goes through the one constant: the list, the text, the choice and the Archive's check
        self.assertEqual(len(re.findall(r"\+\s*CubePowerItems\b", CRAFTING)), 4)

    def broken(self, edit):
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(folder.startswith(tempfile.gettempdir()))
            for name in ("cube_excluded.csv", "base_items.csv"):
                shutil.copy(G.DATA / name, folder)
            path = Path(folder) / "cube_excluded.csv"
            rows = read_csv(path)
            edit(rows)
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["d3_id", "reason", "source"])
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(G.CubeError) as caught:
                G.render_excluded(folder)
            return str(caught.exception)

    def test_the_generator_refuses_a_bad_row(self):
        self.assertIn("not a legendary item", self.broken(lambda r: r[0].update(d3_id="Unique_Nothing_999_x1")))
        self.assertIn("not a legendary item", self.broken(lambda r: r[0].update(d3_id=next(
            x["d3_id"] for x in read_csv(G.DATA / "base_items.csv") if x["rarity"] != "legendary"))))
        self.assertIn("listed twice", self.broken(lambda r: r.append(dict(r[0]))))
        self.assertIn("a reason and its source", self.broken(lambda r: r[0].update(reason="")))
        self.assertIn("a reason and its source", self.broken(lambda r: r[0].update(source="")))


if __name__ == "__main__":
    unittest.main()
