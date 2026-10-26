"""Legendary rest, bead diablocraft-szycu: The Undisputed Champion (Barbarian belt, K4: a skill that carries every rune at once).

  "Frenzy gains the effect of every rune and deals [300-400]% increased damage."
  * the words and the range are read from d3planner (item_waist.js, leg_theundisputedchampion_p68) and the catalogue row; the five runes from
    barbarian_runes.csv;
  * the table (data/legendary_powers.csv) holds TWO rows for the owner: `rune` Frenzy / `all` (given without choosing it, as Mortick's Brace)
    and `skill` Frenzy `damage_increase_pct` 300-400 (a range: it rolls once per item); the generator refuses a bad shape of the rune row;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (dc_item_power_math.h GrantsRune and SkillFactor) are compiled and driven with the generated rows, and their mutants
    fail the same driver;
  * source-text guards for the half that cannot be compiled here: dc_barbarian_primaries.cpp reads each Frenzy rune's effect (Maniac's damage, Sidearm's
    axe, Vanguard's movement, Smite's bolt, Berserk's Fury) from the rune's own row when the chosen rune is not it and a power gives it, outside
    the primaries lock; their mutants (the old reads put back, one at a time) fail the same guards. The C++ is compile-checked by
    syntax_check.sh; the in-game steps are in docs/test-diablocraft-szycu.md.
"""
import csv
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_legendary_powers as generator  # noqa: E402
import harness_env  # noqa: E402
import test_item_power_fury as fury  # noqa: E402  (modules, so their test classes are not run twice)
import test_item_power_math as power_math  # noqa: E402
import test_item_power_k4 as k4  # noqa: E402
from test_item_power_math import GENERATED, read_csv  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
OWNER, MORTICK = "P68_Unique_BarbBelt_006", "P2_Unique_Bracer_003"
SKILL, STAT = "Frenzy", "damage_increase_pct"
RUNES = ("Maniac", "Sidearm", "Vanguard", "Smite", "Berserk")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def numbers():
    """(damage low, damage high) as the planner words them, checked against the catalogue's row."""
    text = (REPO / "reference/d3planner/item_waist.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("\n  },", start)]
    m = re.search(r'custom: \{id: "leg_theundisputedchampion_p68", [^}]*format: "Frenzy gains the effect of every rune and deals %d%% increased '
                  r'damage\.", min: (\d+), max: (\d+)\}', item)
    assert m, item
    with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
        row = next(r for r in csv.DictReader(stream, strict=True) if r["d3_id"] == OWNER)
    assert row["power_text"] == "Frenzy gains the effect of every rune and deals [%s-%s]%% increased damage." % (m[1], m[2]), row["power_text"]
    assert row["skills"] == SKILL, row["skills"]
    return float(m[1]), float(m[2])


def mine():
    return [r for r in fury.all_rows() if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_name_the_numbers(self):
        self.assertEqual((300.0, 400.0), numbers())

    def test_the_five_runes_are_frenzys(self):
        self.assertEqual(set(RUNES), {r["rune_name"] for r in read_csv("data/d3/barbarian_runes.csv") if r["skill_name"] == SKILL})

    def test_two_rows_are_the_whole_power(self):
        low, high = numbers()
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(OWNER, 0, "rune", SKILL, "all", 1.0, 1.0, *blank), (OWNER, 0, "skill", SKILL, STAT, low, high, *blank)}, set(mine()))
        self.assertEqual(2, len(mine()))

    def test_the_tooltip_shows_the_rolled_range(self):
        text = fury.tooltip(OWNER)
        self.assertIn("Frenzy gains the effect of every rune", text)
        self.assertIn("300–400%", text)

    def test_the_generator_refuses_a_bad_shape(self):
        rune = next(r for r in read_csv("data/legendary_powers.csv") if (r["owner"], r["kind"]) == (OWNER, "rune"))
        refused = {
            "a rune of another skill": dict(rune, stat="Insanity"),
            "a rune that is not one": dict(rune, stat="Not A Rune"),
            "a skill that is not one": dict(rune, skill="Not A Skill"),
            "a rune given twice over": dict(rune, value_min="2", value_max="2"),
            "a rune on a condition": dict(rune, cond="quiet_stacks", cond_arg="1"),
            "no source": dict(rune, source=""),
        }
        for name, row in refused.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([row])
        self.assertEqual(1, len(power_math.Table.rows_of([rune])))
        self.assertEqual(1, len(power_math.Table.rows_of([dict(rune, stat="Smite")])))      # one named rune is as good a row as `all`

    def test_the_newest_table_is_not_yet_shipped(self):
        self.assertNotIn(GENERATED.name, (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))


class Rules(unittest.TestCase):
    def cases(self):
        low, high = numbers()
        out = [(T("row", *r), None) for r in fury.all_rows()]
        clear = [(T("clear"), None), (T("now", 100000), None)]
        # not worn: nothing given, Frenzy as it is
        out += clear + [(T("rune", SKILL, rune, 0), "0") for rune in RUNES]
        out += [(T("factor", SKILL, STAT, 0), "1")]
        # worn: every rune of Frenzy given (and any name asked, as `all` means), no other skill's rune
        out += clear + [(T("wears", OWNER, 0), None)]
        out += [(T("rune", SKILL, rune, 0), "1") for rune in RUNES]
        out += [(T("rune", SKILL, "Not A Rune", 0), "1"), (T("rune", "Cleave", "Broad Sweep", 0), "0"),
                (T("rune", "Wrath of the Berserker", "Insanity", 0), "0"), (T("rune", "Whirlwind", "Dust Devils", 0), "0")]
        # no stored roll, no damage; the stored roll is the multiplier of its own, and only Frenzy's
        out += [(T("factor", SKILL, STAT, 0), "1")]
        for roll in (low, 333, (low + high) / 2, high):
            out += clear + [(T("wears", OWNER, 0), None), (T("value", OWNER, SKILL, STAT, roll), None),
                            (T("factor", SKILL, STAT, 0), "%g" % (1 + roll / 100)), (T("factor", "Cleave", STAT, 0), "1"),
                            (T("factor", "Weapon Throw", STAT, 0), "1"), (T("factor", SKILL, "attack_speed_pct", 0), "1")]
        # not the item's roll when the item is not worn
        out += clear + [(T("value", OWNER, SKILL, STAT, high), None), (T("factor", SKILL, STAT, 0), "1"), (T("rune", SKILL, "Smite", 0), "0")]
        # with Mortick's Brace: each gives its own skill's runes only
        out += clear + [(T("wears", OWNER, 0), None), (T("wears", MORTICK, 0), None),
                        (T("rune", SKILL, "Smite", 0), "1"), (T("rune", "Wrath of the Berserker", "Insanity", 0), "1"),
                        (T("rune", "Cleave", "Broad Sweep", 0), "0")]
        out += clear + [(T("wears", MORTICK, 0), None), (T("rune", SKILL, "Smite", 0), "0")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = k4.Rules.build(header_text, "champion-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rules_agree_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 30)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        factor = 'for (double pct : ActiveValues(rows, counts, "skill", skill, stat, situation))\n            factor *= 1.0 + pct / 100.0;'
        grants = 'return !ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||\n               !ActiveValues(rows, counts, "rune", skill, "all", situation).empty();'
        mutants = {
            "all_is_ignored": real.replace(grants, grants.replace('"all"', '"Smite"')),
            "the_rune_skill_is_ignored": real.replace(grants, grants.replace('"rune", skill, rune', '"rune", "Frenzy", rune')
                                                      .replace('"rune", skill, "all"', '"rune", "Frenzy", "all"')),
            "the_stat_is_ignored": real.replace(factor, factor.replace("skill, stat, situation", 'skill, "damage_increase_pct", situation')),
            "the_skill_is_ignored": real.replace(factor, factor.replace("skill, stat, situation", '"Frenzy", stat, situation')),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
