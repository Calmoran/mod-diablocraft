"""Nilfur's Boast (diablocraft-fxtxo, Wizard legendary list row 93; N-NHIT, Skular's Salvation's count on a Wizard skill): "Increase the damage of Meteor by 600%.
When your Meteor hits 3 or fewer enemies, the damage is increased by [675-900]%."

  * the numbers (the fixed 600, the count 3, the range 675-900) are read from d3planner (item_feet.js, the pool boots P61_Unique_Boots_01 `leg_nilfursboast_p6`);
    the table (data/legendary_powers.csv) holds TWO `skill` rows for them on Meteor: `damage_increase_pct` 600 (fixed) and `damage_increase_pct` 675-900 (rolled
    once per item) under the condition `cast_enemies_at_most` 3. The two sentences are two multipliers of their own (the catalogue's "two effects",
    maxroll's Separate Multipliers), as Skular's Salvation's;
  * the two rows share one skill and stat, so the ranged row must read its OWN stored roll and not the fixed row's number that sits beside it in the item's
    values (`Value::fixed`, Owned): the driver lists both, in both orders, and a mutant that drops the check fails it;
  * the production rules (src/combat/dc_item_power_math.h: Holds' `cast_enemies_at_most`, with SkillFactor / Owned / RollPowers) are compiled and driven with the
    generated rows: a hit in a cast that hits 1 to 3 enemies takes (1 + 600/100) x (1 + N/100), one in a bigger cast, or one no cast counted (the molten ground's
    ticks), takes 1 + 600/100 only; no other skill takes anything; a Primal stores 900;
  * mutants of the rows, the rules and the header fail the same driver;
  * the source-text guards (a Meteor impact counts its area through StrikeArea) are in test_item_power_nilfurs_boast_wiring.py; the C++ is compile-checked by
    syntax_check.sh and the in-game steps are in docs/test-diablocraft-fxtxo.md.
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
from test_item_power_math import all_rows, planner, read_csv, tooltip  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_nilfurs_boast/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
OWNER = "P61_Unique_Boots_01"
SKILL = "Meteor"
RUNES = ("Molten Impact", "Meteor Shower", "Comet", "Star Pact", "Thunder Crash")
STAT = "damage_increase_pct"
COND = "cast_enemies_at_most"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(fixed, count, low, high) as the planner words the pool item's power."""
    text = planner("item_feet.js", OWNER)
    m = re.search(r'format: "Increase the damage of Meteor by (\d+)%%\. When your Meteor hits (\d+) or fewer enemies, the damage is increased by %d%%\.", '
                  r"min: (\d+), max: (\d+)", text)
    assert m, text
    return float(m[1]), int(m[2]), float(m[3]), float(m[4])


class Table(unittest.TestCase):
    def test_the_sources_name_the_skill_the_count_and_the_range(self):
        self.assertEqual((600.0, 3, 675.0, 900.0), numbers())
        self.assertIn(SKILL, {r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")})
        self.assertEqual({"Molten Impact", "Meteor Shower", "Comet", "Star Pact", "Thunder Crash"},
                         {r["rune_name"] for r in read_csv("data/d3/wizard_runes.csv") if r["skill_name"] == SKILL})

    def test_two_damage_rows_name_meteor(self):
        fixed, count, low, high = numbers()
        self.assertEqual({(OWNER, 0, "skill", SKILL, STAT, fixed, fixed, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
                          (OWNER, 0, "skill", SKILL, STAT, low, high, COND, float(count), "", 0.0, 0, "", "", 100.0, 0.0)},
                         set(mine()))
        self.assertEqual(2, len(mine()))
        self.assertEqual("Increase the damage of Meteor by 600%. When your Meteor hits 3 or fewer enemies, the damage is increased by 675–900%.", tooltip(OWNER))

    def test_the_owner_is_the_pool_boots_that_drop(self):
        item = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Nilfur's Boast", "feet", "legendary", "wizard", "yes", "no"),
                         (item["d3_name"], item["slot"], item["rarity"], item["designated_class"], item["pool_version"], item["craft_only"]))

    def test_the_rows_have_their_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertIn("leg_nilfursboast_p6", row["source"])
            self.assertIn("6.75-9", row["source"])                                    # decode_pow.py item: the roll
            self.assertIn("SF_0 'Base Damage Increase' = 6, SF_1 'Max Targets' = 3", row["source"])   # decode_pow.py power: the fixed number and the count
            self.assertTrue(row["note"])

    def test_the_roll_key_fits_the_affix_column(self):
        self.assertLessEqual(len("power:%s:%s" % (SKILL, STAT)), 64)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
        work = Path(tempfile.mkdtemp(prefix="itemnilfur-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        fixed, count, low, high = numbers()
        base = 1 + fixed / 100
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: nothing, whatever the cast
        out += clear + [(T("hit", SKILL, "-", 1), "1")]
        # worn, no roll stored yet: the fixed 600 stands, the ranged row gives no power
        out += clear + [(T("wears", OWNER), None)]
        for enemies in range(0, count + 3):
            out += [(T("hit", SKILL, "-", enemies), g(base))]
        # worn and rolled: every hit takes the fixed 600; a hit in a cast of 1 to `count` enemies takes the roll as a multiplier of its own besides
        for roll in (low, 800, high):
            few = base * (1 + roll / 100)
            # the item's values as WornValues lists them: the fixed row's number and the roll, in either order
            for order in (("fixed", "roll"), ("roll", "fixed")):
                out += clear + [(T("wears", OWNER), None)]
                for kind in order:
                    out += [(T("fixedvalue", OWNER, SKILL, STAT, fixed) if kind == "fixed" else T("value", OWNER, SKILL, STAT, roll), None)]
                for enemies in range(0, count + 12):
                    out += [(T("hit", SKILL, "-", enemies), g(few) if 1 <= enemies <= count else g(base))]
                for rune in RUNES:
                    for enemies in (0, 1, count, count + 1):
                        out += [(T("hit", SKILL, rune, enemies), g(few) if 1 <= enemies <= count else g(base))]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, STAT, 800), None), (T("hit", SKILL, "-", 1), "1")]
        # only Meteor: no other skill takes either row
        out += clear + [(T("wears", OWNER), None), (T("fixedvalue", OWNER, SKILL, STAT, fixed), None), (T("value", OWNER, SKILL, STAT, high), None)]
        for other in ("Hydra", "Arcane Orb", "Meteors", "Meteo", "Meteor Shower", ""):
            for enemies in (1, count + 1):
                out += [(T("hit", other or "-", "-", enemies), "1")]
        # the one roll is stored under the skill's name (the fixed row stores none): a Primal stores the top of the range
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, STAT, high)), (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, STAT, (low + high) / 2))]
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 150)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        few = next(r for r in rows if r[7] == COND)
        fixed = next(r for r in rows if r[7] != COND)
        row_mutants = {
            "the_skill_lost": [few[:3] + ("Hydra",) + few[4:], fixed],
            "the_range_halved": [few[:5] + (few[5] / 2, few[6] / 2) + few[7:], fixed],
            "the_count_of_the_old_item": [few[:8] + (5.0,) + few[9:], fixed],
            "the_count_off_by_one": [few[:8] + (4.0,) + few[9:], fixed],
            "no_condition": [few[:7] + ("", 0.0) + few[9:], fixed],
            "the_fixed_number_halved": [few, fixed[:5] + (fixed[5] / 2, fixed[6] / 2) + fixed[7:]],
            "the_fixed_number_has_the_condition": [few, fixed[:7] + few[7:9] + fixed[9:]],
            "only_the_ranged_row": [few],
            "only_the_fixed_row": [fixed],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        rules = {
            "the_last_count_dropped": ("situation.castEnemies <= row.arg", "situation.castEnemies < row.arg"),
            "one_more_enemy": ("situation.castEnemies <= row.arg", "situation.castEnemies <= row.arg + 1"),
            "an_uncounted_hit_takes_it": ("situation.castEnemies >= 1 && situation.castEnemies <= row.arg", "situation.castEnemies <= row.arg"),
            "every_hit_takes_it": ("return situation.castEnemies >= 1 && situation.castEnemies <= row.arg;", "return true;"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                want, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_fixed_number_is_read_as_the_roll": real.replace("return !v.fixed && v.skill == row.skill && v.stat == row.stat;",
                                                                 "return v.skill == row.skill && v.stat == row.stat;"),
            "an_unworn_item_counts": real.replace("situation.wornSince.count(row.owner)", "true"),
            "a_primal_stores_the_bottom": real.replace("atTop ? Best(row) : roll(row.min, row.max)", "atTop ? row.min : roll(row.min, row.max)"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
