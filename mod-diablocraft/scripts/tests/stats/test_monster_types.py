#!/usr/bin/env python3
"""diablocraft-1n2g9: the D3 type of each roster monster, which Damage to Humans reads (the designer, q-1016-16: "our D3 type column").

Checked here:
  * the committed migration is exactly what generate_monster_types.py renders from the sheets;
  * the Human rows are the roster monsters whose warpath row says Human, worked out here from the two CSVs by name and not
    through the generator, and a monster with no warpath row (`none`) has no row, so it takes no bonus;
  * the generator refuses a roster monster whose warpath name is missing from the sheet and a row with no type;
  * the C++ lookup selects the columns the migration creates, and a champion or rare clone reads its base monster's row.
It does not run the server: whether a given item rolls damage_humans is the items mapping's.
"""
import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_monster_types as gen  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
MIGRATION = MODULE / "data/sql/db-world/updates/monster_types_0001_d3_types.sql"
MIRROR = MODULE / "data/generated/monster_types_0001_d3_types.sql"
LOOKUP = MODULE / "src/combat/dc_monster_d3_type.cpp"


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def rows_of(sql):
    return re.findall(r"^\('((?:[^']|'')*)', (\d+), '([^']*)'\)", sql, re.M)


class Migration(unittest.TestCase):
    def test_the_committed_migration_is_the_render(self):
        sql = gen.render(gen.load())
        self.assertEqual(MIGRATION.read_text(encoding="utf-8"), sql)
        self.assertEqual(MIRROR.read_text(encoding="utf-8"), sql)

    def test_the_human_rows_are_the_roster_monsters_the_sheet_types_human(self):
        types = {r["name"]: r["monster_type"] for r in read_csv(gen.sheets.PROGRESS)}
        roster = read_csv(gen.sheets.ROSTER)
        expected = {r["name"] for r in roster if r["warpath_name"] != "none" and types.get(r["warpath_name"]) == "Human"}
        written = {name.replace("''", "'") for name, _entry, kind in rows_of(MIGRATION.read_text(encoding="utf-8")) if kind == "Human"}
        self.assertTrue(expected, "the roster has no Human at all, so the reader would never fire")
        self.assertEqual(written, expected)

    def test_a_monster_with_no_warpath_name_has_no_row(self):
        none_named = {r["name"] for r in read_csv(gen.sheets.ROSTER) if r["warpath_name"] == "none"}
        self.assertTrue(none_named)
        written = {name for name, _entry, _kind in rows_of(MIGRATION.read_text(encoding="utf-8"))}
        self.assertFalse(none_named & written)

    def test_every_row_is_a_creature_entry_once(self):
        entries = [int(entry) for _name, entry, _kind in rows_of(MIGRATION.read_text(encoding="utf-8"))]
        self.assertEqual(len(entries), len(set(entries)))
        self.assertTrue(all(950000 < entry < 951000 for entry in entries))


class Refusals(unittest.TestCase):
    roster = [dict(monster="Dark Cultist", family="Cultists", role="melee", warpath_name="Dark Cultist", entry=950025)]
    sheet = [dict(name="Dark Cultist", monster_type="Human")]

    def test_the_type_is_read_through_the_warpath_name(self):
        self.assertEqual(gen.check_types(self.roster, self.sheet),
                         [dict(monster="Dark Cultist", entry=950025, d3_type="Human")])

    def test_a_warpath_name_missing_from_the_sheet_is_refused(self):
        with self.assertRaises(gen.sheets.DataError):
            gen.check_types([dict(self.roster[0], warpath_name="Nobody")], self.sheet)

    def test_a_row_with_no_type_is_refused(self):
        with self.assertRaises(gen.sheets.DataError):
            gen.check_types(self.roster, [dict(name="Dark Cultist", monster_type=" ")])

    def test_none_and_held_back_monsters_have_no_row(self):
        held = [dict(self.roster[0], warpath_name="none"), dict(self.roster[0], entry=None)]
        self.assertEqual(gen.check_types(held, self.sheet), [])


class Lookup(unittest.TestCase):
    def test_the_lookup_selects_the_migrations_columns(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        table = re.search(r"CREATE TABLE IF NOT EXISTS `(\w+)` \((.*?), PRIMARY KEY", sql).groups()
        columns = re.findall(r"`(\w+)` ", table[1])
        cpp = LOOKUP.read_text(encoding="utf-8")
        select = re.search(r'Query\("SELECT (\w+), (\w+) FROM (\w+)"\)', cpp).groups()
        self.assertEqual(select[2], table[0])
        self.assertIn(select[0], columns)
        self.assertIn(select[1], columns)

    def test_a_clone_reads_its_base_monsters_row(self):
        cpp = LOOKUP.read_text(encoding="utf-8")
        self.assertIn("types.find(Rifts::Family::BaseEntry(creature->GetEntry()))", cpp)
        self.assertNotIn("types.find(creature->GetEntry())", cpp)


if __name__ == "__main__":
    unittest.main()
