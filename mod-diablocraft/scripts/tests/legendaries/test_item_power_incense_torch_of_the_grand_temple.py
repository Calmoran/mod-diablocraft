"""Incense Torch of the Grand Temple (diablocraft-3jl7t, Monk legendary list row 217; N-COST, built by Fury of the Vanished Peak): "Reduces the Spirit cost
of Wave of Light by 50% and increases its damage by [450-550]%."

  * data/legendary_powers.csv gains two `skill` rows for the pool daibo P61_Unique_CombatStaff_2H_003_x1: Wave of Light `cost_reduction_pct` 50 (fixed: the
    text's number) and `damage_increase_pct` 450-550 (rolled once per item); the words and the range come from d3planner (data.json) and are set against
    the tooltip;
  * the spell record (Wave of Light's hidden cost aura in the Monk family, reaching exactly Wave of Light and its five runes, not the Monk cost probe) is
    proved by test_item_power_fury_of_the_vanished_peak.py, whose OWNERS names this item;
  * the production rules (dc_item_power_math.h SkillSum and SkillFactor) are driven with the generated rows through the k0k2 harness, and their mutants fail
    the same driver. The in-game steps are in docs/test-diablocraft-3jl7t.md.
"""
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import test_item_power_math as k0k2  # noqa: E402  (a module, so its test classes are not run twice)
from test_item_power_fury_of_the_vanished_peak import OWNERS  # noqa: E402
from test_item_power_math import all_rows, planner_json, read_csv, tooltip  # noqa: E402

MATH = Path(__file__).resolve().parents[3] / "src/combat/dc_item_power_math.h"
TORCH = "P61_Unique_CombatStaff_2H_003_x1"
WAVE = "Wave of Light"


def source():
    """(text, low, high) as d3planner's data.json words the power."""
    custom = planner_json(TORCH)["required"]["custom"]
    assert custom["format"] == "Reduces the Spirit cost of Wave of Light by 50%% and increases its damage by %d%%.", custom
    return custom["format"] % custom["min"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_rows_are_the_source(self):
        text, low, high = source()
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(TORCH, 0, "skill", WAVE, "cost_reduction_pct", 50.0, 50.0, *blank), (TORCH, 0, "skill", WAVE, "damage_increase_pct", low, high, *blank)},
                         {r for r in all_rows() if r[0] == TORCH})
        self.assertEqual((450.0, 550.0), (low, high))
        self.assertEqual(text.replace("450%", "450–550%"), tooltip(TORCH))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == TORCH)
        self.assertEqual(("Incense Torch of the Grand Temple", "yes", "monk"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))
        self.assertEqual(("Monk", WAVE), OWNERS[TORCH])     # the record tests cover its aura
        cost = next(r for r in read_csv("data/d3/monk_skill_values.csv") if r["skill"] == WAVE and r["token"] == "cost_resource" and not r["rune"])
        self.assertEqual(75.0, float(cost["value"]))          # 75 Spirit, 37.5 with the torch


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None)]
        # not worn: no cut, no damage
        out += clear + [(T("skillsum", WAVE, "cost_reduction_pct"), "0"), (T("factor", WAVE, "damage_increase_pct"), "1")]
        # worn: 50 off Wave of Light only; the Fury weapon's Seismic Slam cut is not the torch's
        out += clear + [(T("wears", TORCH), None), (T("skillsum", WAVE, "cost_reduction_pct"), "50"),
                        (T("skillsum", "Seismic Slam", "cost_reduction_pct"), "0"), (T("skillsum", "Cyclone Strike", "cost_reduction_pct"), "0"),
                        (T("element", "holy", "cost_reduction_pct"), "0")]
        for roll in (450, 500, 550):
            out += clear + [(T("wears", TORCH), None), (T("value", TORCH, WAVE, "damage_increase_pct", roll), None),
                            (T("factor", WAVE, "damage_increase_pct"), "%g" % (1 + roll / 100)), (T("factor", "Cyclone Strike", "damage_increase_pct"), "1"),
                            (T("skillsum", WAVE, "cost_reduction_pct"), "50")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = k0k2.Rules.build(header_text, "torch-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreaterEqual(len(want), 15)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        call = 'ActiveValues(rows, counts, "skill", skill, stat, situation))\n            sum += value;'
        mutants = {
            "the_element_rows": real.replace(call, 'ActiveValues(rows, counts, "element", skill, stat, situation))\n            sum += value;'),
            "the_damage_is_the_cost": real.replace(call, 'ActiveValues(rows, counts, "skill", skill, "damage_increase_pct", situation))\n            sum += value;'),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
