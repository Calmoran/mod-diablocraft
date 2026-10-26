"""Mempo of Twilight (diablocraft-b5p5y, legendary rest bead 025): "Meteor Shower rune is now applied to all cast Meteors and deals [300 - 400]% increased damage."

  * data/legendary_powers.csv gains two rows for the pool helm P74_Unique_Helm_006: `rune` Meteor / Meteor Shower (given without choosing it, as Cosmic Strand's
    Wormhole) and `skill` Meteor `damage_increase_pct` 300-400 (rolled once per item); the words and the range come from d3planner (data.json) and are set against
    the tooltip, and the rune and its numbers exist in the sheets;
  * the production rules (dc_item_power_math.h GrantsRune and SkillFactor) are driven with the generated rows through the k4 harness, and their mutants fail the
    same driver;
  * source-text guards that Wizard::Delayed takes the Shower branch for a Meteor of any rune when the rune is given (the Shower row's own numbers, the Shower's id
    to every impact), and for a chosen Shower once (they prove the calls are there, not that they run; the C++ is compile-checked by syntax_check.sh and the
    in-game steps are in docs/test-diablocraft-b5p5y.md).
"""
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env  # noqa: E402
import test_item_power_k4 as k4  # noqa: E402  (a module, so its test classes are not run twice)
from test_item_power_math import GENERATED, planner_json, read_csv  # noqa: E402
from test_item_power_fury import all_rows, tooltip  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
MEMPO = "P74_Unique_Helm_006"
METEOR, RUNE, STAT = "Meteor", "Meteor Shower", "damage_increase_pct"
RUNES = ("Molten Impact", "Meteor Shower", "Comet", "Star Pact", "Thunder Crash")


def source():
    """(text, low, high) as d3planner's data.json words the power."""
    node = planner_json(MEMPO)
    custom = node["required"]["custom"]
    assert custom["format"] == "Meteor Shower rune is now applied to all cast Meteors and deals %d%% increased damage.", custom
    return custom["format"] % custom["min"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_rows_are_the_source(self):
        text, low, high = source()
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(MEMPO, 0, "rune", METEOR, RUNE, 1.0, 1.0, *blank), (MEMPO, 0, "skill", METEOR, STAT, low, high, *blank)},
                         {r for r in all_rows() if r[0] == MEMPO})
        self.assertEqual((300.0, 400.0), (low, high))
        self.assertEqual(text.replace("300%", "300–400%"), tooltip(MEMPO))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == MEMPO)
        self.assertEqual(("Mempo of Twilight", "yes", "wizard"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))
        # the rune and the numbers its impacts read exist
        self.assertEqual(set(RUNES), {r["rune_name"] for r in read_csv("data/d3/wizard_runes.csv") if r["skill_name"] == METEOR})
        values = {r["token"]: float(r["value"]) for r in read_csv("data/d3/wizard_skill_values.csv") if (r["skill"], r["rune"]) == (METEOR, RUNE)}
        self.assertEqual(7.0, values["spawn_count"])


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        _, low, high = source()
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        # not worn: no rune given, no damage
        out += clear + [(T("rune", METEOR, rune, 0), "0") for rune in RUNES] + [(T("factor", METEOR, STAT, 0), "1")]
        # worn: only the Shower given, for Meteor only; no rune of another skill
        out += clear + [(T("wears", MEMPO, 0), None)]
        out += [(T("rune", METEOR, rune, 0), "1" if rune == RUNE else "0") for rune in RUNES]
        out += [(T("rune", "Hydra", RUNE, 0), "0"), (T("rune", "Blizzard", "Meteor Shower", 0), "0")]
        # worn and rolled: 1 + N/100, only Meteor's
        for roll in (low, 350, high):
            out += clear + [(T("wears", MEMPO, 0), None), (T("value", MEMPO, METEOR, STAT, roll), None), (T("factor", METEOR, STAT, 0), "%.10g" % (1 + roll / 100)),
                            (T("factor", "Blizzard", STAT, 0), "1"), (T("factor", "Hydra", STAT, 0), "1")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = k4.Rules.build(header_text, "mempo-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 15)
        self.assertEqual(GENERATED.read_text(encoding="utf-8").count("\n("), len(all_rows()))     # every generated row parsed
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "every_rune_is_given": real.replace('!ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||',
                                                '!ActiveValues(rows, counts, "rune", skill, "Meteor Shower", situation).empty() ||'),
            "the_skill_is_ignored": real.replace('!ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||',
                                                 '!ActiveValues(rows, counts, "rune", "Meteor", rune, situation).empty() ||'),
            "the_percent_is_read_as_tenths": real.replace("factor *= 1.0 + pct / 100.0;\n        return factor;\n    }\n\n    // The multiplier of the `damage_by_missing_re",
                                                          "factor *= 1.0 + pct / 10.0;\n        return factor;\n    }\n\n    // The multiplier of the `damage_by_missing_re"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
