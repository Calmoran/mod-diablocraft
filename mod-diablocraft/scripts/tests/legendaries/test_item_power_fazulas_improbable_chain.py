"""Legendary rest, bead diablocraft-0la7a: Fazula's Improbable Chain (Wizard belt), the bead that builds N-ARCHON (Archon's stacks from an item).

  "You automatically start with [40 - 50] Archon stacks when entering Archon form."
  * the numbers (the roll range 40-50) are read from d3planner (item_waist.js, leg_fazulasimprobablechain_p2) and the catalogue, apart from the
    table; the table (data/legendary_powers.csv) holds ONE `skill` row for the pool item P4_Unique_Belt_07: Archon, `start_stacks`, 40-50, which
    the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the
    stat for Archon, refuses it for another skill, a part stack, zero, a condition and an event;
  * the production rule (src/combat/dc_item_power_math.h: SkillSetTo, with Owned / Holds / RollPowers) is compiled and driven with the generated row:
    0 stacks without the item, the stored roll while it is worn, only for Archon's `start_stacks`; a Primal stores 50;
  * mutants of the rule and of the row fail the same driver;
  * source-text guards that the Wizard's EnterArchon starts the form's kill stacks at that number (asked before the Wizard's lock), that leaving the form
    still clears them and that the form's damage reads them; the C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-0la7a.md.
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
import harness_env  # noqa: E402
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_fazulas_improbable_chain/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P4_Unique_Belt_07"
SKILL = "Archon"
STAT = "start_stacks"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(low, high) stacks as the planner words them, checked against the catalogue."""
    text = (REPO / "reference/d3planner/item_waist.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "You automatically start with %d Archon stacks when entering Archon form\.", min: (\d+), max: (\d+)', item)
    assert m, item
    with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
        catalogue = next(r for r in csv.DictReader(stream) if r["d3_id"] == OWNER)
    assert catalogue["power_text"] == "You automatically start with [%s-%s] Archon stacks when entering Archon form." % (m[1], m[2]), catalogue
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_name_archon_and_the_range(self):
        self.assertEqual((40.0, 50.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")])

    def test_one_row_names_archon(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, *BLANK)], mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("start with 40–50 Archon stacks when entering Archon form", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "40", "value_max": "50", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="fazula-gen-", dir=str(SCRATCH)))
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
        SCRATCH.mkdir(parents=True, exist_ok=True)
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
            "a skill nothing reads it for": ({"skill": "Meteor"}, "start_stacks"),
            "several skills": ({"skill": "Archon;Meteor"}, "start_stacks"),
            "a part stack": ({"value_min": "40.5", "value_max": "50"}, "start_stacks"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": "Archon"}, "start_stacks"),
            "another stat": ({"stat": "start_stack"}, "a skill stat is one of"),
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
        work = Path(tempfile.mkdtemp(prefix="itemfazula-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        worn = lambda roll: clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, roll), None)]  # noqa: E731
        # not worn: the form starts with no stacks
        out += clear + [(T("setto", SKILL, STAT, 0), "0")]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("setto", SKILL, STAT, 0), "0")]
        # worn and rolled: the roll, at both ends and between
        for roll in (low, 45, high):
            out += worn(roll) + [(T("setto", SKILL, STAT, 0), "%g" % roll)]
        # only Archon, only `start_stacks`
        out += worn(high)
        for other in ("Meteor", "Slow Time", "Archonx", "archon", ""):
            out += [(T("setto", other, STAT, 0), "0")]
        for other in ("damage_increase_pct", "start_stack", "max_stacks_count", ""):
            out += [(T("setto", SKILL, other, 0), "0")]
        # a base above the roll is never lowered (the reader asks for 0; the rule is SkillSetTo's)
        out += worn(low) + [(T("setto", SKILL, STAT, 60), "60")]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, STAT, 45), None), (T("setto", SKILL, STAT, 0), "0")]
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
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 12)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Meteor",) + r[4:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double SkillSetTo("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "never_raises": ("if (value > base)", "if (value < base)"),
            "always_raises": ("if (value > base)", "if (true)"),
            "reads_the_player_rows": ('"skill", skill, stat', '"player", skill, stat'),
            "skill_ignored": ('"skill", skill, stat', '"skill", "Archon", stat'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
