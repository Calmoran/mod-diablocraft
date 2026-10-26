"""Legendary rest, bead diablocraft-s5ydk: The Shame of Delsere (a belt, any class).

  "Your Signature Spells attack 50% faster and restore [9-12] Arcane Power."
  * the numbers (50, and the roll range 9-12) are read from d3planner (item_waist.js, leg_theshameofdelsere) and the catalogue row, the
    Signature Spells (the Wizard's Primary group) from wizard_skills.csv (category Primary), apart from the table; the table
    (data/legendary_powers.csv) holds one `skill` row, `attack_speed_pct` 50 (fixed) on the four, and one `effect` row, `resource_refund`
    9-12 (rolled once per item) fired on `cast` for the four: every Signature Spell the wearer casts gives the rolled Arcane Power ONCE,
    however many enemies it hits (decisions.md 2026-10-13, the Architect: d3planner's text has no "hit", and Prodigy reads per cast);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: SkillFactor, Fire, Owned, RollPowers) are compiled and driven with the generated
    rows through the power_math and events harnesses: each Signature Spell is 1.5 times as fast while the belt is worn, and its cast gives the
    rolled number, nothing unworn or unrolled, no other skill (a Barbarian primary, a Wizard secondary) takes either, a hit or a
    generator-kind event fires nothing (a cast over five enemies pays once), and a Primal stores 12;
  * mutants fail the same drivers (a spell lost, a wrong number, the wrong event, a rule that ignores the worn item, the roll or the skill list);
  * source-text guards that a pressed cast reaches Fire once as the `cast` event for the skill's base name, that the refund is the class's own
    primary resource (a Wizard's is Arcane Power), and that Prodigy's per-cast gain is called on the same cast; the C++ is
    compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-s5ydk.md.
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
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P4_Unique_Belt_02"
LIST = "Magic Missile;Shock Pulse;Spectral Blade;Electrocute"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%g" % x  # noqa: E731


def signature():
    """The Signature Spells: the Wizard's Primary group, from the skills sheet."""
    return [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv") if r["category"] == "Primary"]


def others():
    """Every skill of the classes Torment has that is not a Signature Spell, and names that only look like one."""
    skills = [r["skill_name"] for sheet in ("barbarian", "wizard") for r in read_csv("data/d3/%s_skills.csv" % sheet) if r["skill_name"] not in signature()]
    return [*skills, "Magic", "Missile", "Magic Missile;Shock Pulse", ""]


def numbers():
    """(attack speed percent, (refund low, refund high)) as the planner words them, checked against the catalogue row."""
    item = planner("item_waist.js", OWNER)
    m = re.search(r'format: "Your Signature Spells attack (\d+)% faster and restore %d Arcane Power.", min: (\d+), max: (\d+)', item)
    assert m, item
    row = next(r for r in read_csv("../docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
    assert row["power_text"] == "Your Signature Spells attack %s%% faster and restore [%s-%s] Arcane Power." % (m[1], m[2], m[3]), row["power_text"]
    return float(m[1]), (float(m[2]), float(m[3]))


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_name_four_signature_spells_and_their_numbers(self):
        self.assertEqual(["Magic Missile", "Shock Pulse", "Spectral Blade", "Electrocute"], signature())
        self.assertEqual((50.0, (9.0, 12.0)), numbers())

    def test_one_speed_row_and_one_refund_row(self):
        speed, (low, high) = numbers()
        self.assertEqual(LIST, ";".join(signature()))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        want = {(OWNER, 0, "skill", LIST, "attack_speed_pct", speed, speed, *blank),
                (OWNER, 0, "effect", "", "resource_refund", low, high, "", 0.0, "", 0.0, 0, "cast", LIST, 100.0, 0.0)}
        self.assertEqual(want, set(mine()))
        self.assertEqual(2, len(mine()))

    def test_each_signature_spell_is_a_free_primary_of_the_wizard(self):
        # "Signature spells are free to cast": the refund is a gain, not a rebate on a cost
        for r in read_csv("data/d3/wizard_skills.csv"):
            if r["skill_name"] in signature():
                self.assertIn("Signature spell", r["full_tooltip_text"])
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        for skill in signature():
            self.assertRegex(shells, r'\{\d+, "%s", "", ' % re.escape(skill))

    def test_the_tooltip_shows_the_rolled_range(self):
        text = tooltip(OWNER)
        self.assertIn("9–12 Arcane Power", text)
        self.assertIn("50% faster", text)

    def test_the_generator_refuses_a_bad_refund(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == "resource_refund")
        bad = {
            "a skill on the refund": dict(base, skill="Magic Missile"),
            "no event": dict(base, fire_on="", fire_skills=""),
            "a skill that does not exist": dict(base, fire_skills="Magic Missile;Not A Skill"),
            "a set bonus with a range": dict(base, owner="Immortal King's Call", pieces="6"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([row])
        self.assertEqual(1, len(power_math.Table.rows_of([base])))


class Rules(unittest.TestCase):
    """The speed row through the power_math harness (SkillFactor, RollPowers), the refund through the events harness (Fire)."""

    def speed_cases(self, rows):
        speed, (low, high) = numbers()
        fast = 1 + speed / 100
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        for skill in signature():
            out += clear + [(T("factor", skill, "attack_speed_pct"), "1")]                                 # not worn
            out += clear + [(T("wears", OWNER), None), (T("factor", skill, "attack_speed_pct"), g(fast)),    # worn: fixed, needs no roll
                            (T("factor", skill, "damage_increase_pct"), "1")]
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, "", "resource_refund", 10), None),   # a stored refund roll changes no speed
                            (T("factor", skill, "attack_speed_pct"), g(fast))]
        out += clear + [(T("wears", OWNER), None)]
        for other in others():
            out += [(T("factor", other, "attack_speed_pct"), "1")]
        # one roll, the effect's, stored under no skill name; the fixed speed row stores none. A Primal takes the top.
        out += [(T("roll", OWNER, 1), "power::resource_refund=%g;" % high), (T("roll", OWNER, 0), "power::resource_refund=%g;" % ((low + high) / 2))]
        return out

    def refund_cases(self, rows):
        _, (low, high) = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        fire = lambda event, skill: T("fire", event, skill, 1, 50, 0)  # noqa: E731
        for skill in signature():
            out += clear + [(fire("cast", skill), "")]                                                         # not worn
            out += clear + [(T("wears", OWNER, 0), None), (fire("cast", skill), "")]                           # worn, no roll stored: nothing
            for roll in (low, 10, 10.5, high):
                refund = "resource_refund=%g;" % roll
                out += clear + [(T("wears", OWNER, 0), None), (T("value", OWNER, "", "resource_refund", roll), None),
                                (fire("cast", skill), refund), (fire("cast", skill), refund),                 # every cast gives it
                                (fire("hit", skill), ""), (fire("hit_generator", skill), ""),                 # only the cast event
                                (fire("hit_spender", skill), ""), (fire("kill", skill), "")]
            out += clear + [(T("value", OWNER, "", "resource_refund", 10), None), (fire("cast", skill), "")]  # rolled, but in the bag
        out += clear + [(T("wears", OWNER, 0), None), (T("value", OWNER, "", "resource_refund", high), None)]
        for other in others():
            out += [(fire("cast", other), "")]
        out += clear + [(T("wears", OWNER, 0), None), (T("value", OWNER, "", "resource_refund", high), None)]
        out += self.multi_target_cast(high)
        return out

    def multi_target_cast(self, refund):
        """A Signature cast over five enemies, as the server raises its events: the cast once, a `hit` for each enemy (Passives::Hit), and the
        cast's one `hit_generator` (Combat::Connected, enemies = 5). The belt pays once, not five times."""
        fire = lambda event, skill: T("fire", event, skill, 1, 50, 0)  # noqa: E731
        out = [(T("enemies", 5), None), (fire("cast", "Magic Missile"), "resource_refund=%g;" % refund)]
        out += [(fire("hit", "Magic Missile"), "")] * 5
        out += [(fire("hit_generator", "Magic Missile"), "")]
        return out

    def drive(self, harness, build, cases, name):
        work, binary = build
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def both(self, header_text, rows, name):
        speed = self.drive("power_math", power_math.Rules.build(header_text, "shame-speed-" + name), self.speed_cases(rows), name)
        refund = self.drive("events", events.Rules.build(header_text, "shame-refund-" + name), self.refund_cases(rows), name)
        return speed, refund

    def test_every_rule_agrees_with_the_sources(self):
        speed, refund = self.both(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(speed[0]), 20)
        self.assertGreater(len(refund[0]), 60)
        self.assertEqual(speed[0], speed[1])
        self.assertEqual(refund[0], refund[1])

    def test_the_mutants_fail_the_same_drivers(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        speed_row = next(r for r in rows if r[2] == "skill")
        refund_row = next(r for r in rows if r[2] == "effect")

        def swap(old, new):
            return [new if r is old else r for r in rows]

        row_mutants = {
            "a_spell_lost": swap(speed_row, speed_row[:3] + (LIST.replace(";Electrocute", ""),) + speed_row[4:]),
            "a_refund_spell_lost": swap(refund_row, refund_row[:13] + (LIST.replace("Magic Missile;", ""),) + refund_row[14:]),
            "the_speed_halved": swap(speed_row, speed_row[:5] + (speed_row[5] / 2, speed_row[6] / 2) + speed_row[7:]),
            "the_refund_range_halved": swap(refund_row, refund_row[:5] + (refund_row[5] / 2, refund_row[6] / 2) + refund_row[7:]),
            "fired_per_enemy_hit": swap(refund_row, refund_row[:12] + ("hit",) + refund_row[13:]),
            "fired_per_cast_that_hit": swap(refund_row, refund_row[:12] + ("hit_generator",) + refund_row[13:]),
            "a_fixed_refund": swap(refund_row, refund_row[:5] + (refund_row[5], refund_row[5]) + refund_row[7:]),
            "no_speed_row": [refund_row],
            "no_refund_row": [speed_row],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                speed, refund = self.both(real, mutant_rows, name)
                self.assertTrue(speed[0] != speed[1] or refund[0] != refund[1], name + " survived")
        header_mutants = {
            "the_skill_list_is_ignored": real.replace("!row.fireSkills.empty() && std::find(row.fireSkills.begin(), row.fireSkills.end(), skill) == row.fireSkills.end()", "false"),
            "the_event_is_ignored": real.replace("row.fireOn != fireOn || !Owned", "!Owned"),
            "the_roll_is_ignored": real.replace("if (!row.pieces && Rolls(row))", "if (false)"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                speed, refund = self.both(header, rows, name)
                self.assertTrue(speed[0] != speed[1] or refund[0] != refund[1], name + " survived")


if __name__ == "__main__":
    unittest.main()
