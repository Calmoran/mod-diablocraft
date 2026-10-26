"""Gungdo Gear (diablocraft-ph20t, Monk legendary list row 227; builds N-APPLYAURA): "Exploding Palm's on-death explosion applies Exploding Palm. Exploding
Palm's damage is increased by [75-100]%."

  * data/legendary_powers.csv gains two rows for the pool bracers P610_Unique_Bracer_006: `effect` `apply_skill` Exploding Palm fired on the new event
    `explosion` of Exploding Palm, and `skill` Exploding Palm `damage_increase_pct` 75-100 (rolled once per item); the words and the range come from d3planner
    (data.json) and are set against the tooltip;
  * the production rules (dc_item_power_math.h Fire and SkillFactor) are driven with the generated rows through the k4 harness, and their mutants fail the same
    driver;
  * the generator refuses an explosion row it cannot stand behind (no skill, a skill whose code fires no explosion, skills on another event) and an apply of a
    skill the code cannot apply;
  * source-text guards that Exploding Palm's explosion fires the event on every enemy it reaches before its damage, that the event fires the rows, and that
    the `apply_skill` effect reaches Exploding Palm's own palm through Monk::Apply (they prove the calls are there, not that they run; the C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-ph20t.md).
"""
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import test_item_power_k4 as k4  # noqa: E402  (a module, so its test classes are not run twice)
from test_item_power_math import GENERATED, planner_json, read_csv  # noqa: E402
from test_item_power_fury import all_rows, tooltip  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
GUNGDO = "P610_Unique_Bracer_006"
PALM, STAT = "Exploding Palm", "damage_increase_pct"


def source():
    """(text, low, high) as d3planner's data.json words the power."""
    custom = planner_json(GUNGDO)["required"]["custom"]
    assert custom["format"] == ("Exploding Palm's on-death explosion applies Exploding Palm. Exploding Palm's damage is increased by %d%%."), custom
    return custom["format"] % custom["min"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_rows_are_the_source(self):
        text, low, high = source()
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(GUNGDO, 0, "effect", PALM, "apply_skill", 1.0, 1.0, "", 0.0, "", 0.0, 0, "explosion", PALM, 100.0, 0.0),
                          (GUNGDO, 0, "skill", PALM, STAT, low, high, *blank)},
                         {r for r in all_rows() if r[0] == GUNGDO})
        self.assertEqual((75.0, 100.0), (low, high))
        self.assertEqual(text.replace("75%", "75–100%"), tooltip(GUNGDO))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == GUNGDO)
        self.assertEqual(("Gungdo Gear", "yes", "monk"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))

    def test_the_generator_refuses_an_explosion_it_cannot_stand_behind(self):
        base = {"owner": GUNGDO, "pieces": "", "kind": "effect", "skill": PALM, "stat": "apply_skill", "value_min": "1", "value_max": "1",
                "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "explosion", "fire_skills": PALM,
                "chance_pct": "", "icd_seconds": "", "source": "x", "note": ""}
        self.assertEqual(1, len(k4.Table.rows_of([base])))
        self.assertEqual(1, len(k4.Table.rows_of([dict(base, fire_on="hit", fire_skills="Seven-Sided Strike")])))  # Madstone's shape
        bad = {
            "an explosion that names no skill": dict(base, fire_skills=""),
            "an explosion of a skill whose code fires none": dict(base, fire_skills="Wave of Light"),
            "an explosion of a skill that does not exist": dict(base, fire_skills="Not A Skill"),
            "skills on a kill": dict(base, fire_on="kill"),
            "an apply the code cannot do": dict(base, skill="Wave of Light"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                k4.Table.rows_of([row])


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        _, low, high = source()
        none = k4.Rules.sets()
        apply_ = "apply_skill(Exploding Palm)=1;"
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        # not worn: the explosion applies nothing, no damage
        out += clear + [(T("fire", "explosion", PALM, 1, 99, *none), ""), (T("factor", PALM, STAT, 0), "1")]
        # worn: every explosion of the palm applies it (no chance, no internal cooldown); nothing else does
        out += clear + [(T("wears", GUNGDO, 0), None)]
        out += [(T("fire", "explosion", PALM, 1, 99, *none), apply_), (T("fire", "explosion", PALM, 1, 0, *none), apply_),
                (T("fire", "explosion", "Rend", 1, 0, *none), ""), (T("fire", "hit", PALM, 1, 0, *none), ""),
                (T("fire", "kill", "", 1, 0, *none), ""), (T("fire", "cast", PALM, 1, 0, *none), "")]
        # worn and rolled: 1 + N/100, only Exploding Palm's
        for roll in (low, 90, high):
            out += clear + [(T("wears", GUNGDO, 0), None), (T("value", GUNGDO, PALM, STAT, roll), None),
                            (T("factor", PALM, STAT, 0), "%.10g" % (1 + roll / 100)), (T("factor", "Wave of Light", STAT, 0), "1")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = k4.Rules.build(header_text, "gungdo-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 10)
        self.assertEqual(GENERATED.read_text(encoding="utf-8").count("\n("), len(all_rows()))     # every generated row parsed
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "any_skill_fires_it": real.replace(
                "if (!row.fireSkills.empty() && std::find(row.fireSkills.begin(), row.fireSkills.end(), skill) == row.fireSkills.end())\n                continue;",
                ""),
            "any_event_fires_it": real.replace("if (row.fireOn != fireOn || !Owned(row, counts, situation, number))",
                                               "if (!Owned(row, counts, situation, number))"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
