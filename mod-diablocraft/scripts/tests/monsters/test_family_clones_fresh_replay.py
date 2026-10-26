"""diablocraft-bilc: a FRESH world database ends with the family clones and every stock clone.

Migrations apply in file-name order. monsters_0004 (family clones, 8950001+ and 9950001+) sorts before the applied, frozen
rifts_0006_elite_clones.sql, whose `DELETE ... >= 8000000` then removes them. rifts_0023_family_clones.sql sorts after it
and inserts them again, rendered by generate_monster_models.py (the one source of monsters_0004's clone rows too).

The replay needs no database: it walks every world migration in file-name order, keeps the set of keys each
creature_template / creature_template_model statement leaves (the parsers of test_generator_delete_ranges: INSERTs with a
column list, DELETEs with an integer key range; a DELETE shape the parser does not know is not seen), and checks the end state.
"""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_monster_models as gen
from test_generator_delete_ranges import UPDATES, parse_delete, parse_insert, statements

KEYS = {"creature_template": "entry", "creature_template_model": "CreatureID"}
CLONES = "rifts_0023_family_clones.sql"
STOCK = ((gen.CHAMPION_BASE, gen.CHAMPION_BASE + gen.FAMILY_ENTRY_BASE - 1),
         (gen.RARE_BASE, gen.RARE_BASE + gen.FAMILY_ENTRY_BASE - 1))


def world_files():
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(UPDATES.glob("*.sql"))}


def replay(files):
    """{table: set of keys} left by running `files` (name -> text) in file-name order."""
    keys = {table: set() for table in KEYS}
    for name in sorted(files):
        text = files[name]
        if "creature_template" not in text:
            continue
        for statement in statements(text):
            if re.match(r"DELETE\b", statement, re.I):
                found = parse_delete(statement)
                if found and found[0] in KEYS and found[1] == KEYS[found[0]]:
                    keys[found[0]] = {k for k in keys[found[0]] if not found[2](k)}
            elif (found := parse_insert(statement)) and found[0] in KEYS:
                keys[found[0]].update(found[1].get(KEYS[found[0]], []))
    return keys


def inserted(text, table):
    return {k for s in statements(text) if (i := parse_insert(s)) and i[0] == table for k in i[1][KEYS[table]]}


def in_stock_band(key):
    return any(low <= key <= high for low, high in STOCK)


class FamilyClonesFreshReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = world_files()
        ids = gen.entries()
        cls.family = {base + ids[row["monster"]] for row in gen.picked_monsters()
                      for base in (gen.CHAMPION_BASE, gen.RARE_BASE)}
        elites = cls.files["rifts_0006_elite_clones.sql"]
        cls.stock = {table: {k for k in inserted(elites, table) if in_stock_band(k)} for table in KEYS}

    def test_a_fresh_replay_ends_with_128_family_clones_and_every_stock_clone(self):
        self.assertEqual(len(self.family), 128)
        self.assertTrue(self.stock["creature_template"], "rifts_0006 inserts no stock clone: the test reads nothing")
        end = replay(self.files)
        for table in KEYS:
            lost = self.family - end[table]
            self.assertEqual(len(lost), 0, f"{table}: {len(lost)} of 128 family clones lost on a fresh database")
            lost = self.stock[table] - end[table]
            self.assertEqual(len(lost), 0, f"{table}: {len(lost)} of {len(self.stock[table])} stock clones lost")

    def test_the_new_migration_sorts_after_the_frozen_one(self):
        self.assertGreater(CLONES, "rifts_0006_elite_clones.sql")
        self.assertTrue(CLONES in self.files, f"{CLONES} is missing")

    def test_a_migration_that_sorted_before_it_would_lose_them(self):
        """The mutant: the same file under a name before rifts_0006 (what monsters_0004 is) leaves no family clone."""
        files = dict(self.files)
        files["monsters_0006_" + CLONES] = files.pop(CLONES)
        end = replay(files)
        self.assertEqual(len(end["creature_template"] & self.family), 0)

    def test_the_clone_rows_are_the_generators_and_the_same_as_monsters_0004s(self):
        self.assertTrue(self.files[CLONES] == gen.render_clones(), f"{CLONES} is not the generator's render: rerun it")
        # one source: the clone rows of monsters_0004 and of this file are the same statements
        def clone_rows(text):
            return {s for s in statements(text) if re.match(r"INSERT\b", s) and re.search(r"VALUES\s*\((?:8|9)950\d\d\d\b", s)}
        before = clone_rows(self.files["monsters_0004_family_data.sql"])
        self.assertEqual(len(before), len(clone_rows(self.files[CLONES])))
        self.assertTrue(before == clone_rows(self.files[CLONES]), "the clone rows differ from monsters_0004's")
        self.assertGreaterEqual(len(before), 128 * 2)       # template + at least one model row per clone

    def test_it_deletes_only_the_family_clone_bands(self):
        """Each DELETE is one family band (champion or rare), and both bands are deleted for each of the four tables."""
        low, high = gen.FAMILY_ENTRY_BASE + 1, gen.FAMILY_ENTRY_BASE + gen.FAMILY_ENTRY_SPAN - 1
        deleted = set()
        for statement in statements(self.files[CLONES]):
            if re.match(r"DELETE\b", statement, re.I):
                table, _, test, _ = parse_delete(statement)
                bases = [b for b in (gen.CHAMPION_BASE, gen.RARE_BASE) if test(b + low) and test(b + high)]
                self.assertEqual(len(bases), 1, statement)
                self.assertFalse(any(test(b + n) for b in (gen.CHAMPION_BASE, gen.RARE_BASE)
                                     for n in (1, 1663, gen.FAMILY_ENTRY_BASE - 1)), "a stock clone is inside the DELETE")
                deleted.add((table, bases[0]))
        self.assertEqual(len(deleted), 8)


if __name__ == "__main__":
    unittest.main()
