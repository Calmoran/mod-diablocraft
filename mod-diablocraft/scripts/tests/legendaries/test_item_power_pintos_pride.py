"""Legendary rest, bead diablocraft-3rr7o: Pinto's Pride (Monk bracers), on Jang's Envelopment's N-MONSLOW (diablocraft-9qisl).

  "Wave of Light also Slows enemies by 80% for 3 seconds and deals [125-150]% increased damage."
  * the numbers (80 percent, 3 seconds, 125-150 percent) are read from d3planner (item_wrists.js, leg_pintospride) and the catalogue row and the
    item's tooltip, apart from the table; the table holds THREE rows for the pool item P4_Unique_Bracer_105: a `skill` Wave of Light
    `damage_increase_pct` 125-150 (rolled once per item), an `effect` `slow_pct` 80 (fixed) fired on a `hit` of Wave of Light, and the fixed
    `player` `slow_seconds` 3 beside it;
  * the generated SQL and the committed migration are what the generator renders, the migration the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: SkillFactor of the stored roll, Fire on a `hit` of the named skill, OwnerNumber for
    the seconds, RollPowers) are compiled and driven with the generated rows through Jang's harness: Wave of Light deals x(1 + N/100), every hit
    of it slows by 80 for 3 s, another skill and other events do not, an unworn item does neither; a Primal stores 150;
  * mutants of the rows fail the same driver;
  * source-text guards: every Wave of Light shell names the skill, so SkillFactor reaches every rune; Wave of Light damages through
    Combat::Strike, which reports a non-periodic strike as a hit (Passives::Hit -> ItemPowers::Hit). The slow's executor is Jang's (its guards are
    test_item_power_jangs_envelopment.py's); the in-game steps are in docs/test-diablocraft-3rr7o.md.
"""
import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_legendary_powers as generator  # noqa: E402
import test_item_power_jangs_envelopment as jang  # noqa: E402

MODULE = jang.MODULE
REPO = jang.REPO
OWNER = "P4_Unique_Bracer_105"
SKILL = "Wave of Light"
DAMAGE, SLOW, SECONDS = "damage_increase_pct", "slow_pct", "slow_seconds"
KEY = "power:%s:%s" % (SKILL, DAMAGE)
T = jang.T


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def mine():
    return [r for r in jang.all_rows() if r[0] == OWNER]


def numbers():
    """(slow, seconds, low, high) as the planner words them."""
    text = (REPO / "reference/d3planner/item_wrists.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Wave of Light also Slows enemies by (\d+)%% for (\d+) seconds and deals %d%% increased damage\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2]), float(m[3]), float(m[4])


def expected():
    slow, seconds, low, high = numbers()
    return [(OWNER, 0, "skill", SKILL, DAMAGE, low, high, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
            (OWNER, 0, "effect", "", SLOW, slow, slow, "", 0.0, "", 0.0, 0, "hit", SKILL, 100.0, 0.0),
            (OWNER, 0, "player", "", SECONDS, seconds, seconds, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)]


class Table(unittest.TestCase):
    def test_the_sources_name_wave_of_light_and_the_numbers(self):
        self.assertEqual((80.0, 3.0, 125.0, 150.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv(MODULE / "data/d3/monk_skills.csv")])
        catalogue = [r for r in read_csv(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertIn("Slows enemies by 80% for 3 seconds and deals [125-150]% increased damage", catalogue[0]["power_text"])

    def test_three_rows_name_the_damage_the_slow_and_its_seconds(self):
        self.assertEqual(expected(), mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("Slows enemies by 80% for 3 seconds and deals 125–150% increased damage", m[1])


class Rules(unittest.TestCase):
    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        slow, seconds, low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = lambda roll: clear + [(T("stored", KEY, roll), None), (T("wears", OWNER), None)]  # noqa: E731
        # not worn: no damage, no slow, also with its roll known (in the bag)
        for setup in ([], [(T("bag", OWNER), None)]):
            out += clear + [(T("stored", KEY, 140), None)] + setup + [(T("factor", SKILL, DAMAGE), "1"), (T("fire", "hit", SKILL), "")]
        for roll in (low, 137.5, high):
            # Wave of Light deals the roll more, a multiplier of its own; other skills do not
            out += wear(roll) + [(T("factor", SKILL, DAMAGE), "%g" % (1 + roll / 100)), (T("factor", "Cyclone Strike", DAMAGE), "1"),
                                 (T("factor", "Black Hole", DAMAGE), "1")]
            # each hit of Wave of Light slows by 80, whatever the roll, again and again (no cooldown in the text)
            out += [(T("now", 1000), None), (T("fire", "hit", SKILL), "%s=%g;" % (SLOW, slow)),
                    (T("now", 1001), None), (T("fire", "hit", SKILL), "%s=%g;" % (SLOW, slow))]
            for event, skill in (("hit", "Cyclone Strike"), ("hit", "Black Hole"), ("cast", SKILL), ("taken", ""), ("kill", "")):
                out += wear(roll) + [(T("fire", event, skill), "")]
        # the slow lasts the item's 3 seconds, the aura's amount is -80
        out += [(T("seconds", OWNER), "%g" % seconds), (T("amount", slow), str(-int(slow)))]
        # a Primal stores the top of the damage range; the fixed rows store nothing
        out += [(T("roll", OWNER, 1), "%s=%g;" % (KEY, high)), (T("roll", OWNER, 0), "%s=%g;" % (KEY, (low + high) / 2))]
        return out

    def drive(self, rows, name):
        return jang.Rules.drive(self, jang.MATH.read_text(encoding="utf-8"), rows, "pinto-" + name)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(mine(), "real")
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        rows = mine()
        self.assertEqual(3, len(rows))
        change = lambda stat, at, value: [r[:at] + (value,) + r[at + 1:] if r[4] == stat else r for r in rows]  # noqa: E731
        mutants = {
            "the_damage_fixed": change(DAMAGE, 5, rows[0][6]),
            "the_damage_on_another_skill": change(DAMAGE, 3, "Cyclone Strike"),
            "the_slow_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == SLOW else r for r in rows],
            "the_slow_on_another_skill": change(SLOW, 13, "Cyclone Strike"),
            "the_slow_on_a_cast": change(SLOW, 12, "cast"),
            "the_seconds_doubled": [r[:5] + (r[5] * 2, r[6] * 2) + r[7:] if r[4] == SECONDS else r for r in rows],
            "no_damage_row": [r for r in rows if r[4] != DAMAGE],
            "no_slow_row": [r for r in rows if r[4] != SLOW],
            "no_seconds_row": [r for r in rows if r[4] != SECONDS],
        }
        for name, mutant_rows in mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")


Rules.build = jang.Rules.build


if __name__ == "__main__":
    unittest.main()
