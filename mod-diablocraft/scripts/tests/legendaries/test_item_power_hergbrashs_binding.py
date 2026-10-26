"""Hergbrash's Binding (diablocraft-uynen, Wizard legendary list row 85; N-COST, built by Fury of the Vanished Peak): "Reduces the Arcane Power cost of Arcane
Torrent, Disintegrate, and Ray of Frost by [50-65]%."

  * data/legendary_powers.csv gains ONE `skill` row for the pool belt P4_Unique_Belt_06: `cost_reduction_pct` 50-65 on the three skills joined by ';' (one
    roll, rolled once per item, shared by the three); the words and the range come from d3planner (item_waist.js) and are set against the tooltip;
  * the spell records (a hidden cost aura for each of the three skills in the Wizard family, reaching exactly that skill's records, the channels' included) are
    proved by test_item_power_fury_of_the_vanished_peak.py, whose COST_SKILLS names them;
  * the production rule (dc_item_power_math.h SkillSum) is driven with the generated row through the k0k2 harness: the roll is the cut of each of the three
    skills and of no other, a Primal stores 65, and its mutants fail the same driver. The in-game steps are in docs/test-diablocraft-uynen.md.
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
from test_item_power_fury_of_the_vanished_peak import HERGBRASH, HERGBRASH_SKILLS  # noqa: E402
from test_item_power_math import all_rows, planner, read_csv, tooltip  # noqa: E402

MATH = Path(__file__).resolve().parents[3] / "src/combat/dc_item_power_math.h"
LIST = ";".join(HERGBRASH_SKILLS)
STAT = "cost_reduction_pct"


def source():
    """(low, high) as d3planner's item file words the power."""
    text = planner("item_waist.js", HERGBRASH)
    m = re.search(r'format: "Reduces the Arcane Power cost of Arcane Torrent, Disintegrate, and Ray of Frost by %d%%\.", min: (\d+), max: (\d+)', text)
    assert m, text
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_row_is_the_source(self):
        low, high = source()
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual((50.0, 65.0), (low, high))
        self.assertEqual([(HERGBRASH, 0, "skill", LIST, STAT, low, high, *blank)], [r for r in all_rows() if r[0] == HERGBRASH])
        self.assertEqual("Reduces the Arcane Power cost of Arcane Torrent, Disintegrate, and Ray of Frost by 50–65%.", tooltip(HERGBRASH))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == HERGBRASH)
        self.assertEqual(("Hergbrash's Binding", "waist", "legendary", "wizard", "yes", "no"),
                         (pool["d3_name"], pool["slot"], pool["rarity"], pool["designated_class"], pool["pool_version"], pool["craft_only"]))

    def test_each_skill_is_a_wizard_skill_that_states_a_cost(self):
        wizard = {r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")}
        costed = {r["skill"] for r in read_csv("data/d3/wizard_skill_values.csv") if r["token"] == "cost_resource" and not r["rune"]}
        for skill in HERGBRASH_SKILLS:
            self.assertIn(skill, wizard)
            self.assertIn(skill, costed)

    def test_the_row_has_its_source(self):
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == HERGBRASH)
        self.assertIn("leg_hergbrashsbinding", row["source"])
        self.assertIn("item_waist.js", row["source"])
        self.assertIn("0.5-0.65", row["source"])         # decode_pow.py item: the item's own roll
        self.assertTrue(row["note"])


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None)]
        low, high = source()
        # not worn: no cut
        out += clear + [(T("skillsum", skill, STAT), "0") for skill in HERGBRASH_SKILLS]
        # worn with no stored roll: a ranged row with no roll gives nothing
        out += clear + [(T("wears", HERGBRASH), None)] + [(T("skillsum", skill, STAT), "0") for skill in HERGBRASH_SKILLS]
        # worn and rolled: the roll is each of the three skills' cut, and nothing off another skill (Meteor has its own staff), the damage stat or an element
        for roll in (low, 57, high):
            out += clear + [(T("wears", HERGBRASH), None), (T("value", HERGBRASH, LIST, STAT, roll), None)]
            out += [(T("skillsum", skill, STAT), "%g" % roll) for skill in HERGBRASH_SKILLS]
            out += [(T("skillsum", other, STAT), "0") for other in ("Meteor", "Magic Missile", "Arcane Torrent;Disintegrate", "Disinteg", "")]
            out += [(T("skillsum", HERGBRASH_SKILLS[0], "damage_increase_pct"), "0"), (T("element", "arcane", STAT), "0")]
        # the roll is made once for the three: one key under the first skill's name, a Primal takes the top
        out += clear + [(T("roll", HERGBRASH, 0), "power:%s:%s=%g;" % (HERGBRASH_SKILLS[0], STAT, (low + high) / 2)),
                        (T("roll", HERGBRASH, 1), "power:%s:%s=%g;" % (HERGBRASH_SKILLS[0], STAT, high))]
        return out

    def drive(self, header_text, name, rows=None):
        cases = self.cases()
        if rows is not None:
            cases = [(line, want) for line, want in cases if not line.startswith("row\t")]
            cases = [("\t".join(("row", *map(str, r))), None) for r in rows] + cases
        work, binary = k0k2.Rules.build(header_text, "hergbrash-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreaterEqual(len(want), 35)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        row = next(r for r in all_rows() if r[0] == HERGBRASH)
        call = 'ActiveValues(rows, counts, "skill", skill, stat, situation))\n            sum += value;'
        rule_mutants = {
            "the_element_rows": real.replace(call, 'ActiveValues(rows, counts, "element", skill, stat, situation))\n            sum += value;'),
            "the_damage_is_the_cost": real.replace(call, 'ActiveValues(rows, counts, "skill", skill, "damage_increase_pct", situation))\n            sum += value;'),
            "an_unworn_item_counts": real.replace("situation.wornSince.count(row.owner)", "true"),
        }
        for name, mutant in rule_mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)
        row_mutants = {
            "a_skill_lost": [(*row[:3], ";".join(HERGBRASH_SKILLS[:2]), *row[4:])],
            "the_range_halved": [(*row[:5], row[5] / 2, row[6] / 2, *row[7:])],
            "a_fixed_cut": [(*row[:5], row[5], row[5], *row[7:])],
            "no_row": [],
        }
        for name, rows in row_mutants.items():
            want, got = self.drive(real, name, rows)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
