"""The spell SQL replaces only the ids generate_spells.py owns: the shared span below the wings and each class block above it.

What this proves, and how:

  * **The shipped render.** Every `DELETE FROM spell_dbc` / `spell_custom_attr` range in data/generated/spell_shells.sql is
    read back and applied to a set of ids: every record the manifest (spell_shells.csv) writes is covered, and no id
    another writer inserts into spell_dbc is (the wings' cosmetic_wings.sql and cosmetics_0001, the retired trade-skill
    pilot world_0013, every other spell_dbc INSERT under data/sql and data/generated that is not this generator's), nor
    any stock Spell.dbc id, nor a reserved block's id. Above the shared span the ranges are exactly the class blocks.
  * **The rule.** owned_spans() with made-up ids: a record in a class block above 84000 adds that block's records and
    helpers whole, never 84000-84006; the shared span ends at the highest id written below 84000; an id written above
    84000 outside every block is refused; a block straddling 83999/84000 is refused. check_blocks() refuses two blocks
    sharing an id or a category, reserved blocks included.
  * **A planted difference is seen.** The checker, fed the one-span DELETE this writer used before (81000 to the highest
    id written) for a render with a block above 84000, reports the wings as deleted.

What it does not prove: that the server loads the rows (the dev deploy), or that no future writer picks ids inside a class
block (check_blocks covers only the blocks named in generate_spells.py).

    python mod-diablocraft/scripts/tests/classes/test_spell_delete_blocks.py
"""

import csv
import re
import struct
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
GENERATED = MODULE / "data" / "generated"
SQL_ROOT = MODULE / "data" / "sql"
sys.path.insert(0, str(MODULE / "scripts"))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as gs  # noqa: E402

DELETE_RANGE = re.compile(r"DELETE FROM `?(spell_dbc|spell_custom_attr)`? WHERE `?(?:ID|spell_id)`? BETWEEN (\d+) AND (\d+);")
INSERT_ROWS = re.compile(r"INSERT INTO `?spell_dbc`?\s*\([^)]*\)\s*VALUES\s*(.*?);", re.S)
ROW_ID = re.compile(r"(?:^|\),\s*)\((\d+),")
OWN_HEADER = "generate_spells.py"


def ranges_of(sql, table="spell_dbc"):
    return [(int(first), int(last)) for name, first, last in DELETE_RANGE.findall(sql) if name == table]


def covered(identifier, ranges):
    return any(first <= identifier <= last for first, last in ranges)


def manifest_ids():
    with (GENERATED / "spell_shells.csv").open(encoding="utf-8", newline="") as stream:
        return [int(row["spell_id"]) for row in csv.DictReader(stream)]


def foreign_spell_ids():
    """{id: file} for every spell_dbc row a file other than this generator's render inserts."""
    out = {}
    for path in sorted(list(SQL_ROOT.rglob("*.sql")) + list(GENERATED.glob("*.sql"))):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if OWN_HEADER in text[:400] and "spell_dbc" in text:
            continue
        for block in INSERT_ROWS.findall(text):
            for identifier in ROW_ID.findall(block):
                out.setdefault(int(identifier), path.name)
    return out


def stock_ids():
    """Every Spell.dbc id below FIRST_SPELL_ID in the server input the generator reads, when it is there."""
    path = gs.DBC / "Spell.dbc"
    if not path.is_file():
        return []
    raw = path.read_bytes()
    count, _fields, size = struct.unpack_from("<III", raw, 4)
    ids = (struct.unpack_from("<I", raw, 20 + index * size)[0] for index in range(count))
    return [identifier for identifier in ids if identifier < gs.FIRST_SPELL_ID]


def problems(ranges, written, foreign, reserved):
    """What a set of DELETE ranges gets wrong: a written id left undeleted, a foreign or reserved id deleted."""
    out = ["written %d not deleted" % i for i in written if not covered(i, ranges)]
    out += ["foreign %d (%s) deleted" % (i, name) for i, name in sorted(foreign.items()) if covered(i, ranges)]
    out += ["reserved %d deleted" % i for i in reserved if covered(i, ranges)]
    return out


def reserved_ids():
    return [i for blocks in gs.RESERVED_BLOCKS.values() for first, last in blocks[:2] for i in range(first, last + 1)]


class ShippedRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        cls.written = manifest_ids()
        cls.foreign = foreign_spell_ids()

    def test_other_writers_exist_to_protect(self):
        # The wings and the trade-skill pilot are the ids above 84000 today; without them the next checks prove nothing.
        for identifier in (84000, 84006, 85000, 85003):
            self.assertIn(identifier, self.foreign)

    def test_spell_dbc_deletes_only_owned(self):
        self.assertEqual(problems(ranges_of(self.sql), self.written, self.foreign, reserved_ids()), [])

    def test_custom_attr_deletes_the_same_ranges(self):
        self.assertEqual(ranges_of(self.sql, "spell_custom_attr"), ranges_of(self.sql))

    def test_no_stock_id_deleted(self):
        ranges = ranges_of(self.sql)
        self.assertEqual([i for i in stock_ids() if covered(i, ranges)], [])

    def test_above_the_shared_span_only_class_blocks(self):
        high = [r for r in ranges_of(self.sql) if r[0] > gs.SHARED_SPAN_LAST]
        blocks = sorted(r for block in gs.CLASS_BLOCKS.values() for r in (block.records, block.helpers)
                        if r[0] > gs.SHARED_SPAN_LAST)
        self.assertEqual(sorted(high), blocks)
        self.assertTrue(blocks, "no class block above the shared span: the rule is untested")

    def test_shared_span_ends_at_highest_low_id(self):
        first = ranges_of(self.sql)[0]
        self.assertEqual(first, (gs.FIRST_SPELL_ID, max(i for i in self.written if i <= gs.SHARED_SPAN_LAST)))


class Rule(unittest.TestCase):
    def test_block_above_adds_whole_block_not_wings(self):
        high = gs.CLASS_BLOCKS["necromancer"]
        spans = gs.owned_spans([81000, 83867, high.records[0] + 3])
        self.assertIn(high.records, spans)
        self.assertIn(high.helpers, spans)
        self.assertEqual(spans[0], (81000, 83867))
        self.assertFalse(any(covered(i, spans) for i in range(84000, 84007)))

    def test_stray_high_id_refused(self):
        with self.assertRaises(SystemExit):
            gs.owned_spans([81000, 84500])

    def test_straddling_block_refused(self):
        saved = gs.CLASS_BLOCKS["necromancer"]
        gs.CLASS_BLOCKS["necromancer"] = gs.ClassBlocks("necromancer", 23, (83950, 84050), saved.helpers, saved.categories)
        try:
            with self.assertRaises(SystemExit):
                gs.owned_spans([81000])
        finally:
            gs.CLASS_BLOCKS["necromancer"] = saved

    def test_blocks_do_not_overlap(self):
        gs.check_blocks()

    def test_overlap_with_reserved_refused(self):
        saved = dict(gs.RESERVED_BLOCKS)
        necro = gs.CLASS_BLOCKS["necromancer"]
        gs.RESERVED_BLOCKS["planted"] = ((necro.helpers[1], necro.helpers[1] + 10), (90000, 90001), (9900, 9901))
        try:
            with self.assertRaises(SystemExit):
                gs.check_blocks()
        finally:
            gs.RESERVED_BLOCKS.clear()
            gs.RESERVED_BLOCKS.update(saved)

    def test_module_spell(self):
        self.assertTrue(gs.module_spell(81000))
        self.assertTrue(gs.module_spell(gs.CLASS_BLOCKS["necromancer"].records[0]))
        self.assertTrue(gs.module_spell(gs.CLASS_BLOCKS["crusader"].helpers[0]))
        self.assertFalse(gs.module_spell(84000))
        self.assertFalse(gs.module_spell(85000))
        self.assertFalse(gs.module_spell(80864))


class Planted(unittest.TestCase):
    def test_one_span_form_deletes_the_wings(self):
        written = manifest_ids()
        one_span = [(gs.FIRST_SPELL_ID, max(written + [gs.CLASS_BLOCKS["necromancer"].records[0]]))]
        found = problems(one_span, written, foreign_spell_ids(), [])
        self.assertTrue(any(line.startswith("foreign 84000") for line in found), found[:3])


if __name__ == "__main__":
    unittest.main()
