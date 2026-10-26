"""diablocraft-placeholder-tunables-apply: the sourced values are in the sheets
and reach the compiled header and the migration (ruling 2026-09-29)."""
import csv
import re
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
RESEARCH = MODULE.parent / "docs/research/placeholder-tunables-values.csv"
UPDATES = MODULE / "data/sql/db-world/updates"
# The designer's ruling over the research value: broad sweep stays 8 (his earlier
# value). The chill rows take the current-D3 60 the research listed.
KEPT = {"broad_sweep_radius_yards": 8}


def sheet(name):
    with (MODULE / "data/tunables" / name).open(encoding="utf-8", newline="") as stream:
        return {row[0]: row for row in csv.reader(stream)}


class SourcedTunables(unittest.TestCase):
    def sourced(self):
        with RESEARCH.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if re.fullmatch(r"[0-9.]+", row["d3_value"]):
                    yield row

    def test_seventeen_sourced_rows(self):
        self.assertEqual(len(list(self.sourced())), 17)

    def test_every_sourced_value_is_in_its_sheet(self):
        for row in self.sourced():
            name, file = row["name"], Path(row["file"]).name
            expected = KEPT.get(name, float(row["d3_value"]))
            cells = sheet(file)[name]
            self.assertEqual(float(cells[1]), expected, name)
            if file == "ability_tunables.csv":
                self.assertEqual(cells[2], "SOURCED", name)
                self.assertNotIn("the designer sets", cells[3], name)

    def test_gathering_reaches_the_compiled_header(self):
        header = (MODULE / "src/classes/barbarian/dc_barbarian_primary_data.h").read_text(encoding="utf-8")
        self.assertIn("gathering_chill_pct = 60;", header)
        self.assertIn("broad_sweep_radius_yards = 8;", header)

    def test_the_migrations_carry_the_sheet(self):
        # combat_0036 is applied and frozen; Part B's combat_0037 is the current carrier.
        text = (UPDATES / "combat_0037_final_tunable_values.sql").read_text(encoding="utf-8")
        for name, cells in sheet("ability_tunables.csv").items():
            if name != "name":
                self.assertIn("('%s',%s,'%s'" % (name, float(cells[1]), cells[2]), text, name)
        shells = (UPDATES / "combat_0035_gathering_chill_sourced.sql").read_text(encoding="utf-8")
        self.assertRegex(shells, r"\(81197,.*?,-61,9,")


if __name__ == "__main__":
    unittest.main()
