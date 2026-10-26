"""Legendary rest, bead diablocraft-9c2kv: Crystal Fist (Monk fist weapon, K3: a cast opens a triggered damage reduction).

  "Dashing Strike reduces your damage taken by [40-50]% for 6 seconds."
  * the numbers (40-50, 6 seconds) are read from d3planner (item_onehand.js, leg_crystalfist) and the catalogue row; Dashing Strike is a
    Monk skill the player presses, and every rune shell of it is the skill Dashing Strike to the cast hook;
  * the table (data/legendary_powers.csv) holds ONE `player` row: `damage_reduction_pct` 40-50 (a range: rolls once per item), condition
    `triggered` for 6 s, fired on a `cast` of Dashing Strike (Band of Might's shape); the generator refuses a bad shape of it;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: Fire, Holds, ReductionFactor, RollPowers) are compiled and driven with the
    generated row: a Dashing Strike cast takes the damage taken down by the item's stored roll, for 6000 ms (the end inclusive) and not 6001,
    a recast (the next charge) renews it, no other skill's cast or other event opens it, nothing unworn or unrolled, a Primal stores the top;
  * mutants fail the same driver (the row changed, one rule at a time; the rules' own header mutants are Girdle of Giants' and Halo of
    Karini's, the same Fire and Holds);
  * source-text guards for the half that cannot be compiled here: the cast hook and the incoming damage read. The in-game steps are in
    docs/test-diablocraft-9c2kv.md. No C++ changed.
"""
import re
import shutil
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import test_item_power_girdle_of_giants as girdle
from test_item_power_girdle_of_giants import GENERATED, MIGRATION, MODULE, REPO, SRC, MATH, read_csv, read_csv_path, all_rows

OWNER = "P41_Unique_Fist_008"
TRIGGER, STAT = "Dashing Strike", "damage_reduction_pct"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%g" % x  # noqa: E731


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(reduction low, reduction high, window seconds) as the planner words them, checked against the catalogue's row."""
    text = (REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("\n  },", start)]
    m = re.search(r'custom: \{id: "leg_crystalfist", [^}]*format: "Dashing Strike reduces your damage taken by %d%% for (\d+) seconds\.", '
                  r'min: (\d+), max: (\d+)\}', item)
    assert m, item
    row = next(r for r in read_csv_path(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
    assert row["power_text"] == "Dashing Strike reduces your damage taken by [%s-%s]%% for %s seconds." % (m[2], m[3], m[1]), row["power_text"]
    assert row["skills"] == TRIGGER, row["skills"]
    return float(m[2]), float(m[3]), float(m[1])


class Table(unittest.TestCase):
    def test_the_sources_name_the_numbers(self):
        self.assertEqual((40.0, 50.0, 6.0), numbers())

    def test_dashing_strike_is_a_pressed_monk_skill_and_every_rune_is_it(self):
        sheet = {r["skill_name"]: r for r in read_csv("data/d3/monk_skills.csv")}
        self.assertIn(TRIGGER, sheet)
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        # the skill's own shell and its five runes all answer Shells::FindAbility with the skill's name, which the cast event fires with
        self.assertRegex(shells, r'\{\d+, "%s", "", ' % TRIGGER)
        runes = {r["rune_name"] for r in read_csv("data/d3/monk_runes.csv") if r["skill_name"] == TRIGGER}
        self.assertEqual(5, len(runes))
        for rune in runes:
            self.assertRegex(shells, r'\{\d+, "%s", "%s", ' % (TRIGGER, re.escape(rune)))

    def test_one_row_is_the_whole_power(self):
        low, high, window = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, "triggered", window, "", 0.0, 0, "cast", TRIGGER, 100.0, 0.0)], mine())

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("40–50%", m[1])
        self.assertIn("for 6 seconds", m[1])

    def test_the_generator_refuses_a_bad_shape(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        refused = {
            "triggered with no event": dict(base, fire_on="", fire_skills=""),
            "a cast with no skill": dict(base, fire_skills=""),
            "an unknown casting skill": dict(base, fire_skills="Dashing Strikes"),
            "triggered with no seconds": dict(base, cond_arg=""),
            "triggered with cond_skills": dict(base, cond_skills=TRIGGER),
            "an event without triggered": dict(base, cond="", cond_arg=""),
            "a player row naming a skill": dict(base, skill=TRIGGER),
            "a negative reduction": dict(base, value_min="-50", value_max="-40"),
            "no source": dict(base, source=""),
        }
        for name, row in refused.items():
            with self.subTest(name), self.assertRaises(ValueError):
                girdle.Table.rows_of([row])
        self.assertEqual(1, len(girdle.Table.rows_of([base])))

    def test_the_sql_row_of_the_cast_window(self):
        sql = girdle.generator.render(MODULE)
        self.assertIn("('%s',0,'player','','%s',40,50,'triggered',6,'',0,0,'cast','%s',100,0)" % (OWNER, STAT, TRIGGER), sql)

    def test_the_newest_table_is_not_yet_shipped(self):
        self.assertNotIn(MIGRATION.name, (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))
        # the table before this bead's own fold (0053) is left as written: it does not carry Crystal Fist (a later fold, Hellrack's 0054, is the newest)
        self.assertNotIn(OWNER, (MODULE / "data/sql/db-world/updates/legendary_powers_0052_table.sql").read_text(encoding="utf-8"))
        self.assertIn(OWNER, (MODULE / "data/sql/db-world/updates/legendary_powers_0053_table.sql").read_text(encoding="utf-8"))


class Rules(unittest.TestCase):
    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        low, high, window = numbers()
        ms = int(window * 1000)
        out = [(T("row", *r), None) for r in rows]
        start = [(T("clear"), None), (T("now", 10000), None), (T("wears", OWNER, 0), None), (T("value", OWNER, "", STAT, 45), None)]
        fire = lambda event, skill: (T("fire", event, skill, 1, 0, 0), "")  # noqa: E731
        reduction = T("reduction", 0)
        down = g(1 - 45 / 100)

        # nothing fired: no reduction; the cast opens it at the item's stored roll
        out += start + [(reduction, "1"), fire("cast", TRIGGER), (reduction, down)]
        # the window is 6 s, the end inclusive
        out += [(T("now", 10000 + ms), None), (reduction, down), (T("now", 10000 + ms + 1), None), (reduction, "1")]
        # a certain row (no chance) fires whatever the draw
        out += start + [(T("fire", "cast", TRIGGER, 1, 99, 0), ""), (reduction, down)]
        # a recast (the next charge) renews it from the new cast
        out += [(T("now", 13000), None), fire("cast", TRIGGER), (T("now", 13000 + ms), None), (reduction, down),
                (T("now", 13000 + ms + 1), None), (reduction, "1")]
        # another Monk skill's cast opens nothing; neither does another event of Dashing Strike
        out += start
        for other in ("Fists of Thunder", "Tempest Rush", "Lashing Tail Kick", "Wave of Light", "Furious Charge", "Dashing", "Strike", ""):
            out += [fire("cast", other), (reduction, "1")]
        for event in ("hit", "kill", "kill_elite", "taken", "hit_spender", "hit_generator"):
            out += [fire(event, TRIGGER), (reduction, "1")]
        # once open it is the player's reduction, not a damage or speed number
        out += start + [fire("cast", TRIGGER), (T("player", "damage_dealt_pct", 0), "1"), (T("player", "damage_taken_pct", 0), "1")]
        # the stored roll is the number, at both ends and between
        for roll in (low, 45, high):
            out += [(T("clear"), None), (T("now", 10000), None), (T("wears", OWNER, 0), None), (T("value", OWNER, "", STAT, roll), None),
                    fire("cast", TRIGGER), (reduction, g(1 - roll / 100))]
        # not worn, a roll in the bag, worn with no stored roll: nothing opens
        out += [(T("clear"), None), (T("now", 10000), None), fire("cast", TRIGGER), (reduction, "1")]
        out += [(T("clear"), None), (T("now", 10000), None), (T("value", OWNER, "", STAT, 45), None), fire("cast", TRIGGER), (reduction, "1")]
        out += [(T("clear"), None), (T("now", 10000), None), (T("wears", OWNER, 0), None), fire("cast", TRIGGER), (reduction, "1")]
        # taken off inside the window: the reduction goes with it
        out += start + [fire("cast", TRIGGER), (reduction, down), (T("clear"), None), (T("now", 10000), None), (reduction, "1")]
        # ONE roll of the item: a Primal takes the top, an ordinary item rolls in the range
        out += [(T("roll", OWNER, 1), "power::%s=%g;" % (STAT, high)), (T("roll", OWNER, 0), "power::%s=%g;" % (STAT, (low + high) / 2))]
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = girdle.Rules.build(header_text, "crystal-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_sources(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "no_rows": [],
            "the_window_is_5_s": [r[:8] + (5.0,) + r[9:] for r in rows],
            "the_window_is_7_s": [r[:8] + (7.0,) + r[9:] for r in rows],
            "no_condition": [r[:7] + ("",) + r[8:] for r in rows],
            "fired_by_another_skill": [r[:13] + ("Tempest Rush",) + r[14:] for r in rows],
            "fired_by_a_hit": [r[:12] + ("hit",) + r[13:] for r in rows],
            "damage_taken_not_reduction": [r[:4] + ("damage_taken_pct",) + r[5:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "a_fixed_number_not_a_range": [r[:6] + (r[5],) + r[7:] for r in rows],
            "an_internal_cooldown": [r[:15] + (5.0,) for r in rows],
            "a_chance": [r[:14] + (50.0,) + r[15:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
