"""Legendary rest, bead diablocraft-z6znd: Bastion's Revered (Barbarian two-hand Mighty Weapon).

  "Frenzy now stacks up to 10 times and hits an additional time per stack. Each additional hit will chain to any enemies within 15 yards,
   and the damage is split between all of the affected enemies."
  * the three numbers (10 stacks, one extra hit a stack, 15 yards) are read from d3planner (item_twohand.js, leg_bastionsrevered_p68, args 0:
    nothing is rolled), checked against the catalogue row and the class sheet's text;
  * the table (data/legendary_powers.csv) holds three fixed `skill` rows on Frenzy: buff_max_stacks 10, extra_hits_per_stack 1, chain_yards 15;
    the generator refuses another skill, a range, zero and a fraction;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: SkillSetTo, ExtraHits, ChainShare) are compiled and driven with the generated rows:
    10 stacks only while the item is worn, never below Frenzy's own 5, no other skill; one extra hit per stack held; the damage of an extra hit
    split equally and whole between its victims; mutants fail the same driver;
  * source-text guards on src/classes/barbarian/dc_barbarian_primaries.cpp (the C++ is compile-checked by syntax_check.sh; the GrantFrenzy cap is also driven in
    test_primary_provider.py with the production source): the three places a stack is added read MaxStacks, the extra hits are Frenzy's own,
    re-rolled with ComputeHit, split with ChainShare over the live victims; mutated sources fail the guard.
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
HARNESS = MODULE / "tests/item_power_bastions_revered/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P68_Unique_Mighty_2H_004"
TEXT = ("Frenzy now stacks up to 10 times and hits an additional time per stack. Each additional hit will chain to any enemies within 15 yards, "
        "and the damage is split between all of the affected enemies.")
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%g" % x  # noqa: E731


def read_csv_path(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(max stacks, extra hits per stack, yards) as d3planner words them, checked against the catalogue and the class sheet."""
    text = (REPO / "reference/d3planner/item_twohand.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    assert 'format: "%s"' % TEXT in item and "args: 0" in item, item
    stacks = int(re.search(r"stacks up to (\d+) times", TEXT)[1])
    yards = int(re.search(r"within (\d+) yards", TEXT)[1])
    assert "hits an additional time per stack" in TEXT   # one extra hit a stack: "an additional time"
    cat = next(r for r in read_csv_path(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
    assert cat["power_text"] == TEXT, cat["power_text"]
    sheet = next(r for r in read_csv_path(MODULE / "data/d3/barbarian_legendaries.csv") if r["item_name"] == "Bastion's Revered")
    assert sheet["legendary_power_text"] == TEXT, sheet
    return stacks, 1, yards


class Table(unittest.TestCase):
    def test_the_sources_state_ten_stacks_one_extra_hit_and_fifteen_yards(self):
        self.assertEqual((10, 1, 15), numbers())

    def test_three_fixed_frenzy_rows(self):
        stacks, hits, yards = numbers()
        want = {(OWNER, 0, "skill", "Frenzy", stat, float(v), float(v), *BLANK)
                for stat, v in (("buff_max_stacks", stacks), ("extra_hits_per_stack", hits), ("chain_yards", yards))}
        self.assertEqual(want, set(mine()))
        self.assertEqual(3, len(mine()))

    def test_frenzys_own_stack_cap_is_below_the_item(self):
        own = next(r for r in read_csv_path(MODULE / "data/d3/barbarian_skill_values.csv") if r["skill"] == "Frenzy" and r["token"] == "max_stacks_count" and not r["rune"])
        self.assertEqual("5", own["value"])
        self.assertIn("frenzy_max_stacks = 5", (SRC / "classes/barbarian/dc_barbarian_primary_data.h").read_text(encoding="utf-8"))

    @staticmethod
    def rows_of(sheet_rows):
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as folder:
            module = Path(folder)
            (module / "data/d3").mkdir(parents=True)
            for name in ("base_items.csv", "affix_pools.csv", "legendary_potions.csv", *sorted(p.name for p in (MODULE / "data/d3").glob("*_skills.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_skill_values.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_runes.csv"))):
                shutil.copy(MODULE / "data/d3" / name, module / "data/d3" / name)
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", module / "data/legendary_power_buffs.csv")
            with (module / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(sheet_rows[0]))
                writer.writeheader()
                writer.writerows(sheet_rows)
            return [row for row in generator.rows(module) if row[2] != "potion"]

    def test_the_generator_refuses_a_bad_row(self):
        sheet = [r for r in read_csv_path(MODULE / "data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(3, len(self.rows_of(sheet)))
        for stat in ("buff_max_stacks", "extra_hits_per_stack", "chain_yards"):
            base = next(r for r in sheet if r["stat"] == stat)
            refused = {
                "another skill": dict(base, skill="Bash"),
                "a list of skills": dict(base, skill="Frenzy;Bash"),
                "a range": dict(base, value_max=str(float(base["value_max"]) + 1)),
                "zero": dict(base, value_min="0", value_max="0"),
                "a fraction": dict(base, value_min="2.5", value_max="2.5"),
            }
            for name, row in refused.items():
                with self.subTest(stat=stat, case=name), self.assertRaises(ValueError):
                    self.rows_of([row])

    def test_the_newest_table_is_not_yet_shipped(self):
        self.assertNotIn(GENERATED.name, (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itembastion-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        stacks, per, yards = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        worn = clear + [(T("wears", OWNER), None)]
        # not worn: Frenzy keeps its own 5, no extra hit, no chain
        out += clear + [(T("setto", "Frenzy", "buff_max_stacks", 5), "5"), (T("setto", "Frenzy", "chain_yards", 0), "0")]
        out += [(T("extra", n), "0") for n in (0, 1, 5, 10)]
        # worn: ten stacks, fifteen yards, one extra hit for each stack held
        out += worn + [(T("setto", "Frenzy", "buff_max_stacks", 5), g(stacks)), (T("setto", "Frenzy", "chain_yards", 0), g(yards)),
                       (T("setto", "Frenzy", "extra_hits_per_stack", 0), g(per))]
        out += [(T("extra", n), str(n * per)) for n in range(0, 11)]
        # a power that sets a number never lowers one
        out += [(T("setto", "Frenzy", "buff_max_stacks", 12), "12")]
        # only Frenzy: no other skill, no other stat
        for other in ("Weapon Throw", "Bash", "Cleave", "Whirlwind", "Rend", "Frenzy;Bash", "Fren", ""):
            out += [(T("setto", other, "buff_max_stacks", 5), "5"), (T("setto", other, "chain_yards", 0), "0")]
        out += [(T("setto", "Frenzy", "dot_max_stacks", 1), "1"), (T("setto", "Frenzy", "dot_duration_seconds", 4), "4")]
        # the item in the bag, not worn
        out += clear + [(T("setto", "Frenzy", "buff_max_stacks", 5), "5")] + [(T("extra", 10), "0")]
        # the split: equal, whole, one victim takes it all, nobody takes nothing
        out += [(T("share", 100, 1), "100"), (T("share", 100, 2), "50"), (T("share", 100, 4), "25"), (T("share", 90, 3), "30"), (T("share", 100, 0), "0")]
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

    def test_every_rule_agrees_with_the_sources(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(3, len(rows))
        row_mutants = {
            "five_stacks": [r[:5] + (5.0, 5.0) + r[7:] if r[4] == "buff_max_stacks" else r for r in rows],
            "chain_ten_yards": [r[:5] + (10.0, 10.0) + r[7:] if r[4] == "chain_yards" else r for r in rows],
            "two_extra_hits_a_stack": [r[:5] + (2.0, 2.0) + r[7:] if r[4] == "extra_hits_per_stack" else r for r in rows],
            "the_wrong_skill": [r[:3] + ("Bash",) + r[4:] for r in rows],
            "no_chain_row": [r for r in rows if r[4] != "chain_yards"],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "extra_hits_ignore_the_stacks": real.replace("static_cast<unsigned>(perStack) * stacks", "static_cast<unsigned>(perStack)"),
            "extra_hits_are_one_more": real.replace("static_cast<unsigned>(perStack) * stacks", "static_cast<unsigned>(perStack) * (stacks + 1)"),
            "the_share_is_not_split": real.replace("return victims ? total / victims : 0.0;", "return total;"),
            "the_share_leaves_the_target_out": real.replace("return victims ? total / victims : 0.0;", "return victims > 1 ? total / (victims - 1) : total;"),
            "set_to_takes_the_lowest": real.replace("            if (value > base)\n                base = value;\n        return base;\n    }\n\n    // A passive's number",
                                                    "            if (value < base)\n                base = value;\n        return base;\n    }\n\n    // A passive's number"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
