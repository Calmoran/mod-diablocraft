"""diablocraft-t9fl: the Mystic rebuild (xw2m) stopped reading mystic_cost_multiplier and enchant_material_count.

Both left the sheets; the migrations that already shipped keep their text (they are frozen). This holds that
nothing live reads either name again, and that the generators' own output removes them from the live tables.
"""
import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_sql
import generate_tunables

MODULE = Path(__file__).resolve().parents[3]
UPDATES = MODULE / "data/sql/db-world/updates"
COLUMN, TUNABLE = "mystic_cost_multiplier", "enchant_material_count"

# The only live files allowed to say a retired name, each for a stated reason.
ALLOWED = {
    "scripts/generate/crafting/generate_crafting.py": "re-renders frozen crafting_0001, which added the column",
    "scripts/generate/tunables/generate_tunables.py": "RETIRED, the list the migration deletes from",
}
READERS = [("src", "*.cpp"), ("src", "*.h"), ("lua", "*.lua"), ("../client-patch/addons", "*.lua"),
           ("scripts", "*.py"), ("scripts", "*.lua"), ("data/d3", "*.csv"), ("data/tunables", "*.csv")]


def newest_loot_tuning_migration():
    return sorted(UPDATES.glob("loot_tuning_*_csv.sql"))[-1]


class RetiredMysticNamesTests(unittest.TestCase):
    def test_nothing_live_reads_either_name(self):
        hits = []
        for folder, pattern in READERS:
            for path in sorted((MODULE / folder).rglob(pattern)):
                relative = path.resolve().relative_to(MODULE.parent).as_posix().removeprefix("mod-diablocraft/")
                if path.name.startswith("test_") or relative in ALLOWED:
                    continue
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                hits += [f"{relative}: {name}" for name in (COLUMN, TUNABLE) if name in text]
        self.assertEqual(hits, [])

    def test_the_allowed_files_are_still_needed(self):
        for relative in ALLOWED:
            text = (MODULE / relative).read_text(encoding="utf-8")
            self.assertTrue(COLUMN in text or TUNABLE in text, f"{relative} no longer names a retired name: drop it from ALLOWED")

    def test_the_loot_tuning_render_has_no_such_column(self):
        spec = generate_sql.TABLES["loot_tuning"]
        sql, _count = generate_sql.render_table(generate_sql.source_csv(MODULE, "loot_tuning"), spec)
        self.assertNotIn(COLUMN, sql)
        self.assertIn("mystic_base_gold", sql)                      # its neighbour stays
        self.assertEqual(newest_loot_tuning_migration().read_text(encoding="utf-8"), sql)
        self.assertEqual((MODULE / "data/generated/loot_tuning.sql").read_text(encoding="utf-8"), sql)

    def test_the_table_is_rebuilt_after_every_migration_that_adds_the_column(self):
        """The updater applies in filename order; the rebuild without the column must come last of them."""
        rebuild = newest_loot_tuning_migration().name
        adders = [p.name for p in UPDATES.glob("*.sql") if re.search(rf"ADD COLUMN {COLUMN}\b", p.read_text(encoding="utf-8"))]
        self.assertTrue(adders, "no migration adds the column: the fixture changed, review this test")
        for name in adders:
            self.assertLess(name, rebuild, f"{name} would add the column back after {rebuild} dropped it")

    def test_the_tunables_migration_deletes_the_row_the_sheet_no_longer_has(self):
        with open(MODULE / "data/tunables/crafting.csv", newline="") as handle:
            sheet = {row["name"] for row in csv.DictReader(handle)}
        self.assertNotIn(TUNABLE, sheet)
        text = generate_tunables.sql(generate_tunables.read_all(MODULE), generate_tunables.RETIRED)
        insert = text.split("INSERT INTO", 1)[1].split("ON DUPLICATE KEY UPDATE", 1)[0]
        self.assertNotIn(TUNABLE, insert)
        self.assertIn(f"DELETE FROM `dc_tunables` WHERE `category` = 'crafting' AND `name` = '{TUNABLE}';", text)
        self.assertEqual((UPDATES / generate_tunables.CURRENT_MIGRATION).read_text(encoding="utf-8"), text)

    def test_nothing_retired_is_still_in_a_sheet(self):
        names = {(category, name) for category, name, *_ in generate_tunables.read_all(MODULE)}
        self.assertFalse(names & set(generate_tunables.RETIRED))

    def test_class_starts_render_still_matches_its_committed_migration(self):
        """generate_sql --class-starts shares tunables sql(); a DELETE leaking in made it differ from applied world_0021."""
        text, _count = generate_sql.render_class_starts(MODULE)
        self.assertNotIn("DELETE FROM `dc_tunables`", text)
        self.assertEqual((UPDATES / generate_sql.CLASS_START_MIGRATION).read_text(encoding="utf-8"), text)
        self.assertEqual((MODULE / "data/generated/class_starts.sql").read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()
