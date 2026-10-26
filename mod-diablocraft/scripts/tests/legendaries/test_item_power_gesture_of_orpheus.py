"""Legendary rest, bead diablocraft-1i52b: Gesture of Orpheus (Wizard wand), which builds N-CD (a skill's cooldown cut by a percent).

  "Reduces the cooldown of Slow Time by [30-40]%."
  * the text and range are read from d3planner (data.json items, leg_gestureoforpheus_p2, min 30 max 40) and the catalogue row; the table
    (data/legendary_powers.csv) holds ONE `skill` row for the pool item P2_Unique_Wand_002: Slow Time, `cooldown_reduction_pct`, 30-40, a range the roller
    rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses a
    percent of 0 or over 100, a condition, an event and a set bonus's row;
  * the production rule (src/combat/dc_item_power_math.h: CooldownFactor) is compiled and driven with the generated row: the cooldown is 1 - N/100 of
    itself with the item's stored roll, only for Slow Time, only while the item is worn; two sources multiply (D3) and the factor never goes below 0;
  * mutants of the rule and of the row fail the same driver, and mutants of the two readers fail the source guards on them:
    Combat::SkillCooldownMilliseconds (dc_combat.cpp: the readout and a restart) applies the factor after the sheet's reduction, and
    ReducedCooldownMilliseconds does not (Crown of the Primus's Time Shell send goes through it and Cast's cut follows), and ItemPowers::Cast (dc_item_powers.cpp) cuts the cooldown the core installed by the same factor;
    the reader takes no Seen (the stat takes no condition), only the item powers' lock. The C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-1i52b.md.
"""
import csv
import json
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
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_gesture_of_orpheus/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P2_Unique_Wand_002"
SKILL = "Slow Time"
STAT = "cooldown_reduction_pct"
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


def planner():
    """(text, min, max) of the pool item's power in d3planner's data.json."""
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_sources_say_slow_time_cooldown_30_to_40(self):
        text, low, high = planner()
        self.assertEqual("Reduces the cooldown of Slow Time by %d%%.", text)
        self.assertEqual((30.0, 40.0), (low, high))
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Reduces the cooldown of Slow Time by [30-40]%.", catalogue[0]["power_text"])
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")])

    def test_one_row_names_slow_time_with_the_range(self):
        _, low, high = planner()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, *BLANK)], mine())

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("leg_gestureoforpheus_p2", rows[0]["source"])
        self.assertIn("legacy twin", rows[0]["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("Reduces the cooldown of Slow Time by 30", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "30", "value_max": "40", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="orpheus-gen-", dir=str(SCRATCH)))
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

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        why = "cooldown_reduction_pct is an item's percent above 0 and at most 100"
        refused = {
            "zero": ({"value_min": "0", "value_max": "40"}, "0 < value_min|" + why),
            "over all of it": ({"value_min": "30", "value_max": "101"}, why),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL}, why),
            "an event": ({"fire_on": "cast", "fire_skills": SKILL}, "an event fires|" + why),
            "a set bonus": ({"owner": "Vyr's Amazing Arcana", "pieces": "2", "value_min": "30", "value_max": "30"}, why),
        }
        for name, (edit, reason) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, reason):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    OTHER = ("Other Wand", 0, "skill", SKILL, STAT, 1.0, 200.0, *BLANK)   # a ranged row: the driver sets its stored roll

    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemorpheus-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        _, low, high = planner()
        out = [(T("row", *r), None) for r in rows + [self.OTHER]]
        clear = [(T("clear"), None)]
        # not worn: the cooldown as it is, even with the item's roll known (taken off, in the bag)
        out += clear + [(T("factor", SKILL), "1")]
        out += clear + [(T("rolled", OWNER, SKILL, STAT, low), None), (T("factor", SKILL), "1")]
        # worn, each end of the roll: 30% off is 0.7 of the cooldown, 40% off 0.6
        for roll in (low, high):
            out += clear + [(T("wears", OWNER, SKILL, STAT, roll), None), (T("factor", SKILL), "%.10g" % (1 - roll / 100))]
        # only Slow Time
        out += clear + [(T("wears", OWNER, SKILL, STAT, low), None)]
        for other in ("Teleport", "Slow Timex", "slow time", ""):
            out += [(T("factor", other), "1")]
        # a second source multiplies (D3): 0.7 x 0.8 = 0.56, not 1 - 0.5
        out += [(T("wears", "Other Wand", SKILL, STAT, 20), None), (T("factor", SKILL), "%.10g" % ((1 - low / 100) * 0.8))]
        # never below 0, however much is stacked
        out += clear + [(T("wears", "Other Wand", SKILL, STAT, 150), None), (T("factor", SKILL), "0")]
        # another owner's item alone does not carry this row
        out += clear + [(T("wears", "Some Ring", SKILL, STAT, 35), None), (T("factor", SKILL), "1")]
        # taken off
        out += clear + [(T("factor", SKILL), "1")]
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
        self.assertGreater(len(want), 8)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Teleport",) + r[4:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double CooldownFactor("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "lengthens": ("1.0 - pct / 100.0", "1.0 + pct / 100.0"),
            "adds_the_sources": ("factor *= std::max(0.0, 1.0 - pct / 100.0);", "factor -= pct / 100.0;"),
            "no_floor": ("std::max(0.0, 1.0 - pct / 100.0)", "(1.0 - pct / 100.0)"),
            "percent_as_a_fraction": ("1.0 - pct / 100.0", "1.0 - pct"),
            "reads_the_player_rows": ('"skill", skill, "cooldown_reduction_pct"', '"player", skill, "cooldown_reduction_pct"'),
            "skill_ignored": ('"skill", skill, "cooldown_reduction_pct"', '"skill", "Slow Time", "cooldown_reduction_pct"'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_bottom_not_the_roll": real.replace("number = found->value;", "number = row.min;"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
