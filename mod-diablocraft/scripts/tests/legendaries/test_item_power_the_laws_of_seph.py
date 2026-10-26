"""Legendary rest, bead diablocraft-cyzna: The Laws of Seph (a Monk Spirit Stone).

  "Using Blinding Flash restores [125-165] Spirit."
  * the range is read from d3planner (item_head.js, leg_thelawsofseph) and the catalogue row; the table (data/legendary_powers.csv) holds one
    `effect` row, `resource_refund` 125-165 (rolled once per item) fired on `cast` of Blinding Flash: every Blinding Flash the wearer presses
    gives the rolled Spirit ONCE, whether it blinds anything or not ("using", as The Shame of Delsere's per-cast refund, decisions.md 2026-10-13);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: Fire, Owned, RollPowers) are compiled and driven with the generated row through the
    events and power_math harnesses: the cast gives the rolled number, nothing unworn or unrolled, no other skill, no hit or kill event, and a
    Primal stores 165;
  * mutants fail the same drivers (a wrong skill, a wrong number, the wrong event, a rule that ignores the worn item, the roll or the skill);
  * source-text guards that every Blinding Flash spell (the skill and its five runes) is a shell of that name, so a pressed one reaches Fire
    as the `cast` event, and that the refund is the class's own primary resource (a Monk's is Spirit); the C++ is unchanged; the in-game
    steps are in docs/test-diablocraft-cyzna.md.
"""
import re
import shutil
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import test_item_power_events as events
import test_item_power_math as power_math
from test_item_power_math import all_rows, planner, read_csv, tooltip

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
OWNER = "Unique_SpiritStone_101_x1"
SKILL = "Blinding Flash"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def numbers():
    """(refund low, refund high) as the planner words them, checked against the catalogue row."""
    item = planner("item_head.js", OWNER)
    m = re.search(r'format: "Using Blinding Flash restores %d Spirit.", min: (\d+), max: (\d+)', item)
    assert m, item
    row = next(r for r in read_csv("../docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
    assert row["power_text"] == "Using Blinding Flash restores [%s-%s] Spirit." % (m[1], m[2]), row["power_text"]
    return float(m[1]), float(m[2])


def others():
    """Every other skill of the classes Torment has, and names that only look like Blinding Flash."""
    skills = [r["skill_name"] for sheet in ("barbarian", "wizard", "monk") for r in read_csv("data/d3/%s_skills.csv" % sheet) if r["skill_name"] != SKILL]
    return [*skills, "Blinding", "Flash", "Blinding Flash;Serenity", ""]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_one_refund_row(self):
        low, high = numbers()
        self.assertEqual((125.0, 165.0), (low, high))
        self.assertEqual([(OWNER, 0, "effect", "", "resource_refund", low, high, "", 0.0, "", 0.0, 0, "cast", SKILL, 100.0, 0.0)], mine())

    def test_the_tooltip_shows_the_rolled_range(self):
        self.assertIn("125–165 Spirit", tooltip(OWNER))

    def test_the_generator_refuses_a_bad_refund(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        bad = {
            "a skill on the refund": dict(base, skill=SKILL),
            "no event": dict(base, fire_on="", fire_skills=""),
            "a skill that does not exist": dict(base, fire_skills="Blinding Flashes"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([row])
        self.assertEqual(1, len(power_math.Table.rows_of([base])))


class Rules(unittest.TestCase):
    """The refund through the events harness (Fire), the roll through the power_math harness (RollPowers)."""

    def refund_cases(self, rows):
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        fire = lambda event, skill: T("fire", event, skill, 1, 50, 0)  # noqa: E731
        out += clear + [(fire("cast", SKILL), "")]                                                          # not worn
        out += clear + [(T("wears", OWNER, 0), None), (fire("cast", SKILL), "")]                            # worn, no roll stored: nothing
        for roll in (low, 140, 150.5, high):
            refund = "resource_refund=%g;" % roll
            out += clear + [(T("wears", OWNER, 0), None), (T("value", OWNER, "", "resource_refund", roll), None),
                            (fire("cast", SKILL), refund), (fire("cast", SKILL), refund),                   # every cast gives it
                            (fire("hit", SKILL), ""), (fire("hit_generator", SKILL), ""),
                            (fire("hit_spender", SKILL), ""), (fire("kill", SKILL), ""), (fire("taken", SKILL), "")]
        out += clear + [(T("value", OWNER, "", "resource_refund", 140), None), (fire("cast", SKILL), "")]   # rolled, but in the bag
        out += clear + [(T("wears", OWNER, 0), None), (T("value", OWNER, "", "resource_refund", high), None)]
        for other in others():
            out += [(fire("cast", other), "")]
        return out

    def roll_cases(self, rows):
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows] + [(T("clear"), None)]
        # one roll, stored under no skill name; a Primal takes the top
        return out + [(T("roll", OWNER, 1), "power::resource_refund=%g;" % high),
                      (T("roll", OWNER, 0), "power::resource_refund=%g;" % ((low + high) / 2))]

    def drive(self, build, cases):
        work, binary = build
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def both(self, header_text, rows, name):
        refund = self.drive(events.Rules.build(header_text, "seph-refund-" + name), self.refund_cases(rows))
        roll = self.drive(power_math.Rules.build(header_text, "seph-roll-" + name), self.roll_cases(rows))
        return refund, roll

    def test_every_rule_agrees_with_the_sources(self):
        refund, roll = self.both(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(refund[0]), 40)
        self.assertEqual(refund[0], refund[1])
        self.assertEqual(roll[0], roll[1])

    def test_the_mutants_fail_the_same_drivers(self):
        real = MATH.read_text(encoding="utf-8")
        [row] = mine()

        def cell(index, *value):
            return [row[:index] + value + row[index + len(value):]]

        row_mutants = {
            "another_skill": cell(13, "Serenity"),
            "the_range_halved": cell(5, row[5] / 2, row[6] / 2),
            "a_fixed_refund": cell(5, row[5], row[5]),
            "fired_per_enemy_hit": cell(12, "hit"),
            "fired_per_cast_that_hit": cell(12, "hit_generator"),
            "no_row": [],
        }
        for name, rows in row_mutants.items():
            with self.subTest(mutant=name):
                refund, roll = self.both(real, rows, name)
                self.assertTrue(refund[0] != refund[1] or roll[0] != roll[1], name + " survived")
        header_mutants = {
            "the_skill_list_is_ignored": real.replace("!row.fireSkills.empty() && std::find(row.fireSkills.begin(), row.fireSkills.end(), skill) == row.fireSkills.end()", "false"),
            "the_event_is_ignored": real.replace("row.fireOn != fireOn || !Owned", "!Owned"),
            "the_roll_is_ignored": real.replace("if (!row.pieces && Rolls(row))", "if (false)"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                refund, roll = self.both(header, [row], name)
                self.assertTrue(refund[0] != refund[1] or roll[0] != roll[1], name + " survived")


if __name__ == "__main__":
    unittest.main()
