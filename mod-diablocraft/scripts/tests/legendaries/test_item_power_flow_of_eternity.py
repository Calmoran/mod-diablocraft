"""Legendary rest, bead diablocraft-fyi93: The Flow of Eternity (Monk daibo), on the standing S-DMG and N-CD pieces.

  "Increase the damage of Seven-Sided Strike by 100% and reduce the cooldown of Seven-Sided Strike by [45-60]%."
  * the text and range are read from d3planner (data.json items, leg_theflowofeternity_p2, min 45 max 60) and the catalogue row; the table
    (data/legendary_powers.csv) holds TWO `skill` rows for the pool item P41_Unique_CombatStaff_2H_005 on Seven-Sided Strike: `damage_increase_pct` 100
    (the text's fixed number) and `cooldown_reduction_pct` 45-60, a range the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: SkillFactor and CooldownFactor) are compiled and driven with the generated rows: the damage is
    doubled and the cooldown is 1 - N/100 of itself with the item's stored roll, only for Seven-Sided Strike, only while the item is worn;
  * mutants of the rows and the rules fail the same driver, and mutants of the skill's own readers fail the source guards: every strike, Sudden
    Assault's area and Incinerate's burn go through Combat::Strike / StrikeArea (ComputeHit's hit.legendary, which reads SkillFactor by the shell's skill),
    and the cooldown the last strike starts again is Combat::SkillCooldownMilliseconds (which applies CooldownFactor; Gesture of Orpheus's test guards
    that reader and the cast's cut). The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-fyi93.md.
"""
import csv
import json
import re
import shutil
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_flow_of_eternity/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P41_Unique_CombatStaff_2H_005"
LEGACY = "Unique_CombatStaff_2H_005_x1"
SKILL = "Seven-Sided Strike"
DAMAGE, COOLDOWN = "damage_increase_pct", "cooldown_reduction_pct"
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


def planner(item_id=OWNER):
    """(text, min, max) of the item's power in d3planner's data.json."""
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == item_id)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


class Table(unittest.TestCase):
    def test_the_sources_say_double_damage_and_cooldown_45_to_60(self):
        text, low, high = planner()
        self.assertEqual("Increase the damage of Seven-Sided Strike by 100%% and reduce the cooldown of Seven-Sided Strike by %d%%.", text)
        self.assertEqual((45.0, 60.0), (low, high))
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Increase the damage of Seven-Sided Strike by 100% and reduce the cooldown of Seven-Sided Strike by [45-60]%.", catalogue[0]["power_text"])
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv")])

    def test_two_rows_on_seven_sided_strike(self):
        _, low, high = planner()
        self.assertEqual(sorted([(OWNER, 0, "skill", SKILL, DAMAGE, 100.0, 100.0, *BLANK), (OWNER, 0, "skill", SKILL, COOLDOWN, low, high, *BLANK)]),
                         sorted(mine()))

    def test_the_owner_is_the_monk_daibo_that_drops(self):
        item = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("The Flow of Eternity", "twohand", "Daibo", "legendary", "monk", "yes", "no"),
                         (item["d3_name"], item["slot"], item["type"], item["rarity"], item["designated_class"], item["pool_version"],
                          item["craft_only"]))
        # the legacy twin has its own rows nowhere: it owns the pool item's under the legacy-twin rule
        self.assertEqual("no", next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == LEGACY)["pool_version"])
        self.assertEqual([], [r for r in all_rows() if r[0] == LEGACY])

    def test_the_rows_have_their_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertIn("leg_theflowofeternity_p2", row["source"])
        self.assertIn("legacy twin", next(r for r in rows if r["stat"] == COOLDOWN)["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("Increase the damage of Seven-Sided Strike by 100% and reduce the cooldown of Seven-Sided Strike by 45", m[1])


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemflow-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        _, low, high = planner()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        both = ("damage", "factor")
        # not worn: nothing, even with the item's roll known (taken off, in the bag)
        out += clear + [(T(c, SKILL), "1") for c in both]
        out += clear + [(T("rolled", OWNER, SKILL, COOLDOWN, low), None)] + [(T(c, SKILL), "1") for c in both]
        # worn, each end of the roll: twice the damage, and 45% off is 0.55 of the cooldown, 60% off 0.4
        for roll in (low, high):
            out += clear + [(T("wears", OWNER, SKILL, COOLDOWN, roll), None), (T("damage", SKILL), "2"),
                            (T("factor", SKILL), "%.10g" % (1 - roll / 100))]
        # worn with no stored roll (an item rolled before the row existed): the fixed damage holds, the ranged cut has nothing to read
        out += clear + [(T("wears", OWNER, "", "", 0), None), (T("damage", SKILL), "2"), (T("factor", SKILL), "1")]
        # only Seven-Sided Strike
        out += clear + [(T("wears", OWNER, SKILL, COOLDOWN, low), None)]
        for other in ("Lashing Tail Kick", "Seven-Sided Strikes", "seven-sided strike", ""):
            out += [(T(c, other), "1") for c in both]
        # another owner's item alone does not carry these rows
        out += clear + [(T("wears", "Some Daibo", SKILL, COOLDOWN, 50), None)] + [(T(c, SKILL), "1") for c in both]
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
        self.assertEqual(2, len(rows))
        want, _ = self.drive(real, rows, "want")
        damage = [r for r in rows if r[4] == DAMAGE]
        cut = [r for r in rows if r[4] == COOLDOWN]
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Lashing Tail Kick",) + r[4:] for r in rows],
            "no_damage_row": cut,
            "no_cooldown_row": damage,
            "damage_150": [r[:5] + (150.0, 150.0) + r[7:] for r in damage] + cut,
            "damage_as_a_range": [r[:5] + (50.0, 100.0) + r[7:] for r in damage] + cut,
            "the_cut_as_damage": damage + [r[:4] + (DAMAGE,) + r[5:] for r in cut],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        rules = {
            "damage_percent_as_a_fraction": ("factor *= 1.0 + pct / 100.0;\n        return factor;\n    }\n\n    // The multiplier of the `damage_by_missing",
                                             "factor *= 1.0 + pct;\n        return factor;\n    }\n\n    // The multiplier of the `damage_by_missing"),
            "cooldown_lengthens": ("std::max(0.0, 1.0 - pct / 100.0)", "std::max(0.0, 1.0 + pct / 100.0)"),
            "cooldown_reads_damage": ('"skill", skill, "cooldown_reduction_pct"', '"skill", skill, "damage_increase_pct"'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                _, got = self.drive(real.replace(old, new), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_bottom_not_the_roll": real.replace("number = found->value;", "number = row.min;"),
            "a_fixed_row_needs_a_roll": real.replace("if (!row.pieces && Rolls(row))", "if (!row.pieces)"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
