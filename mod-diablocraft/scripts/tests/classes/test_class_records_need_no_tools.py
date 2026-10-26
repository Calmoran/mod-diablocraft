"""No Torment class record asks the player for a tool or a totem (diablocraft-u4e8z).

A class record is cloned from a stock donor, and a stock Shaman spell keeps "Tools: Air Totem" in its record: the client then shows the
requirement in red on the tooltip and the spell cannot be cast without the stock totem item. The generator zeroes the donor's fields in
generate_spells.py FORCED_ZERO, but it named the totem category columns "TotemCategory_1" and "TotemCategory_2" when the record's columns are
RequiredTotemCategoryID_1 and RequiredTotemCategoryID_2, and a name that is no column was skipped without a word.

What this proves, and how:

  * **The generator names real columns for the requirement.** FORCED_ZERO holds the four columns that make a tool or a totem category
    requirement (Totem_1, Totem_2, RequiredTotemCategoryID_1, RequiredTotemCategoryID_2), and each is a column of the spell record.
  * **Every record of every class has none.** In the generated server render (spell_shells.sql) no record of the class blocks has a tool or a
    totem category, and the same in the client Spell.dbc inside patch-4.MPQ (read when smpq is on the machine). Planted differences in a copy of
    the render (a tool, a totem category, on one record each) must each be seen.

    python mod-diablocraft/scripts/tests/classes/test_class_records_need_no_tools.py
"""

import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as spells  # noqa: E402
from test_control_immunity_gap import insert_rows, number  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
SHELLS_SQL = MODULE / "data/generated/spell_shells.sql"
MPQ = REPO / "client-patch/patch-4.MPQ"
REQUIREMENT = ("Totem_1", "Totem_2", "RequiredTotemCategoryID_1", "RequiredTotemCategoryID_2")
# The ids the generator owns (the class blocks and the helper blocks): the module's records, not the stock ones.
FIRST, LAST = 81000, 86599


def requirements(rows):
    """{id: {column: value}} of the records in the class blocks that carry a tool or a totem category."""
    found = {}
    for row in rows:
        spell = int(row["ID"])
        if FIRST <= spell <= LAST:
            held = {column: number(row[column]) for column in REQUIREMENT if number(row[column])}
            if held:
                found[spell] = held
    return found


class Generator(unittest.TestCase):
    def test_the_requirement_columns_are_cleared_by_name_and_are_columns(self):
        rows = list(insert_rows(SHELLS_SQL.read_text(encoding="utf-8"), "spell_dbc"))
        for column in REQUIREMENT:
            self.assertIn(column, spells.FORCED_ZERO, column)
            self.assertIn(column, rows[0], column + " is no column of the record: the clear would be skipped without a word")


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = list(insert_rows(SHELLS_SQL.read_text(encoding="utf-8"), "spell_dbc"))

    def test_no_class_record_has_a_tool_or_a_totem_category(self):
        self.assertGreater(sum(FIRST <= int(r["ID"]) <= LAST for r in self.rows), 900)
        self.assertEqual({}, requirements(self.rows))

    def test_a_planted_tool_or_totem_category_is_seen(self):
        for column, value in (("Totem_1", "5175"), ("Totem_2", "5176"), ("RequiredTotemCategoryID_1", "4"), ("RequiredTotemCategoryID_2", "2")):
            with self.subTest(column=column):
                planted = [dict(r) for r in self.rows]
                target = next(r for r in planted if int(r["ID"]) == 86315)   # the Tempest Totem, the air totem of the screenshot
                target[column] = value
                self.assertEqual({86315: {column: float(value)}}, {k: {c: float(v) for c, v in held.items()} for k, held in requirements(planted).items()})

    def test_the_client_records_have_none_either(self):
        smpq = shutil.which("smpq")
        if not smpq or not MPQ.is_file():
            self.skipTest("smpq or the archive is not on this machine")
        with tempfile.TemporaryDirectory() as folder:
            done = subprocess.run([smpq, "-x", "-f", str(MPQ)], cwd=folder, capture_output=True, text=True)
            if done.returncode:
                self.skipTest("the archive cannot be read here: " + done.stderr[-200:])
            raw = (Path(folder) / "DBFilesClient/Spell.dbc").read_bytes()
        _, count, fields, size, _ = struct.unpack("<4sIIII", raw[:20])
        columns = list(self.rows[0])
        position = {column: columns.index(column) for column in REQUIREMENT}
        seen = 0
        for index in range(count):
            values = struct.unpack("<%dI" % fields, raw[20 + index * size:20 + (index + 1) * size])
            if FIRST <= values[0] <= LAST:
                seen += 1
                self.assertEqual({}, {c: values[i] for c, i in position.items() if values[i]}, "record %d" % values[0])
        self.assertGreater(seen, 900)


if __name__ == "__main__":
    unittest.main()
