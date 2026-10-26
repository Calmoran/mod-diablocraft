"""Legendary rest, bead diablocraft-y0bnd: Rivera Dancers (boots, Monk). No new C++: two rows of the existing table on stats the code already reads.

  "Lashing Tail Kick attacks 50% faster and deals [250 - 300]% increased damage."
  * the range (250-300) and the 50 are read from d3planner (item_feet.js, leg_riveradancers) and the tooltip text from the generated crafting table; the table
    (data/legendary_powers.csv) holds TWO `skill` rows for the pool item P4_Unique_Boots_001, both on Lashing Tail Kick: `attack_speed_pct` 50 and
    `damage_increase_pct` 250-300 (the damage rolled once per item, a Primal takes 300);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rule (src/combat/dc_item_power_math.h: SkillFactor, with Owned / Holds / RollPowers) is compiled and driven with the generated rows:
    1 + 50/100 and 1 + N/100 for Lashing Tail Kick only, while the boots are worn and rolled, 1 for every other skill, 1 for unworn or unrolled boots,
    a second source multiplies; mutants of the rule and of the rows fail the same driver;
  * source-text guards that the attack-speed stat reaches the skill's swing recovery (HandAttacksPerSecond) and the damage stat reaches the hit (ComputeHit's
    legendary term) for any skill with a shell row (the Monk's included); the in-game steps are in docs/test-diablocraft-y0bnd.md.
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
OWNER = "P4_Unique_Boots_001"
SKILL = "Lashing Tail Kick"
SPEED, DAMAGE = "attack_speed_pct", "damage_increase_pct"
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
    """(speed, low, high) as the planner words them."""
    text = (REPO / "reference/d3planner/item_feet.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Lashing Tail Kick attacks (\d+)%% faster and deals %d%% increased damage\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2]), float(m[3])


class Table(unittest.TestCase):
    def test_the_sources_name_the_skill_and_the_numbers(self):
        self.assertEqual((50.0, 250.0, 300.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv")])
        self.assertEqual("", next(r["cooldown_seconds"] for r in read_csv("data/d3/monk_skills.csv") if r["skill_name"] == SKILL))   # no stated cooldown: the swing recovery is 1/APS

    def test_two_rows_name_lashing_tail_kick(self):
        speed, low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, SPEED, speed, speed, *BLANK), (OWNER, 0, "skill", SKILL, DAMAGE, low, high, *BLANK)],
                         sorted(mine(), key=lambda r: r[4]))

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Lashing Tail Kick attacks 50% faster and deals 250–300% increased damage.", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": DAMAGE, "value_min": "250", "value_max": "300", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="rivera-gen-", dir=str(SCRATCH)))
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

    def test_the_real_rows_pass_and_so_does_each_alone(self):
        self.assertEqual(2, len([r for r in self.render_with({}, {"stat": SPEED, "value_min": "50", "value_max": "50"}) if r[0] == OWNER]))
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a skill that is not one": ({"skill": "Lashing Tail Kickx"}, "is not a skill"),
            "a repeat of the same skill and stat": (None, "named once"),
            "a set bonus with a range": ({"pieces": "2"}, "not a set|set bonus"),
        }
        with self.assertRaises(ValueError):
            self.render_with({}, {})                                   # the same skill and stat twice
        for name, (edit, why) in refused.items():
            if edit is None:
                continue
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemrivera-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        speed, low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        factor = lambda skill, stat, want: (T("factor", skill, stat), g(want))  # noqa: E731

        def worn(roll):
            return clear + [(T("wears", OWNER, 0), None), (T("value", OWNER, SKILL, DAMAGE, roll), None)]

        # not worn: nothing; worn with no stored roll: the fixed 50 counts, the unrolled range gives nothing
        out += clear + [factor(SKILL, DAMAGE, 1), factor(SKILL, SPEED, 1)]
        out += clear + [(T("wears", OWNER, 0), None), factor(SKILL, DAMAGE, 1), factor(SKILL, SPEED, 1 + speed / 100)]
        # worn and rolled: both factors, at both ends of the range and between
        for roll in (low, 275, high):
            out += worn(roll) + [factor(SKILL, DAMAGE, 1 + roll / 100), factor(SKILL, SPEED, 1 + speed / 100)]
        # only Lashing Tail Kick, and each stat only its own
        out += worn(high)
        for other in ("Fists of Thunder", "Tempest Rush", "Exploding Palm", "Cleave", "Lashing Tail Kickx", "Lashing", ""):
            out += [factor(other, DAMAGE, 1), factor(other, SPEED, 1)]
        out += [factor(SKILL, "resource_generation_pct", 1), factor(SKILL, "duration_add_seconds", 1)]
        # a value stored but the boots in the bag
        out += clear + [(T("value", OWNER, SKILL, DAMAGE, 275), None), factor(SKILL, DAMAGE, 1), factor(SKILL, SPEED, 1)]
        # a second source multiplies with it
        out += worn(high) + [(T("wears", "Other Boots", 0), None), (T("value", "Other Boots", SKILL, DAMAGE, 100), None), factor(SKILL, DAMAGE, (1 + high / 100) * 2)]
        # only the damage is a range, so only it is rolled and stored (a Primal stores the top); the 50 is a fixed row
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, DAMAGE, high)),
                (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, DAMAGE, (low + high) / 2))]
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

    OTHER = [("Other Boots", 0, "skill", SKILL, DAMAGE, 100.0, 100.0, *BLANK)]

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + self.OTHER, "real")
        self.assertGreater(len(want), 30)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(real, rows + self.OTHER, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Fists of Thunder",) + r[4:] for r in rows],
            "the_speed_row_lost": [r for r in rows if r[4] != SPEED],
            "the_damage_row_lost": [r for r in rows if r[4] != DAMAGE],
            "the_speed_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == SPEED else r for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == DAMAGE else r for r in rows],
            "the_stats_swapped": [r[:4] + ((DAMAGE, SPEED)[r[4] == DAMAGE],) + r[5:] for r in rows],
            "no_rows": [],
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
            "the_stat_ignored": ("skill, stat, situation)", 'skill, "damage_increase_pct", situation)'),
            "the_skill_ignored": ('"skill", skill, stat', '"skill", "Lashing Tail Kick", stat'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows + self.OTHER, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
