"""Legendary rest, bead diablocraft-sjctu: Lefebvre's Soliloquy (Monk shoulders). No new C++: one row of the existing table.

  "Cyclone Strike reduces your damage taken by [40 - 50]% for 5 seconds."
  * the range (40-50) and the 5 seconds are read from d3planner (item_shoulders.js, leg_lefebvressoliloquy; the power file P4_ItemPassive_Unique_Ring_078 states
    no number of its own, the item 0.4-0.5) and the tooltip text from the generated crafting table; the table (data/legendary_powers.csv) holds ONE `player` row
    for the pool item P4_Unique_Shoulder_101: `damage_reduction_pct`, 40-50, `triggered` for 5 s, fired by a `cast` of Cyclone Strike, which the roller rolls once
    per item (Band of Might's and Spirit Guards' shape);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: Fire, the `triggered` window, ReductionFactor, RollPowers) are compiled and driven with the generated
    row: a cast of Cyclone Strike opens 5 s of reduction at the stored roll (the window ends exactly 5000 ms later, the next cast renews it), nothing opens for
    another skill or event, an unworn or unrolled item has no power, two sources multiply, a Primal stores 60; mutants of the rule and of the row fail the same driver;
  * source-text guards that a cast of Cyclone Strike reaches the cast event (OnSpellCast -> ItemPowers::Cast -> Fire "cast" for any skill with a shell row, every
    rune answering with the skill) and that nothing in the combat code names the item; the in-game steps are in docs/test-diablocraft-sjctu.md.
"""
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import item_power_cast_window as cast_window  # noqa: E402
from item_power_cast_window import read_csv  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
OWNER = "P4_Unique_Shoulder_101"
STAT = "damage_reduction_pct"
SKILLS = ["Cyclone Strike"]
CELL = ";".join(SKILLS)


def numbers():
    """(low, high, seconds) as the planner words them."""
    text = (REPO / "reference/d3planner/item_shoulders.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Cyclone Strike reduces your damage taken by %d%% for (\d+) seconds\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[2]), float(m[3]), float(m[1])


class Table(unittest.TestCase):
    def test_the_sources_name_the_range_the_seconds_and_the_skill(self):
        self.assertEqual((40.0, 50.0, 5.0), numbers())
        self.assertIn("Cyclone Strike", [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv")])

    def test_one_row_opens_five_seconds_on_a_cast_of_cyclone_strike(self):
        low, high, seconds = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, "triggered", seconds, "", 0.0, 0, "cast", CELL, 100.0, 0.0)], ITEM.mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Cyclone Strike reduces your damage taken by 40–50% for 5 seconds.", m[1])


ITEM = cast_window.Item(
    owner=OWNER, skills=SKILLS, numbers=numbers, other="Other Shoulders", mid_roll=45, cast="Cyclone Strike", recast=("Cyclone Strike", "Cyclone Strike"),
    quiet_skill="Cyclone Strike", ignored=("Tempest Rush", "Wave of Light", "Fists of Thunder", "Whirlwind", "Magic Missile", "Cyclone Strikex", ""),
    idle_roll=50, shorter=3.0,
    skill_mutants={"another_skill": "Tempest Rush", "a_skill_added": CELL + ";Tempest Rush"}, scratch_prefix="itemlefebvre")


class Rules(cast_window.RulesTests, unittest.TestCase):
    ITEM = ITEM

    @staticmethod
    def run_binary(command):
        return harness_env.run(command, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
