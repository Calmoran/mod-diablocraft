"""Legendary rest, bead diablocraft-lxvl2: The Fist of Az'Turrasq (Monk fist weapon). Builds N-SKPART: a skill stat that names one PART of a skill.

  "Exploding Palm's on-death explosion damage is increased by [400 - 500]%."
  * the range (400-500) is read from d3planner (item_onehand.js, P61_Unique_Fist_009_x1, leg_thefistofazturrasq_p6; the Legacy ids carry 75-100 and 250-300 and are not
    the pool item) and the tooltip text from the generated crafting table; the table (data/legendary_powers.csv) holds ONE `skill` row for the pool item, Exploding
    Palm, stat `explosion_damage_pct` (NOT damage_increase_pct, which would also raise the bleed), rolled once per item (a Primal takes 500);
  * the generated SQL and the committed migration are what the generator renders; the generator accepts the part stat for Exploding Palm only, simply on, one skill;
    the migration is the newest full table;
  * the production rule (src/combat/dc_item_power_math.h: SkillFactor, with Owned / Holds / RollPowers) is compiled and driven with the generated rows: 1 + N/100 for
    Exploding Palm's explosion_damage_pct while the fist is worn and rolled, 1 for every other skill and every other stat (the bleed's and the hits' damage_increase_pct
    stays 1), 1 for unworn or unrolled, a second source multiplies; mutants of the rule and of the rows fail the same driver;
  * source-text guards that ExplodingPalm::Explode reads the part once and multiplies the explosion's weapon-damage percent by it, for Essence Burn's burn and for the
    hit of every other rune, while the bleed (Palm) does not read it; mutants of that text fail the same guards. The in-game steps are in docs/test-diablocraft-lxvl2.md.
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
HARNESS = MODULE / "tests/item_power_events/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P61_Unique_Fist_009_x1"
SKILL = "Exploding Palm"
PART, HIT = "explosion_damage_pct", "damage_increase_pct"
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
    """(low, high) as the planner words them for the pool item."""
    text = (REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n", start)]
    m = re.search(r'format: "Exploding Palm\'s on-death explosion damage is increased by %d%%\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_name_the_skill_and_the_numbers(self):
        self.assertEqual((400.0, 500.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv")])
        explosion = [r for r in read_csv("data/d3/monk_skill_values.csv") if r["skill"] == SKILL and r["qualifier"] == "explosion"]
        self.assertTrue(explosion, "the skill has an explosion part to raise")

    def test_one_row_names_the_explosion_part(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, PART, low, high, *BLANK)], mine())

    def test_the_owner_is_the_monk_fist_that_drops(self):
        item = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("The Fist of Az'Turrasq", "onehand", "legendary", "monk", "yes", "no"),
                         (item["d3_name"], item["slot"], item["rarity"], item["designated_class"], item["pool_version"], item["craft_only"]))
        for legacy in ("Unique_Fist_009_x1", "P4_Unique_Fist_009_x1"):
            self.assertEqual("no", next(r["pool_version"] for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == legacy), legacy)
            self.assertEqual([], [r for r in all_rows() if r[0] == legacy])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','((?:[^']|'')*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Exploding Palm''s on-death explosion damage is increased by 400–500%.", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": PART, "value_min": "400", "value_max": "500", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="fist-gen-", dir=str(SCRATCH)))
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

    def test_it_refuses_what_the_code_does_not_read(self):
        refused = {
            "a skill that has no explosion part": {"skill": "Lashing Tail Kick"},
            "no skill at all": {"skill": "Exploding Palmx"},
            "two skills": {"skill": "Exploding Palm;Lashing Tail Kick"},
            "a set bonus": {"pieces": "2"},
            "a condition": {"cond": "triggered", "cond_arg": "3"},
            "an event": {"fire_on": "hit_generator"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemfist-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        factor = lambda skill, stat, want: (T("factor", skill, stat), g(want))  # noqa: E731

        def worn(roll):
            return clear + [(T("wears", OWNER, 0), None), (T("value", OWNER, SKILL, PART, roll), None)]

        # not worn: nothing; worn with no stored roll: the range gives nothing
        out += clear + [factor(SKILL, PART, 1)]
        out += clear + [(T("wears", OWNER, 0), None), factor(SKILL, PART, 1)]
        # worn and rolled: the factor at both ends of the range and between
        for roll in (low, 450, high):
            out += worn(roll) + [factor(SKILL, PART, 1 + roll / 100)]
        # only Exploding Palm, and only its part: the bleed and the hits (damage_increase_pct) stay 1
        out += worn(high) + [factor(SKILL, HIT, 1), factor(SKILL, "attack_speed_pct", 1), factor(SKILL, "dot_duration_seconds", 1)]
        for other in ("Fists of Thunder", "Lashing Tail Kick", "Sweeping Wind", "Exploding Palmx", "Exploding", ""):
            out += [factor(other, PART, 1), factor(other, HIT, 1)]
        # a value stored but the fist in the bag
        out += clear + [(T("value", OWNER, SKILL, PART, 450), None), factor(SKILL, PART, 1)]
        # a second source multiplies with it
        out += worn(high) + [(T("wears", "Other Fist", 0), None), (T("value", "Other Fist", SKILL, PART, 100), None), factor(SKILL, PART, (1 + high / 100) * 2)]
        # the range rolls once per item (a Primal stores the top)
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, PART, high)),
                (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, PART, (low + high) / 2))]
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

    OTHER = [("Other Fist", 0, "skill", SKILL, PART, 100.0, 100.0, *BLANK)]

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + self.OTHER, "real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows + self.OTHER, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Fists of Thunder",) + r[4:] for r in rows],
            "the_row_lost": [],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_part_widened_to_every_hit": [r[:4] + (HIT,) + r[5:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows + self.OTHER, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double SkillFactor("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "added_not_multiplied": ("factor *= 1.0 + pct / 100.0;", "factor += pct / 100.0;"),
            "percent_read_as_a_fraction": ("factor *= 1.0 + pct / 100.0;", "factor *= 1.0 + pct;"),
            "only_the_first_source": ("factor *= 1.0 + pct / 100.0;", "return 1.0 + pct / 100.0;"),
            "the_stat_ignored": ("skill, stat, situation)", 'skill, "explosion_damage_pct", situation)'),
            "the_skill_ignored": ('"skill", skill, stat', '"skill", "Exploding Palm", stat'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows + self.OTHER, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
