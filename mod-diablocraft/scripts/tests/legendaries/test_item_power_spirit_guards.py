"""Legendary rest, bead diablocraft-1ays9: Spirit Guards (bracers, class any, Monk in effect). No new C++: one row of the existing table.

  "Your Spirit Generators reduce your damage taken by [45 - 60]% for 3 seconds."
  * the range (45-60) and the 3 seconds are read from d3planner (item_wrists.js, leg_spiritguards_p6) and the tooltip text from the generated crafting table;
    the skills are the four Primary skills of monk_skills.csv (the Spirit Generators); the table (data/legendary_powers.csv) holds ONE `player` row for the pool
    item P61_Unique_Bracer_109: `damage_reduction_pct`, 45-60, `triggered` for 3 s, fired by a `cast` of any of the four, which the roller rolls once per item
    (Band of Might's shape; the class-free `hit_generator` is not used, so a Barbarian's or Wizard's primaries open nothing);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: Fire, the `triggered` window, ReductionFactor, RollPowers) are compiled and driven with the generated
    row: a cast of each of the four opens 3 s of reduction at the stored roll (the window ends exactly 3000 ms later, the next cast renews it), nothing opens for
    another skill or event, an unworn or unrolled item has no power, two sources multiply, a Primal stores 60; mutants of the rule and of the row fail the same driver;
  * source-text guards that a cast of a Monk primary reaches the cast event (CombatCastCheck -> ItemPowers::Cast -> Fire "cast" for any skill with a shell row)
    and that nothing in the combat code names the item; the in-game steps are in docs/test-diablocraft-1ays9.md.
"""
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import item_power_cast_window as cast_window
from item_power_cast_window import read_csv

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
OWNER = "P61_Unique_Bracer_109"
STAT = "damage_reduction_pct"
SKILLS = ["Fists of Thunder", "Deadly Reach", "Crippling Wave", "Way of the Hundred Fists"]
CELL = ";".join(SKILLS)


def numbers():
    """(low, high, seconds) as the planner words them."""
    text = (REPO / "reference/d3planner/item_wrists.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Your Spirit Generators reduce your damage taken by %d%% for (\d+) seconds\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[2]), float(m[3]), float(m[1])


class Table(unittest.TestCase):
    def test_the_sources_name_the_range_the_seconds_and_the_four_generators(self):
        self.assertEqual((45.0, 60.0, 3.0), numbers())
        primaries = [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv") if r["category"] == "Primary"]
        self.assertEqual(sorted(SKILLS), sorted(primaries))

    def test_one_row_opens_three_seconds_on_a_cast_of_the_four(self):
        low, high, seconds = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, "triggered", seconds, "", 0.0, 0, "cast", CELL, 100.0, 0.0)], ITEM.mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Your Spirit Generators reduce your damage taken by 45–60% for 3 seconds.", m[1])


ITEM = cast_window.Item(
    owner=OWNER, skills=SKILLS, numbers=numbers, other="Other Bracers", mid_roll=52.5, cast="Fists of Thunder", recast=("Deadly Reach", "Crippling Wave"),
    quiet_skill="Deadly Reach", ignored=("Tempest Rush", "Cleave", "Frenzy", "Whirlwind", "Magic Missile", "Fists of Thunderx", ""),
    idle_roll=60, shorter=2.0,
    skill_mutants={"a_generator_lost": "Fists of Thunder;Deadly Reach;Crippling Wave", "a_spender_added": CELL + ";Tempest Rush"}, scratch_prefix="itemguards")


class Rules(cast_window.RulesTests, unittest.TestCase):
    ITEM = ITEM

    @staticmethod
    def run_binary(command):
        return harness_env.run(command, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
