"""Cosmic Strand (diablocraft-vm1q1, legendary rest bead 022): Teleport gains the effect of the Wormhole rune.

  * data/legendary_powers.csv gains its one row: `rune` Teleport / Wormhole (given without choosing it, as Fury of the Ancients and Mortick's
    Brace); the words come from d3planner's item file and are set against the tooltip, and the rune and its two numbers exist in the sheets;
  * the production rule (dc_item_power_math.h GrantsRune) is driven with the generated rows through the k4 harness, and its mutants fail the
    same driver;
  * source-text guards that Wizard::Cast opens Wormhole's grace window for a Teleport of any rune when the rune is given, reads the Wormhole
    row's own numbers, and counts a chosen-and-given Wormhole once (they prove the calls are there, not that they run; the C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-vm1q1.md).
"""
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env  # noqa: E402
import test_item_power_k4 as k4  # noqa: E402  (a module, so its test classes are not run twice)
from test_item_power_math import GENERATED, planner, read_csv  # noqa: E402
from test_item_power_fury import all_rows, tooltip  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
COSMIC = "Unique_Orb_004_x1"
TELEPORT, RUNE = "Teleport", "Wormhole"
RUNES = ("Calamity", "Fracture", "Safe Passage", "Reversal", "Wormhole")


def source():
    text = planner("item_offhand.js", COSMIC)
    found = re.search(r"format: \"Teleport gains the effect of the Wormhole rune\.\", args: 0\}", text)
    assert found, text
    return "Teleport gains the effect of the Wormhole rune."


class Table(unittest.TestCase):
    def test_the_row_is_the_source(self):
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(COSMIC, 0, "rune", TELEPORT, RUNE, 1.0, 1.0, *blank)}, {r for r in all_rows() if r[0] == COSMIC})
        self.assertEqual(source(), tooltip(COSMIC))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == COSMIC)
        self.assertEqual(("Cosmic Strand", "yes", "wizard"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))
        # the rune and the two numbers its window reads exist
        self.assertEqual(set(RUNES), {r["rune_name"] for r in read_csv("data/d3/wizard_runes.csv") if r["skill_name"] == TELEPORT})
        values = {r["token"]: float(r["value"]) for r in read_csv("data/d3/wizard_skill_values.csv") if (r["skill"], r["rune"]) == (TELEPORT, RUNE)}
        self.assertGreater(values["duration_seconds"], 0)
        self.assertGreater(values["cast_count"], 0)


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        # not worn: no rune given
        out += clear + [(T("rune", TELEPORT, rune, 0), "0") for rune in RUNES]
        # worn: Wormhole given and no other rune of Teleport, no rune of another skill
        out += clear + [(T("wears", COSMIC, 0), None)]
        out += [(T("rune", TELEPORT, rune, 0), "1" if rune == RUNE else "0") for rune in RUNES]
        out += [(T("rune", "Slow Time", RUNE, 0), "0"), (T("rune", "Mirror Image", "Wormhole", 0), "0")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = k4.Rules.build(header_text, "cosmic-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 6)
        self.assertEqual(GENERATED.read_text(encoding="utf-8").count("\n("), len(all_rows()))     # every generated row parsed
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "every_rune_is_given": real.replace('!ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||',
                                                '!ActiveValues(rows, counts, "rune", skill, "Wormhole", situation).empty() ||'),
            "the_skill_is_ignored": real.replace('!ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||',
                                                 '!ActiveValues(rows, counts, "rune", "Teleport", rune, situation).empty() ||'),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
