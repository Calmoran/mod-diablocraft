"""D3's Healing table of the power formulas (data/d3/healing_table.csv, scripts/generate/classes/generate_healing_table.py,
src/combat/dc_healing_table.h), diablocraft-im7mr.24.

  * The header is the sheet's render: a changed sheet is a changed header.
  * The sheet is the table the decoder reads out of the game files (decode_pow.py table Healing), level 0 to 70; the check is skipped on a
    machine without the reference archives.
  * The generator refuses a sheet with a gap in the levels, a value that falls, or no value for level 0.
  * The values that matter: level 70 is 536421, and 0.0014 of it is the 751 of Leech's Osmosis tooltip.

    python mod-diablocraft/scripts/tests/classes/test_healing_table.py
"""

import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import decode_pow
import generate_healing_table as gen

MODULE = Path(__file__).resolve().parents[3]
SCRATCH = MODULE.parent / "azerothcore-wotlk/build/_agent-scratch/healing_table_test"


class Table(unittest.TestCase):
    def test_the_header_is_the_sheets_render(self):
        self.assertEqual((MODULE / "src/combat/dc_healing_table.h").read_text(encoding="utf-8"), gen.render())

    def test_the_sheet_runs_from_level_0_to_70(self):
        values = gen.read()
        self.assertEqual(len(values), 71)
        self.assertEqual((values[1], values[10], values[35], values[70]), (390, 1133, 12201, 536421))

    def test_osmosis_at_70_is_the_tooltips_751(self):
        self.assertEqual(round(0.0014 * gen.read()[70]), 751)

    @unittest.skipUnless(decode_pow.available(), "needs reference/blizzless-diiis and smpq")
    def test_the_sheet_is_the_decoders_table(self):
        decoded = decode_pow.power_table("Healing")
        self.assertEqual(gen.read(), [float(f"{v:g}") for v in decoded[:71]])
        self.assertTrue(all(v == 0 for v in decoded[71:]))


class Refusals(unittest.TestCase):
    def sheet(self, text):
        shutil.rmtree(SCRATCH, ignore_errors=True)
        (SCRATCH / "data/d3").mkdir(parents=True)
        (SCRATCH / "data/d3/healing_table.csv").write_text(text, encoding="utf-8")
        return SCRATCH

    def tearDown(self):
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def test_a_gap_in_the_levels_is_refused(self):
        with self.assertRaises(ValueError):
            gen.read(self.sheet("level,value,source\n0,1,x\n1,390,x\n3,514,x\n"))

    def test_a_value_that_falls_is_refused(self):
        with self.assertRaises(ValueError):
            gen.read(self.sheet("level,value,source\n0,1,x\n1,390,x\n2,452,x\n3,400,x\n"))

    def test_no_value_for_level_0_is_refused(self):
        with self.assertRaises(ValueError):
            gen.read(self.sheet("level,value,source\n0,0,x\n1,390,x\n2,452,x\n"))

    def test_a_good_sheet_is_taken(self):
        self.assertEqual(gen.read(self.sheet("level,value,source\n0,1,x\n1,390,x\n2,452,x\n")), [1.0, 390.0, 452.0])


if __name__ == "__main__":
    unittest.main()
