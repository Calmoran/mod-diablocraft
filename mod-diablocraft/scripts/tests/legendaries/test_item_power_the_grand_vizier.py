"""The Grand Vizier (diablocraft-muzdx, Wizard legendary list row 86; N-COST, built by Fury of the Vanished Peak): "Reduces the Arcane Power cost of Meteor by 50%
and increases its damage by [300-400]%."

  * data/legendary_powers.csv gains two `skill` rows for the pool staff P61_Unique_Staff_009: Meteor `cost_reduction_pct` 50 (fixed: the text's number, the power
    file's SF_0 0.5) and `damage_increase_pct` 300-400 (rolled once per item); the words and the range come from d3planner (item_twohand.js) and are set
    against the tooltip;
  * the spell record (Meteor's hidden cost aura in the Wizard family, reaching exactly Meteor and its runes) is proved by
    test_item_power_fury_of_the_vanished_peak.py, whose OWNERS names this item;
  * the production rules (dc_item_power_math.h SkillSum and SkillFactor) are driven with the generated rows through the k0k2 harness, and their mutants fail
    the same driver. The in-game steps are in docs/test-diablocraft-muzdx.md.
"""
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import test_item_power_math as k0k2  # noqa: E402  (a module, so its test classes are not run twice)
from test_item_power_fury_of_the_vanished_peak import OWNERS  # noqa: E402
from test_item_power_math import all_rows, planner, read_csv, tooltip  # noqa: E402

MATH = Path(__file__).resolve().parents[3] / "src/combat/dc_item_power_math.h"
VIZIER = "P61_Unique_Staff_009"
METEOR = "Meteor"


def source():
    """(low, high) as d3planner's item file words the power."""
    text = planner("item_twohand.js", VIZIER)
    m = re.search(r'format: "Reduces the Arcane Power cost of Meteor by 50%% and increases its damage by %d%%\.", min: (\d+), max: (\d+)', text)
    assert m, text
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_rows_are_the_source(self):
        low, high = source()
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual((300.0, 400.0), (low, high))
        self.assertEqual({(VIZIER, 0, "skill", METEOR, "cost_reduction_pct", 50.0, 50.0, *blank), (VIZIER, 0, "skill", METEOR, "damage_increase_pct", low, high, *blank)},
                         {r for r in all_rows() if r[0] == VIZIER})
        self.assertEqual("Reduces the Arcane Power cost of Meteor by 50% and increases its damage by 300–400%.", tooltip(VIZIER))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == VIZIER)
        self.assertEqual(("The Grand Vizier", "twohand", "legendary", "yes", "no"),
                         (pool["d3_name"], pool["slot"], pool["rarity"], pool["pool_version"], pool["craft_only"]))
        self.assertEqual(("Wizard", METEOR), OWNERS[VIZIER])      # the record tests cover its aura

    def test_meteor_is_a_wizard_skill_that_states_the_cost_the_cut_is_off(self):
        self.assertIn(METEOR, {r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")})
        cost = next(r for r in read_csv("data/d3/wizard_skill_values.csv") if r["skill"] == METEOR and r["token"] == "cost_resource" and not r["rune"])
        self.assertEqual(40.0, float(cost["value"]))               # 40 Arcane Power, 20 with the staff

    def test_the_rows_have_their_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == VIZIER]
        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertIn("leg_thegrandvizier_p6", row["source"])
            self.assertIn("SF_0 'Resource Cost Reduction' = 0.5", row["source"])     # decode_pow.py power: the cost's number
            self.assertIn("3-4", row["source"])                                         # decode_pow.py item: the damage roll
            self.assertTrue(row["note"])


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None)]
        low, high = source()
        # not worn: no cut, no damage
        out += clear + [(T("skillsum", METEOR, "cost_reduction_pct"), "0"), (T("factor", METEOR, "damage_increase_pct"), "1")]
        # worn, no roll stored: the fixed cut stands, the ranged damage gives nothing
        out += clear + [(T("wears", VIZIER), None), (T("skillsum", METEOR, "cost_reduction_pct"), "50"), (T("factor", METEOR, "damage_increase_pct"), "1")]
        # worn and rolled: 50 off Meteor only, damage x (1 + roll/100) on Meteor only
        for roll in (low, 350, high):
            out += clear + [(T("wears", VIZIER), None), (T("value", VIZIER, METEOR, "damage_increase_pct", roll), None),
                            (T("factor", METEOR, "damage_increase_pct"), "%g" % (1 + roll / 100)), (T("skillsum", METEOR, "cost_reduction_pct"), "50"),
                            (T("factor", "Magic Missile", "damage_increase_pct"), "1"), (T("skillsum", "Magic Missile", "cost_reduction_pct"), "0"),
                            (T("skillsum", "Arcane Torrent", "cost_reduction_pct"), "0"), (T("element", "fire", "cost_reduction_pct"), "0"),
                            (T("factor", METEOR + "x", "damage_increase_pct"), "1")]
        out += clear + [(T("roll", VIZIER, 0), "power:%s:damage_increase_pct=%g;" % (METEOR, (low + high) / 2)),
                        (T("roll", VIZIER, 1), "power:%s:damage_increase_pct=%g;" % (METEOR, high))]
        return out

    def drive(self, header_text, name, rows=None):
        cases = self.cases()
        if rows is not None:
            cases = [("\t".join(("row", *map(str, r))), None) for r in rows] + [c for c in cases if not c[0].startswith("row\t")]
        work, binary = k0k2.Rules.build(header_text, "vizier-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreaterEqual(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mine = [r for r in all_rows() if r[0] == VIZIER]
        cost = next(r for r in mine if r[4] == "cost_reduction_pct")
        damage = next(r for r in mine if r[4] == "damage_increase_pct")
        call = 'ActiveValues(rows, counts, "skill", skill, stat, situation))\n            sum += value;'
        rule_mutants = {
            "the_element_rows": real.replace(call, 'ActiveValues(rows, counts, "element", skill, stat, situation))\n            sum += value;'),
            "the_damage_is_the_cost": real.replace(call, 'ActiveValues(rows, counts, "skill", skill, "damage_increase_pct", situation))\n            sum += value;'),
            "every_skill": real.replace(call, 'ActiveValues(rows, counts, "skill", "Meteor", stat, situation))\n            sum += value;'),
        }
        for name, mutant in rule_mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)
        row_mutants = {
            "the_cut_halved": [(*cost[:5], 25.0, 25.0, *cost[7:]), damage],
            "the_range_halved": [cost, (*damage[:5], damage[5] / 2, damage[6] / 2, *damage[7:])],
            "a_fixed_damage": [cost, (*damage[:5], damage[5], damage[5], *damage[7:])],
            "another_skill": [cost, (*damage[:3], "Hydra", *damage[4:])],
            "no_cut": [damage],
            "no_damage": [cost],
        }
        for name, rows in row_mutants.items():
            want, got = self.drive(real, name, rows)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
