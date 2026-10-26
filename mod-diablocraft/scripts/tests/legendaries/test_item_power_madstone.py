"""Madstone (diablocraft-b1ymb, Monk legendary list row 241, on Gungdo Gear's N-APPLYAURA): "Your Seven-Sided Strike applies Exploding Palm."

  * data/legendary_powers.csv gains one row for the pool Spirit Stone P1_Unique_SpiritStone_008: `effect` `apply_skill` Exploding Palm fired on `hit` of
    Seven-Sided Strike (a certain row: no chance, no internal cooldown, no number to roll); the words come from d3planner and are set against the tooltip;
  * the production rule (dc_item_power_math.h Fire) is driven with the generated rows through the k4 harness: every hit of Seven-Sided Strike applies the
    palm while the stone is worn, with any proc coefficient, and nothing else does; its mutants fail the same driver;
  * the generator refuses the shapes it cannot stand behind (no skill to fire on, a skill the code cannot apply, a number);
  * source-text guards that each strike of Seven-Sided Strike reaches the `hit` event through Combat::Strike (Passives::Hit -> ItemPowers::Hit with the
    enemy struck, both for the single strike and Fulminating Onslaught's area), and that `apply_skill` reaches Exploding Palm's palm (Gungdo's guards,
    reused); the C++ is unchanged and the in-game steps are in docs/test-diablocraft-b1ymb.md.
"""
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import test_item_power_k4 as k4  # noqa: E402
from test_item_power_math import GENERATED, planner, read_csv  # noqa: E402
from test_item_power_fury import all_rows, tooltip  # noqa: E402
from test_item_power_gungdo_gear_wiring import Hooks as GungdoHooks, hook_rules  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
MADSTONE = "P1_Unique_SpiritStone_008"
PALM, STRIKE = "Exploding Palm", "Seven-Sided Strike"
TEXT = "Your Seven-Sided Strike applies Exploding Palm."


class Table(unittest.TestCase):
    def test_the_row_is_the_source(self):
        item = planner("item_head.js", MADSTONE)
        self.assertIn('custom: {id: "leg_madstone", name: "Auto Exploding Palm", format: "%s", args: 0}' % TEXT, item)
        self.assertEqual([(MADSTONE, 0, "effect", PALM, "apply_skill", 1.0, 1.0, "", 0.0, "", 0.0, 0, "hit", STRIKE, 100.0, 0.0)],
                         [r for r in all_rows() if r[0] == MADSTONE])
        self.assertEqual(TEXT, tooltip(MADSTONE))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == MADSTONE)
        self.assertEqual(("Madstone", "head", "legendary", "yes", "monk", "no"),
                         (pool["d3_name"], pool["slot"], pool["rarity"], pool["pool_version"], pool["designated_class"], pool["craft_only"]))
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == MADSTONE)
        self.assertIn("leg_madstone", row["source"])
        self.assertTrue(row["note"])

    def test_the_generator_refuses_what_it_cannot_stand_behind(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == MADSTONE)
        self.assertEqual(1, len(k4.Table.rows_of([base])))
        bad = {
            "an apply the code cannot do": dict(base, skill="Seven-Sided Strike"),
            "a hit of a skill that does not exist": dict(base, fire_skills="Seven Sided Strike"),
            "no event": dict(base, fire_on="", fire_skills=""),
            "no skill applied": dict(base, skill=""),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                k4.Table.rows_of([row])


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        none = k4.Rules.sets()
        apply_ = "apply_skill(Exploding Palm)=1;"
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        # not worn: a strike applies nothing
        out += clear + [(T("fire", "hit", STRIKE, 1, 99, *none), "")]
        # worn: every hit of the strike applies the palm, whatever its proc coefficient (a certain row), again and again; nothing else does
        out += clear + [(T("wears", MADSTONE, 0), None)]
        out += [(T("fire", "hit", STRIKE, 1, 99, *none), apply_), (T("fire", "hit", STRIKE, 0.1, 0, *none), apply_),
                (T("fire", "hit", STRIKE, 1, 0, *none), apply_),
                (T("fire", "hit", PALM, 1, 0, *none), ""), (T("fire", "hit", "Lashing Tail Kick", 1, 0, *none), ""),
                (T("fire", "cast", STRIKE, 1, 0, *none), ""), (T("fire", "hit_spender", STRIKE, 1, 0, *none), ""),
                (T("fire", "explosion", PALM, 1, 0, *none), ""), (T("fire", "kill", "", 1, 0, *none), "")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = k4.Rules.build(header_text, "madstone-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 8)
        self.assertEqual(GENERATED.read_text(encoding="utf-8").count("\n("), len(all_rows()))
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "any_skill_fires_it": real.replace(
                "if (!row.fireSkills.empty() && std::find(row.fireSkills.begin(), row.fireSkills.end(), skill) == row.fireSkills.end())\n                continue;",
                ""),
            "any_event_fires_it": real.replace("if (row.fireOn != fireOn || !Owned(row, counts, situation, number))",
                                               "if (!Owned(row, counts, situation, number))"),
            "the_chance_scales_a_certain_row": real.replace("if (row.chancePct < 100 && !(row.chancePct * scale > 0 && roll(row.chancePct * scale)))",
                                                            "if (!(row.chancePct * scale >= 100))"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
