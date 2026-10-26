"""Legendary rest, bead diablocraft-zoe00: Deathwish (Wizard one-hand sword).

  "While channeling Arcane Torrent, Disintegrate, or Ray of Frost for at least 1 second, all damage is increased by [250 - 325]%."
  * the numbers (the roll range 250-325, the one second, the three skills) are read from d3planner (item_onehand.js, leg_deathwish_p6) and
    the skills from wizard_skills.csv, apart from the table; the table (data/legendary_powers.csv) holds ONE `player` row for the pool item
    P61_Unique_Sword_1H_112_x1: `damage_dealt_pct` 250-325 under `channel_held` 1 for the three skills (Mantle of Channeling's condition and
    stat, so its readers are the ones already standing: ItemPowers::DealtFactor and the channel clock), rolled once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: PlayerFactor, Holds) are compiled and driven with the generated row: the factor is
    1 + roll/100 once one of the three skills has been channelled for a second, at both ends of the range, nothing before the second, after
    the channel stopped, for another skill, unworn or with no stored roll, and the clock wrapping does not break it;
  * mutants fail the same driver (a skill lost, a wrong number, the wrong stat, the wrong condition, a one-second rule that is not one,
    a rule that ignores the worn item).
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

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_counter/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P61_Unique_Sword_1H_112_x1"
SKILLS = ("Arcane Torrent", "Disintegrate", "Ray of Frost")
STAT = "damage_dealt_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
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
    """(low, high, seconds, skills) as the planner words them."""
    text = (REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "While channeling (.+?), (.+?), or (.+?) for at least (\d+) seconds?, all damage is increased by %d%%\.", '
                  r'min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[5]), float(m[6]), float(m[4]), (m[1], m[2], m[3])


class Table(unittest.TestCase):
    def test_the_sources_name_the_three_skills_and_the_range(self):
        low, high, seconds, skills = numbers()
        self.assertEqual((250.0, 325.0, 1.0, SKILLS), (low, high, seconds, skills))
        names = [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")]
        for skill in SKILLS:
            self.assertIn(skill, names)

    def test_one_damage_row_holds_while_channelled_for_the_second(self):
        low, high, seconds, skills = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, "channel_held", seconds, ";".join(skills), 0.0, 0, "", "", 100.0, 0.0)], mine())

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("250–325%", m[1])


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemdeath-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        low, high, seconds, _ = numbers()
        out = [(T("row", *r[:7], *(r[7:10] if r[7] else ())), None) for r in rows]
        t = 500000

        def ask(spans, roll, factor, worn=True, now=None):
            lines = ["clear", "now\t%d" % (t if now is None else now)]
            if worn:
                lines.append(T("wears", OWNER, t - 100000))
            if roll is not None:
                lines.append(T("value", OWNER, "", STAT, roll))
            lines += [T("span", *s) for s in spans]
            out.extend((line, None) for line in lines)
            out.append((T("player", STAT, 0), g(factor)))

        held = int(seconds * 1000)
        for skill in SKILLS:                                        # every listed skill, at both ends of the range and between
            for roll in (low, 300, high):
                ask([(skill, t - held, 0, 1)], roll, 1 + roll / 100)
                ask([(skill, t - 60000, 0, 1)], roll, 1 + roll / 100)
            ask([(skill, t - held + 1, 0, 1)], 300, 1)               # not yet the second
            ask([(skill, t - 5000, t - 1, 0)], 300, 1)               # stopped: nothing "after" here
        ask([("Whirlwind", t - 5000, 0, 1)], 300, 1)                 # Mantle's other skill is not this item's
        ask([("Frenzy", t - 5000, 0, 1)], 300, 1)
        ask([("Magic Missile", t - 5000, 0, 1)], 300, 1)
        ask([], 300, 1)                                              # channelling nothing
        ask([("Disintegrate", t - 5000, 0, 1)], 300, 1, worn=False)  # not worn
        ask([("Disintegrate", t - 5000, 0, 1)], None, 1)             # no stored roll: no power
        ask([("Ray of Frost", 4294960000, 0, 1)], 300, 4, now=2000)  # the clock wrapped while it channelled
        ask([("Ray of Frost", 4294966000, 0, 1)], 300, 4, now=100)   # wrapped, held 1.396 s
        ask([("Ray of Frost", 4294967000, 0, 1)], 300, 1, now=100)   # wrapped, held 0.396 s
        out.append((T("player", "damage_taken_pct", 0), "1"))        # only the damage: the stat row is not here
        # the roll: one draw inside the range, a whole range on whole numbers, a Primal at the top (a player row names no skill)
        key = "power::%s" % STAT
        for unit in (0, 0.5, 1):
            out.append((T("powers", OWNER, 0, unit), "%s=%d[%g-%g];" % (key, int(low + unit * (high - low) + 0.5), low, high)))
        out.append((T("powers", OWNER, 1, 0), "%s=%g[%g-%g];" % (key, high, low, high)))
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
        row = rows[0]
        row_mutants = {
            "a_skill_lost": [row[:9] + ("Arcane Torrent;Disintegrate",) + row[10:]],
            "a_skill_added": [row[:9] + (row[9] + ";Whirlwind",) + row[10:]],
            "the_range_halved": [row[:5] + (row[5] / 2, row[6] / 2) + row[7:]],
            "the_wrong_stat": [row[:4] + ("damage_taken_pct",) + row[5:]],
            "the_wrong_condition": [row[:7] + ("channel_or_after",) + row[8:]],
            "two_seconds": [row[:8] + (2.0,) + row[9:]],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_second_is_ignored": real.replace("(situation.now - span->second.start) >= static_cast<std::uint32_t>(row.arg * 1000.0))\n                    return true;",
                                                  "true)\n                    return true;"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
