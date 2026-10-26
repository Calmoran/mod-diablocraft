"""Legendary rest, bead diablocraft-a2rln: Dishonored Legacy (Barbarian one-hand Mighty Weapon).

  "Cleave deals up to [300 - 400]% increased damage based on percentage of missing Fury."
  * the numbers (the roll range 300-400) are read from d3planner (item_onehand.js, leg_dishonoredlegacy) and from the legendaries sheet
    (barbarian_legendaries.csv), the skill from barbarian_skills.csv, the resource from class_resources.csv, apart from the table; the table
    (data/legendary_powers.csv) holds ONE `skill` row for the pool item Unique_Mighty_1H_103_x1: Cleave, `damage_by_missing_resource_pct`,
    300-400, which the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    accepts the stat as a skill stat and still refuses a zero or negative number;
  * the production rule (src/combat/dc_item_power_math.h: MissingResourceFactor, with Owned / Holds / RollPowers) is compiled and driven with
    the generated row: "up to N%" by the percent of the primary resource missing, 1 + N/100 x missing/100, continuous, so a hit at full Fury
    takes nothing and a hit at no Fury takes the whole N; only Cleave, only while the item is worn and rolled; a Primal stores 400;
  * mutants of the rule and of the row fail the same driver (a sum in place of a product, with two weapons worn);
  * source-text guards that the hit multiplies the factor into its legendary term with the base skill name, that the reader reads the
    resource before the power lock, and that the sheet reads the resource only when a row names this stat; the C++ is compile-checked by
    syntax_check.sh and the in-game steps are in docs/test-diablocraft-a2rln.md.
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
HARNESS = MODULE / "tests/item_power_dishonored_legacy/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Mighty_1H_103_x1"
SKILL = "Cleave"
STAT = "damage_by_missing_resource_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731
TEXT = "Cleave deals up to %d%% increased damage based on percentage of missing Fury."


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
    text = (REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Cleave deals up to %d%% increased damage based on percentage of missing Fury\.", min: (\d+), max: (\d+)', item)
    assert m, item
    sheet = next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == "Dishonored Legacy")
    assert sheet == "Cleave deals up to [%s - %s]%% increased damage based on percentage of missing Fury." % (m[1], m[2]), sheet
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_name_cleave_fury_and_the_range(self):
        self.assertEqual((300.0, 400.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])
        # the Barbarian's primary resource is Fury, the one the reader takes the missing percent of (Resources::Of, the primary role)
        fury = [r for r in read_csv("data/d3/class_resources.csv") if r["d3_class"] == "Barbarian" and r["role"] == "primary"]
        self.assertEqual(["fury"], [r["resource_key"] for r in fury])

    def test_one_damage_row_names_cleave(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, *BLANK)], mine())

    def test_cleave_is_a_shell(self):
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertRegex(shells, r'\{\d+, "%s", "", ' % SKILL)       # the shell of the skill itself, the one a hit resolves to

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("300–400%", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "300", "value_max": "400", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        """The generator run on a copy of the module whose sheet is the real one with the owner's row replaced by `edits` (dicts over BASE)."""
        work = Path(tempfile.mkdtemp(prefix="dishonored-gen-", dir=str(SCRATCH)))
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
        own = "needs 0 < value_min <= value_max"
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, own),
            "a negative number": ({"value_min": "-400", "value_max": "-300"}, own),
            "not a skill": ({"skill": "Cleavex"}, "is not a skill"),
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
        work = Path(tempfile.mkdtemp(prefix="itemdishonored-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        factor = lambda roll, missing: g(1 + roll / 100 * missing / 100)  # noqa: E731
        # not worn: nothing, whatever is missing
        out += clear + [(T("missing", SKILL, 0), "1")]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("missing", SKILL, 0), "1")]
        # worn and rolled: "up to N%" by the percent missing, continuous, at both ends of the roll and between
        for roll in (low, 350, high):
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, roll), None)]
            for missing in (0, 1, 12.5, 25, 33.3, 50, 66.7, 75, 99, 99.5, 100):
                out += [(T("missing", SKILL, 100 - missing), factor(roll, missing))]
        # nothing missing at full Fury; the whole N at no Fury (the "up to")
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, high), None),
                        (T("missing", SKILL, 100), "1"), (T("missing", SKILL, 0), g(1 + high / 100))]
        # a resource past its maximum or below none is read as full or empty, never a negative or a bigger factor
        out += [(T("missing", SKILL, 130), "1"), (T("missing", SKILL, -20), g(1 + high / 100))]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, STAT, 350), None), (T("missing", SKILL, 0), "1")]
        # only Cleave: no other skill, a skill list that does not name it, nothing for the empty name
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, high), None)]
        for other in ("Rend", "Whirlwind", "Frenzy", "Bash", "Hammer of the Ancients", "Magic Missile", "Cleav", "Cleave Rune", ""):
            out += [(T("missing", other, 0), "1")]
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

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 50)
        self.assertEqual(want, got)

    def two_sources(self, header_text, name):
        """The output for two weapons that each own a row of the stat, worn together, at half Fury."""
        low, high = numbers()
        rows = mine() + [("Other Weapon", 0, "skill", SKILL, STAT, 100.0, 100.0, *BLANK)]
        cases = [T("row", *r) for r in rows] + [T("wears", OWNER), T("value", OWNER, SKILL, STAT, high), T("wears", "Other Weapon"),
                                                  T("value", "Other Weapon", SKILL, STAT, 100), T("missing", SKILL, 50)]
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_two_sources_multiply(self):
        """A second owner of the same stat (another weapon with its own number) is a multiplier of its own: the factors multiply, and a sum fails."""
        low, high = numbers()
        real = MATH.read_text(encoding="utf-8")
        self.assertEqual([g((1 + high / 100 * 50 / 100) * (1 + 100 / 100 * 50 / 100))], self.two_sources(real, "two"))
        old = "factor *= 1.0 + pct / 100.0 * missing / 100.0;"
        self.assertIn(old, real)
        self.assertNotEqual(self.two_sources(real, "two"), self.two_sources(real.replace(old, "factor += pct / 100.0 * missing / 100.0;"), "sum"))

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Rend",) + r[4:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double MissingResourceFactor"):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "missing_is_the_resource": ("100.0 - situation.resourcePct", "situation.resourcePct"),
            "no_clamp": ("std::clamp(100.0 - situation.resourcePct, 0.0, 100.0)", "100.0 - situation.resourcePct"),
            "whole_points_only": ("std::clamp(100.0 - situation.resourcePct, 0.0, 100.0)", "std::floor(std::clamp(100.0 - situation.resourcePct, 0.0, 100.0))"),
            "missing_ignored": ("pct / 100.0 * missing / 100.0", "pct / 100.0"),
            "percent_unscaled": ("pct / 100.0 * missing / 100.0", "pct / 100.0 * missing"),
            "the_stat_dropped": ('"skill", skill, "damage_by_missing_resource_pct", situation', '"skill", skill, "damage_increase_pct", situation'),
            "the_skill_ignored": ('"skill", skill, "damage_by_missing_resource_pct"', '"skill", "Cleave", "damage_by_missing_resource_pct"'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                want, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
