"""Legendary rest, bead diablocraft-8iwwg: Vengeful Wind (Monk fist weapon, list row 236, K1).

  "Increases the maximum stack count of Sweeping Wind by 10 and increases the damage by [600-800]%."
  * the text and numbers are read from d3planner (item_onehand.js, leg_vengefulwind_p67, min 600 max 800; the 10 is in the text) and the catalogue
    row; the table (data/legendary_powers.csv) holds TWO `skill` rows for the pool item P67_fistWeapon_norm_unique_02, both on Sweeping Wind:
    `max_stacks_add` 10 (fixed) and `damage_increase_pct` 600-800 (rolled once per item; the standing S-DMG multiplier of ComputeHit);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses
    a bad `max_stacks_add` row;
  * the production rules are compiled and driven with the generated rows: SkillSetTo (dc_item_power_math.h) gives the raise only while the item is
    worn, and Sweeping Wind's own MaxStacks / StacksAfter / SpawnsTornado (dc_monk_sweeping_wind.h) then hold 13 stacks instead of 3 and spawn
    Cyclone's tornado at 13;
  * mutants of the rows, of the rules and of the vortex's reader (dc_monk_sweeping_wind.cpp: asked before the lock, every cap through MaxStacks)
    fail. The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-8iwwg.md.
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
WIND_H = SRC / "classes/monk/dc_monk_sweeping_wind.h"
HARNESS = MODULE / "tests/item_power_vengeful_wind/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P67_fistWeapon_norm_unique_02"
SKILL = "Sweeping Wind"
STAT = "max_stacks_add"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
TEXT = re.compile(r'custom: \{id: "leg_vengefulwind_p67", name: "Sweeping Wind Damage", format: "Increases the maximum stack count of Sweeping Wind '
                  r'by (\d+) and increases the damage by %d%%\.", min: (\d+), max: (\d+)\}')
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def words():
    """(the stacks added, the damage range's bottom and top) from d3planner's pool item."""
    found = TEXT.findall((REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8"))
    assert len(found) == 1, found
    return tuple(float(x) for x in found[0])


def sheet_max():
    """Sweeping Wind's max_stacks_count, the base skill's and every rune's that has one: one number."""
    found = {r["value"] for r in read_csv("data/d3/monk_skill_values.csv") if r["skill"] == SKILL and r["token"] == "max_stacks_count"}
    assert len(found) == 1, found
    return float(found.pop())


class Table(unittest.TestCase):
    def test_the_sources_say_ten_stacks_and_600_to_800(self):
        self.assertEqual((10.0, 600.0, 800.0), words())
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Increases the maximum stack count of Sweeping Wind by 10 and increases the damage by [600-800]%.", catalogue[0]["power_text"])
        self.assertEqual(3.0, sheet_max())

    def test_two_rows_on_sweeping_wind(self):
        stacks, low, high = words()
        self.assertEqual(sorted([(OWNER, 0, "skill", SKILL, STAT, stacks, stacks, *BLANK), (OWNER, 0, "skill", SKILL, "damage_increase_pct", low, high, *BLANK)]),
                         sorted(mine()))


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "10", "value_max": "10", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="vengeful-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if not (r["owner"] == OWNER and r["stat"] == STAT)]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a range": ({"value_min": "9", "value_max": "10"}, "max_stacks_add is one whole number"),
            "a part stack": ({"value_min": "1.5", "value_max": "1.5"}, "max_stacks_add is one whole number"),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min|max_stacks_add is one whole number"),
            "another skill": ({"skill": "Fists of Thunder"}, "max_stacks_add is one whole number"),
            "not a skill": ({"skill": "Sweeping Windx"}, "is not a skill"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL}, "max_stacks_add is one whole number"),
            "an event": ({"fire_on": "cast", "fire_skills": SKILL}, "an event fires|max_stacks_add is one whole number"),
            "a set bonus": ({"pieces": "2"}, "not a set|max_stacks_add is one whole number"),
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
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemvengeful-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        top = sheet_max()
        stacks = words()[0]
        most = int(top + stacks)
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: no raise, the vortex holds the sheet's 3 and Cyclone's tornado comes at 3
        out += clear + [(T("setto", SKILL, STAT, 0), "0"), (T("attacks", top, 20), "%d 1" % top), (T("attacks", top, 1), "2 0")]
        # worn: 10 more, 13 in all; the tornado only at 13
        out += clear + [(T("wears", OWNER), None), (T("setto", SKILL, STAT, 0), "%g" % stacks)]
        out += [(T("attacks", top, 20), "%d 1" % most), (T("attacks", top, most - 1), "%d 1" % most), (T("attacks", top, most - 2), "%d 0" % (most - 1)),
                (T("attacks", top, 2), "3 0")]
        # only Sweeping Wind's `max_stacks_add`
        for other in ("Fists of Thunder", "Sweeping Windx", "sweeping wind", ""):
            out += [(T("setto", other, STAT, 0), "0")]
        for other in ("damage_increase_pct", "max_stacks_count", "max_stacks", ""):
            out += [(T("setto", SKILL, other, 0), "0")]
        # another owner's item does nothing
        out += clear + [(T("wears", "Other Fist"), None), (T("setto", SKILL, STAT, 0), "0"), (T("attacks", top, 20), "%d 1" % top)]
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
        want, got = self.drive(MATH.read_text(encoding="utf-8"), WIND_H.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 15)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real, wind = MATH.read_text(encoding="utf-8"), WIND_H.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(real, wind, rows, "want")
        raise_row = [r for r in rows if r[4] == STAT]
        others = [r for r in rows if r[4] != STAT]
        row_mutants = {
            "the_skill_lost": others + [r[:3] + ("Fists of Thunder",) + r[4:] for r in raise_row],
            "nine_stacks": others + [r[:5] + (9.0, 9.0) + r[7:] for r in raise_row],
            "the_wrong_stat": others + [r[:4] + ("max_stacks_count",) + r[5:] for r in raise_row],
            "no_raise_row": others,
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, wind, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double SkillSetTo("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "never_raises": ("if (value > base)", "if (value < base)"),
            "reads_the_player_rows": ('"skill", skill, stat', '"player", skill, stat'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), wind, rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {}
        most = wind[wind.index("inline unsigned MaxStacks("):]
        most = most[:most.index("\n    }\n") + 7]
        for name, (old, new) in {"the_raise_ignored": ("std::max(0.0, sheetMax) + std::max(0.0, raise)", "std::max(0.0, sheetMax)"),
                                 "the_raise_replaces": ("std::max(0.0, sheetMax) + std::max(0.0, raise)", "std::max(std::max(0.0, sheetMax), raise)"),
                                 "one_short": ("std::max(0.0, sheetMax) + std::max(0.0, raise)", "std::max(0.0, sheetMax) + std::max(0.0, raise) - 1")}.items():
            header_mutants[name] = (real, wind.replace(most, most.replace(old, new, 1)))
        for name, (math_text, wind_text) in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertTrue(math_text != real or wind_text != wind, name + " did not apply")
                _, got = self.drive(math_text, wind_text, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
