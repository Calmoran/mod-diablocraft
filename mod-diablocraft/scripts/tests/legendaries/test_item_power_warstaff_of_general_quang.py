"""Warstaff of General Quang (diablocraft-bxfkr, Monk legendary list row 216): Tempest Rush gains the effect of the Tailwind rune.

  * data/legendary_powers.csv gains its one row: `rune` Tempest Rush / Tailwind (given without choosing it, as Cosmic Strand's Wormhole); the
    words come from d3planner's item file and are set against the tooltip, and the rune and its one number exist in the sheets;
  * the production rule (dc_item_power_math.h GrantsRune) is driven with the generated rows through the k4 harness, and its mutants fail the
    same driver;
  * source-text guards that a Tempest Rush press of any rune puts Tailwind's movement speed on the Monk when the rune is given, reads the
    Tailwind row's own number, counts a chosen-and-given Tailwind once, and takes off at the end what the press put on (they prove the calls
    are there, not that they run; the C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-bxfkr.md).
"""
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import test_item_power_k4 as k4  # noqa: E402  (a module, so its test classes are not run twice)
from test_item_power_math import GENERATED, planner, read_csv  # noqa: E402
from test_item_power_fury import all_rows, tooltip  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
QUANG = "Unique_CombatStaff_2H_102_x1"
TEMPEST, RUNE = "Tempest Rush", "Tailwind"
RUNES = ("Bluster", "Tailwind", "Electric Field", "Northern Breeze", "Flurry")


def source():
    text = planner("item_twohand.js", QUANG)
    found = re.search(r"format: \"Tempest Rush gains the effect of the Tailwind rune\.\", args: 0\}", text)
    assert found, text
    return "Tempest Rush gains the effect of the Tailwind rune."


class Table(unittest.TestCase):
    def test_the_row_is_the_source(self):
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(QUANG, 0, "rune", TEMPEST, RUNE, 1.0, 1.0, *blank)}, {r for r in all_rows() if r[0] == QUANG})
        self.assertEqual(source(), tooltip(QUANG))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == QUANG)
        self.assertEqual(("Warstaff of General Quang", "yes", "monk"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))
        # the rune and the number its speed reads exist
        self.assertEqual(set(RUNES), {r["rune_name"] for r in read_csv("data/d3/monk_runes.csv") if r["skill_name"] == TEMPEST})
        values = {r["token"]: float(r["value"]) for r in read_csv("data/d3/monk_skill_values.csv") if (r["skill"], r["rune"]) == (TEMPEST, RUNE)}
        self.assertEqual(25.0, values["movement_speed_pct"])


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        # not worn: no rune given
        out += clear + [(T("rune", TEMPEST, rune, 0), "0") for rune in RUNES]
        # worn: Tailwind given and no other rune of Tempest Rush, no rune of another skill
        out += clear + [(T("wears", QUANG, 0), None)]
        out += [(T("rune", TEMPEST, rune, 0), "1" if rune == RUNE else "0") for rune in RUNES]
        out += [(T("rune", "Sweeping Wind", RUNE, 0), "0"), (T("rune", "Teleport", "Wormhole", 0), "0")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = k4.Rules.build(header_text, "quang-" + name)
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
                                                '!ActiveValues(rows, counts, "rune", skill, "Tailwind", situation).empty() ||'),
            "the_skill_is_ignored": real.replace('!ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||',
                                                 '!ActiveValues(rows, counts, "rune", "Tempest Rush", rune, situation).empty() ||'),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
