"""diablocraft-smzk: the Rift Keeper (910003) has no subname and is level 70, from the data cell to the migration.

    python3 mod-diablocraft/scripts/tests/world/test_hub_keeper_tooltip.py        # no database

Pinned: the migration and its data/generated mirror are what the generator renders from world_hub_services.csv; the
render empties the subname and sets minlevel = maxlevel = the cell's level (70); a blank or non-numeric level refuses;
the relocation generator reads the same two cells, so a regeneration cannot bring the donor's 'Macecrafter' / 42 back.
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_hub_keeper_tooltip as keeper  # noqa: E402

MODULE = HERE.parent


class KeeperTooltip(unittest.TestCase):
    def test_migration_and_mirror_are_the_render(self):
        sql = keeper.render()
        for path in (MODULE / "data/sql/db-world/updates" / keeper.NAME, MODULE / "data/generated" / keeper.NAME):
            self.assertEqual(path.read_text(encoding="utf-8"), sql, path)

    def test_no_subname_level_70(self):
        sql = keeper.render()
        self.assertIn("SET `subname` = '', `minlevel` = 70, `maxlevel` = 70 WHERE `entry` = 910003;", sql)
        self.assertNotIn("Macecrafter", sql)

    def test_bad_level_refuses(self):
        with open(keeper.CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        for bad in ("", "seventy"):
            rows[0]["level"] = bad
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "s.csv"
                with p.open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
                with self.assertRaises(ValueError):
                    keeper.render(p)

    def test_regeneration_keeps_it(self):
        src = (HERE / "generate/world/generate_hub_relocation.py").read_text(encoding="utf-8")
        self.assertIn("subname=service['subname']", src)
        self.assertIn("minlevel=int(service['level']), maxlevel=int(service['level'])", src)


if __name__ == "__main__":
    unittest.main()
