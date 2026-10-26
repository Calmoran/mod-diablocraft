"""Legendary rest, bead diablocraft-1zocv: Serpent's Sparker (Wizard wand), the bead that builds N-HYDRA (how many Hydras may be up at once).

  "You may have one extra Hydra active at a time and they deal [250-300]% increased damage."
  * the numbers (the 250-300 range and the one extra Hydra, which is in the words) are read from d3planner (data.json, leg_serpentssparker_p68)
    and the catalogue, apart from the table; the table (data/legendary_powers.csv) holds TWO `skill` rows for the pool item P68_Unique_Wand_102:
    Hydra `extra_active_count` 1 (fixed) and Hydra `damage_increase_pct` 250-300 (rolled once per item);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    accepts `extra_active_count` for Hydra and refuses it for another skill, several skills, a range, a part number, zero, a condition and an event;
  * the production rules are compiled and driven with the generated rows: dc_item_power_math.h's ActiveCount (2 Hydras with the wand worn, 1
    without), Dismissed over a run of casts (the oldest goes once the cap is up: 1, 2, 2, 2 with the wand; 1, 1, 1 without) and SkillFactor on
    Hydra's damage (1 + roll/100);
  * mutants of the rules and of the rows fail the same driver;
  * source-text guards that the Hydra's summon (dc_wizard_hydra.cpp, the TempSummon hook before the core's totem slot) asks ActiveCount with the core's
    one Hydra as its base, dismisses Dismissed's oldest, keeps the new one and takes the survivor off the slot. The C++ is compile-checked by
    syntax_check.sh and the in-game steps are in docs/test-diablocraft-1zocv.md.
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
import harness_env  # noqa: E402
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_serpents_sparker/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P68_Unique_Wand_102"
SKILL = "Hydra"
COUNT = "extra_active_count"
DAMAGE = "damage_increase_pct"
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
    """The extra Hydras (the words' 'one') and the damage range, as d3planner words them, checked against the catalogue."""
    items = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"]
    item = next(i for i in items if i["id"] == OWNER)
    custom = item["required"]["custom"]
    assert custom["id"] == "leg_serpentssparker_p68", custom
    assert custom["format"] == "You may have one extra Hydra active at a time and they deal %d%% increased damage.", custom
    with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
        catalogue = next(r for r in csv.DictReader(stream) if r["d3_id"] == OWNER)
    assert catalogue["power_text"] == "You may have one extra Hydra active at a time and they deal [%d-%d]%% increased damage." % (
        custom["min"], custom["max"]), catalogue
    words = {"one": 1, "two": 2}
    extra = words[re.match(r"You may have (\w+) extra Hydra", custom["format"])[1]]
    return extra, float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_sources_name_the_hydra_and_the_numbers(self):
        self.assertEqual((1, 250.0, 300.0), planner())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")])

    def test_two_rows_name_the_hydra(self):
        extra, low, high = planner()
        self.assertEqual(sorted([(OWNER, 0, "skill", SKILL, COUNT, float(extra), float(extra), *BLANK),
                                 (OWNER, 0, "skill", SKILL, DAMAGE, low, high, *BLANK)]), sorted(mine()))


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": COUNT, "value_min": "1", "value_max": "1", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="sparker-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if not (r["owner"] == OWNER and r["stat"] == COUNT)]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.assertEqual(2, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min|" + COUNT),
            "a skill nothing reads it for": ({"skill": "Familiar"}, COUNT),
            "several skills": ({"skill": "Hydra;Familiar"}, COUNT),
            "a range": ({"value_min": "1", "value_max": "2"}, COUNT),
            "a part number": ({"value_min": "1.5", "value_max": "1.5"}, COUNT),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL}, COUNT),
            "an event": ({"fire_on": "cast", "fire_skills": SKILL}, COUNT + "|fire_on"),
            "another stat": ({"stat": "extra_active_counts"}, "a skill stat is one of"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemsparker-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        extra, low, high = planner()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: the core's one Hydra and no damage term
        out += clear + [(T("count", SKILL, 1), "1"), (T("factor", SKILL, DAMAGE), "1")]
        for roll in (low, (low + high) / 2, high):
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, DAMAGE, roll), None),
                            (T("count", SKILL, 1), "%g" % (1 + extra)), (T("factor", SKILL, DAMAGE), "%.10g" % (1 + roll / 100))]
            for other in ("Familiar", "Hydras", "hydra", ""):
                out += [(T("count", other, 1), "1"), (T("factor", other, DAMAGE), "1")]
        # worn but no roll stored (an item rolled before the row): the count is fixed, the damage has no number, no power
        out += clear + [(T("wears", OWNER), None), (T("count", SKILL, 1), "%g" % (1 + extra)), (T("factor", SKILL, DAMAGE), "1")]
        # the casts: the new Hydra counts, the oldest go once the cap is up
        for cap in (1, 1 + extra, 3, 0):
            for n in (1, 2, 5):
                out += [(T("casts", n, cap), "".join("%d," % min(i + 1, max(cap, 1)) for i in range(n)))]
        return out

    def drive(self, math_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(math_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 30)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        math = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(math, rows, "want")
        count = [r for r in rows if r[4] == COUNT]
        damage = [r for r in rows if r[4] == DAMAGE]
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Familiar",) + r[4:] for r in rows],
            "two_extra": [r[:5] + (2.0, 2.0) + r[7:] for r in count] + damage,
            "no_count_row": damage,
            "no_damage_row": count,
            "the_wrong_stat": [r[:4] + ("duration_add_seconds",) + r[5:] for r in count] + damage,
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(math, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        start = math.index("inline double ActiveCount(")
        body = math[start:math.index("\n    }\n", math.index("inline std::size_t Dismissed(", start)) + 7]
        rules = {
            "the_count_ignored": ("            base += add;\n        return base;\n    }\n\n    // How many", "            (void)add;\n        return base;\n    }\n\n    // How many"),
            "set_not_added": ("            base += add;\n        return base;\n    }\n\n    // How many", "            base = add;\n        return base;\n    }\n\n    // How many"),
            "another_stat": ('"extra_active_count"', '"duration_add_seconds"'),
            "the_new_one_not_counted": ("cap > 1 ? cap - 1 : 0", "cap"),
            "a_cap_of_one_keeps_one": ("cap > 1 ? cap - 1 : 0", "cap > 1 ? cap - 1 : 1"),
            "none_dismissed": ("return up > keep ? up - keep : 0;", "return 0;"),
            "all_dismissed": ("return up > keep ? up - keep : 0;", "return up;"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, body.count(old), name + " does not apply once")
                _, got = self.drive(math.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
