"""Legendary rest, bead diablocraft-yep9j: Pride of Cassius (Barbarian Mighty Belt), the bead that builds N-DUR (a skill's duration lengthened by an item).

  "Increases the duration of Ignore Pain by [4 - 6] seconds."
  * the numbers (the roll range 4-6 seconds) are read from d3planner (item_waist.js, leg_prideofcassius) and from the legendaries sheet
    (barbarian_legendaries.csv), the skill and its seconds from barbarian_skills.csv / barbarian_skill_values.csv, apart from the table; the table
    (data/legendary_powers.csv) holds ONE `skill` row for the pool item Unique_BarbBelt_002_x1: Ignore Pain, `duration_add_seconds`, 4-6, which the
    roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the
    stat for Ignore Pain, refuses it for a skill nothing reads it for, and refuses a zero or negative number, a condition and a set bonus;
  * the production rule (src/combat/dc_item_power_math.h: DurationSeconds, with Owned / Holds / RollPowers) is compiled and driven with the generated row:
    the skill's own duration (its base number, or Iron Hide's) plus the item's seconds, only for Ignore Pain, only while the item is worn and rolled,
    never for a skill that has no duration (0 stays 0); a Primal stores 6;
  * mutants of the rule and of the row fail the same driver (two sources add);
  * source-text guards that Ignore Pain's cast adds it to the duration it marks the player with and the Mob Rule allies with; the C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-yep9j.md.
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
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_pride_of_cassius/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_BarbBelt_002_x1"
SKILL = "Ignore Pain"
STAT = "duration_add_seconds"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(low, high) seconds as the planner words them, checked against the legendaries sheet."""
    text = (REPO / "reference/d3planner/item_waist.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Increases the duration of Ignore Pain by %d seconds\.", min: (\d+), max: (\d+)', item)
    assert m, item
    sheet = next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == "Pride of Cassius")
    assert sheet == "Increases the duration of Ignore Pain by [%s - %s] seconds." % (m[1], m[2]), sheet
    return float(m[1]), float(m[2])


def skill_seconds(rune=""):
    return float(next(r["value"] for r in read_csv("data/d3/barbarian_skill_values.csv")
                      if r["skill"] == SKILL and r["rune"] == rune and r["token"] == "duration_seconds"))


class Table(unittest.TestCase):
    def test_the_sources_name_ignore_pain_and_the_range(self):
        self.assertEqual((4.0, 6.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])
        self.assertEqual((5.0, 7.0), (skill_seconds(), skill_seconds("Iron Hide")))

    def test_one_row_names_ignore_pain(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, *BLANK)], mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("duration of Ignore Pain by 4–6 seconds", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "4", "value_max": "6", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="cassius-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min <= value_max"),
            "a negative number": ({"value_min": "-6", "value_max": "-4"}, "needs 0 < value_min <= value_max"),
            "not a skill": ({"skill": "Ignore Painx"}, "is not a skill"),
            "a skill nothing reads it for": ({"skill": "Cleave"}, "duration"),
            "several skills": ({"skill": "Ignore Pain;Sprint"}, "duration"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": "Ignore Pain"}, "duration"),
            "a set bonus": ({"pieces": "2"}, "not a set"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemcassius-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        low, high = numbers()
        base, iron = skill_seconds(), skill_seconds("Iron Hide")
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        worn = lambda roll: clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, roll), None)]  # noqa: E731
        # not worn: the skill's own seconds
        out += clear + [(T("duration", SKILL, base), g(base))]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("duration", SKILL, base), g(base))]
        # worn and rolled: the skill's own seconds plus the roll, for the base number and for Iron Hide's, at both ends and between
        for roll in (low, 4.5, 5, high):
            out += worn(roll) + [(T("duration", SKILL, base), g(base + roll)), (T("duration", SKILL, iron), g(iron + roll))]
        # a skill with no duration stays at none; a negative is no duration either
        out += worn(high) + [(T("duration", SKILL, 0), "0"), (T("duration", SKILL, -1), "-1")]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, STAT, 5), None), (T("duration", SKILL, base), g(base))]
        # only Ignore Pain
        out += worn(high)
        for other in ("Sprint", "War Cry", "Call of the Ancients", "Wrath of the Berserker", "Ignore", "Ignore Pain Rune", "Ignore Pains", ""):
            out += [(T("duration", other, 20), "20")]
        # a second owner's rows add to the first's: two belts' seconds sum
        out += worn(high) + [(T("wears", "Other Belt"), None), (T("value", "Other Belt", SKILL, STAT, 3), None),
                             (T("duration", SKILL, base), g(base + high + 3))]
        # the range rolls once per item (a Primal stores the top)
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, STAT, high)), (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, STAT, (low + high) / 2))]
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

    def test_every_rule_agrees_with_the_item_text(self):
        other = [("Other Belt", 0, "skill", SKILL, STAT, 3.0, 3.0, *BLANK)]
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + other, "real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        other = [("Other Belt", 0, "skill", SKILL, STAT, 3.0, 3.0, *BLANK)]
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Sprint",) + r[4:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mine() + other, name + "-want")
                _, got = self.drive(real, mutant_rows + other, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("// N-DUR: the seconds"):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "no_roll_still_adds": ('if (base <= 0.0)', 'if (false)'),
            "added_to_a_zero_duration": ('if (base <= 0.0)\n            return base;', ''),
            "the_stat_dropped": ('"duration_add_seconds"', '"damage_increase_pct"'),
            "the_skill_ignored": ('"skill", skill, "duration_add_seconds"', '"skill", "Ignore Pain", "duration_add_seconds"'),
            "multiplied_not_added": ("base += add;", "base *= add;"),
            "only_the_first_source": ("base += add;", "return base + add;"),
            "subtracted": ("base += add;", "base -= add;"),
            "seconds_read_as_ms": ("base += add;", "base += add * 1000.0;"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                want, got = self.drive(real, mine() + other, name + "-want")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), mine() + other, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
