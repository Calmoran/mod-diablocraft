"""Legendary rest, bead diablocraft-i2d92: Envious Blade (class-free dagger). Builds N-CRIT (a crit-chance power) and N-TLIFE (the target's Life as a condition).

  "Gain 100% Critical Hit Chance against enemies at full health."
  * the number is in the text (d3planner data.json, Unique_Dagger_103_x1, custom leg_enviousblade, args 0) and the catalogue row (K2); the table
    (data/legendary_powers.csv) holds ONE `player` row for the pool item: `crit_chance_pct` 100 under the condition `target_life_at_least` 100;
  * the generated SQL and the committed migration are what the generator renders; the generator accepts the condition only on `crit_chance_pct`
    (the one reader that looks at a target), with a percent in (0, 100], no skill list and no event;
  * the production rule (src/combat/dc_item_power_math.h: PlayerSum with Holds / Owned) is compiled and driven with the generated row: 100 at full
    Life, 0 below it, 0 with no target, 0 unworn, a second source adds; mutants of the rule and of the row fail the same driver;
  * source-text guards that ComputeHit sums ItemPowers::CritBonus into the crit chance once, and that CritBonus hands the target's Life percent to the
    situation; mutants of that text fail the same guards. The in-game steps are in docs/test-diablocraft-i2d92.md.
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_events/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Dagger_103_x1"
STAT, COND = "crit_chance_pct", "target_life_at_least"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%g" % x  # noqa: E731
# the cells after value_max of the one row: cond, cond_arg, cond_skills, stack_seconds, stack_max, fire_on, fire_skills, chance, icd
AFTER = (COND, 100.0, "", 0.0, 0, "", "", 100.0, 0.0)


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_what_the_row_says(self):
        data = (REPO / "reference/d3planner/data.json").read_text(encoding="utf-8")
        m = re.search(r'"id":"%s".{0,400}?"format":"([^"]*)"' % OWNER, data)
        self.assertTrue(m)
        self.assertEqual("Gain 100%% Critical Hit Chance against enemies at full health.", m[1])

    def test_one_row_gives_certain_crit_at_full_life(self):
        self.assertEqual([(OWNER, 0, "player", "", STAT, 100.0, 100.0, *AFTER)], mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','((?:[^']|'')*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("Gain 100% Critical Hit Chance against enemies at full health.", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "100", "value_max": "100", "cond": COND,
            "cond_arg": "100", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="envious-gen-", dir=str(SCRATCH)))
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

    def test_a_plain_crit_power_passes_and_a_threshold_below_full_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({"cond": "", "cond_arg": ""}) if r[0] == OWNER]))
        self.assertEqual(1, len([r for r in self.render_with({"cond_arg": "50"}) if r[0] == OWNER]))

    def test_it_refuses_what_the_code_does_not_read(self):
        refused = {
            "the condition on a stat nothing hands the target to": {"stat": "damage_dealt_pct"},
            "the condition on a skill row": {"kind": "skill", "skill": "Frenzy", "stat": "damage_increase_pct"},
            "no percent": {"cond_arg": ""},
            "zero percent": {"cond_arg": "0"},
            "a percent above full": {"cond_arg": "101"},
            "a skill list": {"cond_skills": "Frenzy"},
            "an event": {"fire_on": "hit_generator"},
            "a crit chance that is not positive": {"value_min": "-5", "value_max": "-5"},
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
        work = Path(tempfile.mkdtemp(prefix="itemenvious-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        crit = lambda want: (T("sum", STAT, 0), g(want))  # noqa: E731

        def worn(life):
            return clear + [(T("wears", OWNER, 0), None), (T("target", life), None)]

        # not worn: nothing, whatever the target
        out += clear + [(T("target", 100), None), crit(0)]
        # worn, no target at all: nothing
        out += clear + [(T("wears", OWNER, 0), None), crit(0)]
        # worn: certain at full Life, nothing a hair below it, nothing lower
        out += worn(100) + [crit(100)]
        for life in (99.99, 99, 75, 50, 1, 0):
            out += worn(life) + [crit(0)]
        # a second source adds with it, and a source whose condition fails adds nothing
        out += worn(100) + [(T("wears", "Other Dagger", 0), None), crit(105)]
        out += worn(60) + [(T("wears", "Other Dagger", 0), None), crit(5)]
        # a row with a lower percent (another item's 50) holds from its own level up and not below it, beside this one
        out += worn(100) + [(T("wears", "Half Dagger", 0), None), crit(150)]
        out += worn(60) + [(T("wears", "Half Dagger", 0), None), crit(50)]
        out += worn(50) + [(T("wears", "Half Dagger", 0), None), crit(50)]
        out += worn(49) + [(T("wears", "Half Dagger", 0), None), crit(0)]
        return out

    OTHERS = [("Other Dagger", 0, "player", "", STAT, 5.0, 5.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
              ("Half Dagger", 0, "player", "", STAT, 50.0, 50.0, COND, 50.0, "", 0.0, 0, "", "", 100.0, 0.0)]

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
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + self.OTHERS, "real")
        self.assertGreater(len(want), 10)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows + self.OTHERS, "want")
        row_mutants = {
            "the_row_lost": [],
            "the_percent_lowered": [r[:8] + (99.0,) + r[9:] for r in rows],
            "the_condition_dropped": [r[:7] + ("", 0.0) + r[9:] for r in rows],
            "the_number_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows + self.OTHERS, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "full_life_is_not_enough": real.replace("situation.targetLifePct >= row.arg", "situation.targetLifePct > row.arg"),
            "the_percent_ignored": real.replace("situation.targetLifePct >= row.arg", "situation.targetLifePct >= 100.0"),
            "no_target_counts_as_full": real.replace("situation.targetLifePct >= 0 &&", "situation.targetLifePct < 0 ||"),
            "the_condition_always_holds": real.replace('if (row.cond == "target_life_at_least")', 'if (row.cond == "target_life_at_least_x")'),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows + self.OTHERS, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
