"""Legendary rest, bead diablocraft-tvv2b: Kyoshiro's Soul (Monk belt), the bead that builds N-SWSTACK (Sweeping Wind's stacks from an item).

  "Sweeping Wind gains 2 stacks every second it does not deal damage to any enemies."
  * the number (2, in the text: args 0) is read from d3planner (item_waist.js, leg_kyoshirossoul) and the catalogue, apart from the table; the
    table (data/legendary_powers.csv) holds ONE `skill` row for the pool item P4_Unique_Belt_05: Sweeping Wind, `idle_stacks_per_second`, 2, fixed;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts
    the stat for Sweeping Wind, refuses it for another skill, a range, a part stack, zero, a condition and an event;
  * the production rules are compiled and driven with the generated row: dc_item_power_math.h's SkillSetTo (2 while the belt is worn, 0 without)
    and the real Wind::IdleGain of dc_monk_sweeping_wind.h over runs of the vortex's ticks (the tunable's 0.25 s, the sheet's 3 stacks at most):
    every whole second of ticks that damage no enemy adds 2 stacks, a tick that damages one starts the second over, never past the maximum;
  * mutants of the rule and of the row fail the same driver;
  * source-text guards that the vortex's tick asks the item powers before its lock and adds IdleGain's stacks up to max_stacks_count. The C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-tvv2b.md.
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
WIND = SRC / "classes/monk/dc_monk_sweeping_wind.h"
HARNESS = MODULE / "tests/item_power_kyoshiros_soul/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P4_Unique_Belt_05"
SKILL = "Sweeping Wind"
STAT = "idle_stacks_per_second"
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


def stacks_per_second():
    """The stacks a quiet second gains, as the planner words it, checked against the catalogue."""
    text = (REPO / "reference/d3planner/item_waist.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Sweeping Wind gains (\d+) stacks every second it does not deal damage to any enemies\.", args: 0', item)
    assert m, item
    with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
        catalogue = next(r for r in csv.DictReader(stream) if r["d3_id"] == OWNER)
    assert catalogue["power_text"] == "Sweeping Wind gains %s stacks every second it does not deal damage to any enemies." % m[1], catalogue
    return int(m[1])


def tick_ms():
    row = next(r for r in read_csv("data/tunables/monk.csv") if r["name"] == "sweeping_wind_tick_seconds")
    return round(float(row["d3_value"] or row["value"]) * 1000)


def max_stacks():
    rows = [r for r in read_csv("data/d3/monk_skill_values.csv")
            if (r["skill"], r["rune"], r["token"]) == (SKILL, "", "max_stacks_count")]
    assert len(rows) == 1, rows
    return int(float(rows[0]["value"]))


def expected(tick, per_second, most, stacks, pattern):
    """The item text read on its own: time without damage counts up, each whole second of it is per_second stacks, damage starts it over."""
    out, quiet, paid = [], 0, 0
    for t in pattern:
        if t == "d" or not per_second:
            quiet, paid = 0, 0
        else:
            quiet += tick
            gained = quiet // 1000 - paid
            paid += gained
            stacks = min(stacks + gained * per_second, most)
        out.append(stacks)
    return ",".join(str(s) for s in out) + ","


class Table(unittest.TestCase):
    def test_the_sources_name_sweeping_wind_and_the_number(self):
        self.assertEqual(2, stacks_per_second())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv")])

    def test_one_row_names_sweeping_wind(self):
        n = float(stacks_per_second())
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, n, n, *BLANK)], mine())


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "2", "value_max": "2", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="kyoshiro-gen-", dir=str(SCRATCH)))
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
            "a skill nothing reads it for": ({"skill": "Fists of Thunder"}, STAT),
            "several skills": ({"skill": "Sweeping Wind;Fists of Thunder"}, STAT),
            "a range": ({"value_min": "2", "value_max": "3"}, STAT),
            "a part stack": ({"value_min": "1.5", "value_max": "1.5"}, STAT),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL}, STAT),
            "another stat": ({"stat": "idle_stack_per_second"}, "a skill stat is one of"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math_text, wind_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math_text, "classes/monk/dc_monk_sweeping_wind.h": wind_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemkyoshiro-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        tick, most, n = tick_ms(), max_stacks(), stacks_per_second()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: the tick asks and gets 0; worn: the table's number (a fixed row, no roll stored)
        out += clear + [(T("setto", SKILL, STAT, 0), "0")]
        out += clear + [(T("wears", OWNER), None), (T("setto", SKILL, STAT, 0), "%g" % n)]
        for other in ("Fists of Thunder", "Sweeping Winds", "sweeping wind", ""):
            out += [(T("setto", other, STAT, 0), "0")]
        for other in ("damage_increase_pct", "max_stacks_count", "idle_stack_per_second", ""):
            out += [(T("setto", SKILL, other, 0), "0")]
        # the ticks: a vortex starts with one stack (Wind::Cast)
        quiet_second = "q" * (1000 // tick)
        patterns = [
            quiet_second,                                   # one quiet second: +n
            "q" * (1000 // tick - 1),                       # not yet a second: nothing
            quiet_second * 3,                               # stops at the maximum
            "qq" + "d" + quiet_second,                      # damage starts the second over
            "q" * (1000 // tick - 1) + "d" + "q",           # a damaging tick just before the second: nothing
            "d" * 8,                                        # always damaging: nothing
        ]
        for pattern in patterns:
            out += [(T("ticks", tick, n, most, 1, pattern), expected(tick, n, most, 1, pattern))]
        # no item: nothing, however quiet
        out += [(T("ticks", tick, 0, most, 1, quiet_second * 2), expected(tick, 0, most, 1, quiet_second * 2))]
        # a tick that does not divide the second carries what is left over; a larger maximum shows each second's gain
        for odd in (300, 400, 700):
            out += [(T("ticks", odd, n, 99, 1, "q" * 12), expected(odd, n, 99, 1, "q" * 12))]
        out += [(T("ticks", tick, 3, 99, 0, quiet_second * 2), expected(tick, 3, 99, 0, quiet_second * 2))]
        return out

    def drive(self, math_text, wind_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(math_text, wind_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        self.assertEqual(250, tick_ms())
        self.assertEqual(3, max_stacks())
        want, got = self.drive(MATH.read_text(encoding="utf-8"), WIND.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 15)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        math, wind = MATH.read_text(encoding="utf-8"), WIND.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(math, wind, rows, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Fists of Thunder",) + r[4:] for r in rows],
            "one_stack": [r[:5] + (1.0, 1.0) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(math, wind, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = wind[wind.index("inline unsigned IdleGain("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "damage_does_not_reset": ("if (damaged || !perSecond)", "if (!perSecond)"),
            "gains_on_damage": ("if (damaged || !perSecond)", "if (!damaged || !perSecond)"),
            "no_carry": ("quietMs %= 1000;", "quietMs = 0;"),
            "never_resets_the_second": ("quietMs %= 1000;", ""),
            "per_tick_not_per_second": ("quietMs / 1000", "quietMs / 250"),
            "the_number_ignored": ("return seconds * perSecond;", "return seconds * 2;"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(math, wind.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
