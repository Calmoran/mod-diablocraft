"""Tasker and Theo (diablocraft-1cv9k, legendary-rest): "Increase attack speed of your pets by [40-50]%."

  * data/legendary_powers.csv gains its one row: `player` `pet_attack_speed_pct` [40-50], a player number so the range rolls ONCE per item (two
    skill rows, one per pet, would roll twice); the words and the range are read from d3planner's item file and set against the tooltip; the
    generator takes the stat only as a positive player number;
  * the production rule (dc_item_power_math.h PlayerFactor) is driven with the generated rows through its own harness, and its mutants fail
    the same driver;
  * source-text guards that the pets D3 speeds up (the Ancients and the Hydra: docs/research/enforcer-pets-web-sources.md, Tasker and Theo
    "actually affect all pets, even summons and devices like Hydra, Call of the Ancients") read it on the owner's attacks per second, and the
    two that do not (the Familiar: "does not benefit of Tasker and Theos attack speed increase"; Mirror Image: it never attacks) do not
    (they prove the calls are there, not that they run; the C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-1cv9k.md).
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import harness_env  # noqa: E402
import test_item_power_fury as fury  # noqa: E402  (modules, so their test classes are not run twice)
import test_item_power_math as power_math  # noqa: E402
from test_item_power_math import GENERATED, MIGRATION, generator, planner, read_csv  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/pet_attack_speed/harness.cpp"
TASKER, STAT = "Unique_Gloves_003_x1", "pet_attack_speed_pct"


def source():
    text = planner("item_hands.js", TASKER)
    found = re.search(r'format: "Increase attack speed of your pets by %d%%\.", min: (\d+), max: (\d+)\}', text)
    assert found, text
    return float(found[1]), float(found[2])


class Table(unittest.TestCase):
    def test_the_row_is_the_source(self):
        low, high = source()
        self.assertEqual((40, 50), (low, high))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(TASKER, 0, "player", "", STAT, low, high, *blank)}, {r for r in fury.all_rows() if r[0] == TASKER})
        self.assertIn("attack speed of your pets by %g–%g%%." % (low, high), fury.tooltip(TASKER))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == TASKER)
        self.assertEqual(("Tasker and Theo", "hands", "yes"), (pool["d3_name"], pool["slot"], pool["pool_version"]))

    def test_the_generator_takes_the_stat_only_as_a_positive_player_number(self):
        base = {"owner": TASKER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "40", "value_max": "50",
                "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                "icd_seconds": "", "source": "x", "note": ""}
        for name, row in {"on a skill": dict(base, kind="skill", skill="Hydra"), "slower": dict(base, value_min="-50", value_max="-40"),
                          "zero": dict(base, value_min="0")}.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([row])
        self.assertEqual(1, len(power_math.Table.rows_of([base])))


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        low, high = source()
        out = [(T("row", *r), None) for r in fury.all_rows()]
        clear = [(T("clear"), None)]
        # not worn, worn with no stored roll (a ranged row gives nothing without one), the roll stored but the item in the bag: pets at the owner's speed
        out += clear + [(T("pfactor", STAT), "1"), (T("wears", TASKER), None), (T("pfactor", STAT), "1")]
        out += clear + [(T("value", TASKER, "", STAT, 45), None), (T("pfactor", STAT), "1")]
        # worn with its roll: x(1 + roll/100), at either end and between; no other player stat moves
        for roll in (low, 45, high):
            out += clear + [(T("wears", TASKER), None), (T("value", TASKER, "", STAT, roll), None),
                            (T("pfactor", STAT), "%g" % (1 + roll / 100)), (T("pfactor", "damage_dealt_pct"), "1"), (T("pfactor", "damage_taken_pct"), "1")]
        # two worn sources (a second owner of the same stat, as a row of its own) each multiply: (1 + .40) x (1 + .50), never 1 + .40 + .50
        other = ("Other_Gloves", 0, "player", "", STAT, 40.0, 50.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        out += clear + [(T("row", *other), None), (T("wears", TASKER), None), (T("wears", "Other_Gloves"), None),
                        (T("value", TASKER, "", STAT, 40), None), (T("value", "Other_Gloves", "", STAT, 50), None), (T("pfactor", STAT), "%g" % (1.4 * 1.5))]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @staticmethod
    def build(header_text, name):
        power_math.SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="tasker-%s-" % name, dir=str(power_math.SCRATCH)))
        return work, binary

    def test_the_rule_agrees_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 8)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        factor = 'for (double pct : ActiveValues(rows, counts, "player", "", stat, situation))'
        mutants = {
            "the_stat_is_ignored": real.replace(factor, factor.replace("stat, situation", '"damage_dealt_pct", situation')),
            "the_kind_is_ignored": real.replace(factor, factor.replace('"player", "", stat', '"skill", "", stat')),
            "the_roll_is_not_a_multiplier": real.replace("factor *= 1.0 + pct / 100.0;\n        return factor;\n    }\n\n    // A `set to` stat: the skill's own",
                                                         "factor += pct / 100.0;\n        return factor;\n    }\n\n    // A `set to` stat: the skill's own"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
