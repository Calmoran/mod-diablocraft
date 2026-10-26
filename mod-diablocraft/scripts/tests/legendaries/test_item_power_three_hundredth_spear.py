"""Legendary rest, bead diablocraft-6dzud: The Three Hundredth Spear (Barbarian one-hand spear, P73_Unique_Spear_002).

  "Increase the damage of Weapon Throw and Ancient Spear by [150-200]%. The attack speed of Weapon Throw is increased by 200%."
  * the numbers (the roll range 150-200 and the fixed 200) are read from d3planner (data.json, leg_thethreehundredthspear_p73) and the
    tooltip the item data carries; the skills from barbarian_skills.csv, apart from the table; the table (data/legendary_powers.csv) holds
    a `skill` row that lists Weapon Throw and Ancient Spear joined by ';' for `damage_increase_pct` (the range the roller rolls once per
    item, so the two share one roll) and a `skill` row for Weapon Throw alone, `attack_speed_pct` 200 (fixed); each skill is a spell
    shell the hit resolves to (dc_spell_shells.h);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: SkillFactor, RollPowers, Best) are compiled and driven with the generated rows:
    Weapon Throw takes x(1 + roll/100) and is 3 times as fast, Ancient Spear takes x(1 + roll/100) only, while the item is worn and rolled,
    nothing unworn or unrolled (the fixed speed stands once worn), no other skill, and a Primal stores the top of the range;
  * mutants fail the same driver (a skill lost, a wrong number, the wrong stat, the speed leaking to Ancient Spear, a rule that ignores the
    worn item or the roll);
  * a source-text guard that the two readers (the hit's legendary term and a skill's swing recovery) read the base skill name of a
    shell (the C++ is compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-6dzud.md).
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_math/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P73_Unique_Spear_002"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
LIST = "Weapon Throw;Ancient Spear"
THROW = "Weapon Throw"
SPEAR = "Ancient Spear"
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(attack speed percent, (damage low, damage high)) as the planner words them, apart from the table."""
    data = (REPO / "reference/d3planner/data.json").read_text(encoding="utf-8")
    start = data.index('"id":"%s"' % OWNER)
    item = data[start:data.index('"preset"', start)]
    m = re.search(r'"format":"Increase the damage of Weapon Throw and Ancient Spear by %d%%\. The attack speed of Weapon Throw is increased by (\d+)%%",'
                  r'"min":(\d+),"max":(\d+)', item)
    assert m, item
    return float(m[1]), (float(m[2]), float(m[3]))


class Table(unittest.TestCase):
    def test_the_sources_name_the_two_skills_and_their_numbers(self):
        self.assertEqual((200.0, (150.0, 200.0)), numbers())
        names = {r["skill_name"]: r["category"] for r in read_csv("data/d3/barbarian_skills.csv")}
        self.assertEqual("Primary", names[THROW])
        self.assertEqual("Secondary", names[SPEAR])

    def test_one_damage_row_lists_both_skills_and_one_speed_row_names_weapon_throw(self):
        speed, (low, high) = numbers()
        want = {(OWNER, 0, "skill", LIST, "damage_increase_pct", low, high, *BLANK),
                (OWNER, 0, "skill", THROW, "attack_speed_pct", speed, speed, *BLANK)}
        self.assertEqual(want, set(mine()))
        self.assertEqual(2, len(mine()))

    def test_each_skill_is_a_shell(self):
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        for skill in (THROW, SPEAR):
            # a shell of the skill itself (rune ""), the one the hit resolves to when no rune is chosen
            self.assertRegex(shells, r'\{\d+, "%s", "", ' % re.escape(skill))

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("150–200%", m[1])
        self.assertIn("Weapon Throw is increased by 200%", m[1])


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemspear-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        speed, (low, high) = numbers()
        fast = 1 + speed / 100
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        others = ("Frenzy", "Bash", "Cleave", "Whirlwind", "Hammer of the Ancients", "Rend", "Leap", "Magic Missile", "Throw", "Weapon", "Spear",
                  "Weapon Throw;Ancient Spear", "")
        for skill in (THROW, SPEAR):
            # the speed belongs to Weapon Throw alone
            sped = fast if skill == THROW else 1
            # not worn: nothing
            out += clear + [(T("factor", skill, "attack_speed_pct"), "1"), (T("factor", skill, "damage_increase_pct"), "1")]
            # worn, no roll stored yet: the speed is a fixed number and stands, the damage has no roll and gives nothing
            out += clear + [(T("wears", OWNER), None), (T("factor", skill, "attack_speed_pct"), g(sped)), (T("factor", skill, "damage_increase_pct"), "1")]
            # worn and rolled: x(1 + roll/100), at both ends and between
            for roll in (low, 175, high):
                out += clear + [(T("wears", OWNER), None), (T("value", OWNER, LIST, "damage_increase_pct", roll), None),
                                (T("factor", skill, "damage_increase_pct"), g(1 + roll / 100)), (T("factor", skill, "attack_speed_pct"), g(sped))]
            # a roll stored but the item in the bag
            out += clear + [(T("value", OWNER, LIST, "damage_increase_pct", 175), None), (T("factor", skill, "damage_increase_pct"), "1"),
                            (T("factor", skill, "attack_speed_pct"), "1")]
        # only the two: no other skill takes either number, at the item's best roll
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, LIST, "damage_increase_pct", high), None)]
        for other in others:
            out += [(T("factor", other, "attack_speed_pct"), "1"), (T("factor", other, "damage_increase_pct"), "1")]
        # the power's other stats are not read: a duration, a summon's speed
        for skill in (THROW, SPEAR):
            out += [(T("factor", skill, "dot_duration_seconds"), "1"), (T("factor", skill, "summon_attack_speed_pct"), "1")]
        # the two share ONE roll, stored under the first name: a Primal stores the top of the range, and nothing for the fixed speed row
        out += [(T("roll", OWNER, 1), "power:%s:damage_increase_pct=%g;" % (THROW, high)),
                (T("roll", OWNER, 0), "power:%s:damage_increase_pct=%g;" % (THROW, (low + high) / 2))]
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

    def test_every_rule_agrees_with_the_sources(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        speed_rows = [r for r in rows if r[4] == "attack_speed_pct"]
        damage_rows = [r for r in rows if r[4] == "damage_increase_pct"]
        row_mutants = {
            "a_skill_lost": [r[:3] + (THROW if r[4] == "damage_increase_pct" else SPEAR,) + r[4:] for r in rows],
            "the_speed_leaks_to_the_spear": [r[:3] + (LIST,) + r[4:] if r[4] == "attack_speed_pct" else r for r in rows],
            "the_speed_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == "attack_speed_pct" else r for r in rows],
            "the_damage_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == "damage_increase_pct" else r for r in rows],
            "the_stats_swapped": [r[:4] + ({"attack_speed_pct": "damage_increase_pct", "damage_increase_pct": "attack_speed_pct"}[r[4]],) + r[5:] for r in rows],
            "no_damage_rows": speed_rows,
            "no_speed_rows": damage_rows,
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "only_the_whole_list_matches": real.replace("NamesSkill(row.skill, skill) && row.stat == stat && Owned", "row.skill == skill && row.stat == stat && Owned"),
            "a_name_matches_by_part": real.replace("names.compare(from, to - from, skill) == 0", "names.compare(from, to - from, skill) <= 0 && names.find(skill) != std::string::npos"),
            "the_roll_key_is_the_whole_list": real.replace('"power:" + FirstSkill(row.skill) + ":" + row.stat', '"power:" + row.skill + ":" + row.stat'),
            "a_fixed_row_rolls": real.replace("return !row.pieces && row.kind != \"stat\" && row.min < row.max;", "return !row.pieces && row.kind != \"stat\" && row.min <= row.max;"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
