"""Legendary rest, bead diablocraft-atyj0: Band of Rue Chambers (a ring, class any, Monk in effect), the bead that builds `resource_generation_pct`.

  "Your Spirit Generators generate [40 - 50]% more Spirit."
  * the range (40-50) is read from d3planner (item_finger.js, leg_bandofruechambers) and the item's tooltip text from the generated crafting table; the
    skills are the four Primary skills of monk_skills.csv (the Spirit Generators); the table (data/legendary_powers.csv) holds ONE `skill` row for the pool
    item Unique_Ring_106_x1 naming all four, `resource_generation_pct`, 40-50, which the roller rolls once per item (Oathkeeper's shape);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the
    stat for the four generators, refuses it for any other skill, and refuses a zero or negative number, a condition and a set bonus;
  * the production rule (src/combat/dc_item_power_math.h: SkillFactor, with Owned / Holds / RollPowers) is compiled and driven with the generated row:
    1 + N/100 for each of the four generators while the ring is worn and rolled, 1 for every other skill, 1 for an unworn or unrolled ring, two sources
    multiply, a Primal stores 50; mutants of the rule and of the row fail the same driver;
  * source-text guards that every Spirit a Monk primary generates is multiplied by Monk::SpiritFactor (the per-attack pay and Rising Tide's per-enemy pay),
    and that SpiritFactor reads the stat through ItemPowers::SkillFactor on the skill of the spell; the C++ is compile-checked by syntax_check.sh and the
    in-game steps are in docs/test-diablocraft-atyj0.md.
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
HARNESS = MODULE / "tests/item_power_band_of_rue_chambers/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Ring_106_x1"
STAT = "resource_generation_pct"
SKILLS = ["Fists of Thunder", "Deadly Reach", "Crippling Wave", "Way of the Hundred Fists"]
CELL = ";".join(SKILLS)
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
    """(low, high) percent as the planner words them."""
    text = (REPO / "reference/d3planner/item_finger.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Your Spirit Generators generate %d%% more Spirit\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_name_the_range_and_the_four_generators(self):
        self.assertEqual((40.0, 50.0), numbers())
        primaries = [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv") if r["category"] == "Primary"]
        self.assertEqual(sorted(SKILLS), sorted(primaries))
        self.assertEqual(sorted(SKILLS), sorted(generator.GENERATION_SKILLS))

    def test_one_row_names_the_four_generators(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", CELL, STAT, low, high, *BLANK)], mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Your Spirit Generators generate 40–50% more Spirit.", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": CELL, "stat": STAT, "value_min": "40", "value_max": "50", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="band-gen-", dir=str(SCRATCH)))
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

    def test_the_real_row_passes_and_so_does_one_generator(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))
        self.assertEqual(1, len([r for r in self.render_with({"skill": "Deadly Reach"}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min <= value_max"),
            "a negative number": ({"value_min": "-50", "value_max": "-40"}, "needs 0 < value_min <= value_max"),
            "not a skill": ({"skill": "Fists of Thunderx"}, "is not a skill"),
            "a skill that pays no Spirit": ({"skill": "Tempest Rush"}, "resource_generation_pct"),
            "a generator of another class": ({"skill": "Cleave"}, "resource_generation_pct"),
            "a generator with a non-generator": ({"skill": "Deadly Reach;Tempest Rush"}, "resource_generation_pct"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": "Deadly Reach"}, "resource_generation_pct"),
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
        work = Path(tempfile.mkdtemp(prefix="itemband-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        factor = lambda skill, want: (T("factor", skill, STAT), g(want))  # noqa: E731
        worn = lambda roll: clear + [(T("wears", OWNER), None), (T("value", OWNER, CELL, STAT, roll), None)]  # noqa: E731
        # not worn: nothing
        out += clear + [factor(s, 1) for s in SKILLS]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None)] + [factor(s, 1) for s in SKILLS]
        # worn and rolled: 1 + N/100 for each of the four, at both ends and between
        for roll in (low, 45, high):
            out += worn(roll) + [factor(s, 1 + roll / 100) for s in SKILLS]
        # only the four generators (and other stats are untouched)
        out += worn(high)
        for other in ("Tempest Rush", "Cleave", "Whirlwind", "Fists of Thunderx", "Fists", "Deadly Reach Rune", ""):
            out += [factor(other, 1)]
        out += [(T("factor", "Deadly Reach", "damage_increase_pct"), "1")]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, CELL, STAT, 45), None)] + [factor(s, 1) for s in SKILLS]
        # a second owner's rows multiply with the first's
        out += worn(high) + [(T("wears", "Other Ring"), None), (T("value", "Other Ring", CELL, STAT, 20), None), factor("Deadly Reach", 1.5 * 1.2)]
        # the range rolls once per item, shared by the four (a Primal stores the top)
        key = "power:%s:%s=" % (SKILLS[0], STAT)
        out += [(T("roll", OWNER, 1), key + "%g;" % high), (T("roll", OWNER, 0), key + "%g;" % ((low + high) / 2))]
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
        other = [("Other Ring", 0, "skill", CELL, STAT, 20.0, 20.0, *BLANK)]
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + other, "real")
        self.assertGreater(len(want), 30)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        other = [("Other Ring", 0, "skill", CELL, STAT, 20.0, 20.0, *BLANK)]
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "a_generator_lost": [r[:3] + ("Fists of Thunder;Deadly Reach;Crippling Wave",) + r[4:] for r in rows],
            "another_skill_added": [r[:3] + (CELL + ";Tempest Rush",) + r[4:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        want, _ = self.drive(real, rows + other, "want")
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows + other, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double SkillFactor("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "added_not_multiplied": ("factor *= 1.0 + pct / 100.0;", "factor += pct / 100.0;"),
            "percent_read_as_a_fraction": ("factor *= 1.0 + pct / 100.0;", "factor *= 1.0 + pct;"),
            "only_the_first_source": ("factor *= 1.0 + pct / 100.0;", "return 1.0 + pct / 100.0;"),
            "the_stat_ignored": ("skill, stat, situation)", 'skill, "damage_increase_pct", situation)'),
            "the_skill_ignored": ('"skill", skill, stat', '"skill", "Deadly Reach", stat'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows + other, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
