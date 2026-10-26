"""Legendary rest, bead diablocraft-zub4g: Skull Grasp (Barbarian ring).

  "Increase the damage of Whirlwind by [300 - 400]%."
  * the numbers (the roll range 300-400) are read from d3planner (item_finger.js, leg_skullgrasp_p6) and from the legendaries sheet
    (barbarian_legendaries.csv), the skill from barbarian_skills.csv, apart from the table; the table (data/legendary_powers.csv) holds ONE
    `skill` row for the pool item P61_Unique_Ring_02: Whirlwind, `damage_increase_pct`, 300-400, which the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: SkillFactor, RollPowers, Best) are compiled and driven with the generated row:
    Whirlwind takes x(1 + roll/100) while the item is worn and rolled, nothing unworn, unrolled or bagged, no other skill, no other stat,
    and a Primal stores the top of the range;
  * mutants fail the same driver (the skill lost, a wrong number, the wrong stat, a rule that ignores the worn item or the roll);
  * a source-text guard that the hit's legendary term reads the skill's base name and that a Whirlwind tick asks ComputeHit for its hit (the
    C++ is compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-zub4g.md).
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
import barbarian_source  # noqa: E402
import harness_env

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_math/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P61_Unique_Ring_02"
SKILL = "Whirlwind"
STAT = "damage_increase_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
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
    """(low, high) as the planner words them, checked against the legendaries sheet."""
    text = (REPO / "reference/d3planner/item_finger.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Increase the damage of Whirlwind by %d%%", min: (\d+), max: (\d+)', item)
    assert m, item
    sheet = next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == "Skull Grasp")
    assert sheet == "Increase the damage of Whirlwind by [%s - %s]%%." % (m[1], m[2]), sheet
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_name_whirlwind_and_its_range(self):
        self.assertEqual((300.0, 400.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])

    def test_one_damage_row_names_whirlwind(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, *BLANK)], mine())

    def test_whirlwind_is_a_shell(self):
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertRegex(shells, r'\{\d+, "%s", "", ' % SKILL)       # the shell of the skill itself, the one a hit resolves to

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("300–400%", m[1])


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemskull-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: nothing
        out += clear + [(T("factor", SKILL, STAT), "1")]
        # worn, no roll stored yet: the damage has no roll and gives nothing
        out += clear + [(T("wears", OWNER), None), (T("factor", SKILL, STAT), "1")]
        # worn and rolled: x(1 + roll/100), at both ends and between
        for roll in (low, 350, high):
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, roll), None), (T("factor", SKILL, STAT), g(1 + roll / 100))]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, STAT, 350), None), (T("factor", SKILL, STAT), "1")]
        # only Whirlwind, only the damage: no other skill, no other stat of Whirlwind, at the item's best roll
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, high), None)]
        for other in ("Rend", "Hammer of the Ancients", "Cleave", "Frenzy", "Leap", "Ground Stomp", "Magic Missile", "Whirl", "Whirlwind;Rend", ""):
            out += [(T("factor", other, STAT), "1")]
        for stat in ("attack_speed_pct", "dot_duration_seconds", "summon_attack_speed_pct", "dot_max_stacks"):
            out += [(T("factor", SKILL, stat), "1")]
        # one roll stored under the skill's name: a Primal stores the top of the range
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, STAT, high)),
                (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, STAT, (low + high) / 2))]
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
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Rend",) + r[4:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("attack_speed_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_factor_drops_the_one": real.replace(
                'ActiveValues(rows, counts, "skill", skill, stat, situation))\n            factor *= 1.0 + pct / 100.0;',
                'ActiveValues(rows, counts, "skill", skill, stat, situation))\n            factor *= pct / 100.0;'),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
