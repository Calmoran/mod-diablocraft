"""Legendary rest, bead diablocraft-cnc98: Skular's Salvation (Barbarian bracers), the second reader of N-NHIT (the cast's enemy count).

  "Increase the damage of Ancient Spear by [150 - 200]%. If your Ancient Spear - Boulder Toss hits 5 or fewer enemies, the damage is increased by 100%."
  * the numbers (the roll range 150-200, the count 5, the fixed 100) are read from d3planner's data.json (the pool item P73_Unique_Bracer_101,
    `leg_skularssalvation_p73`), the skill from barbarian_skills.csv and the rune from barbarian_runes.csv, apart from the table; the table
    (data/legendary_powers.csv) holds TWO `skill` rows for the pool item: Ancient Spear `damage_increase_pct` 150-200 (every rune, rolled once per
    item) and "Ancient Spear - Boulder Toss" `damage_increase_pct` 100 (fixed) under the condition `cast_enemies_at_most` 5;
  * the generator accepts `cast_enemies_at_most` only on a skill's damage_increase_pct row with a whole count, no event and no cond_skills, and a rune-qualified
    skill name only as the single name of a damage_increase_pct row, with a rune of that skill in a *_runes.csv sheet;
  * the production rules (src/combat/dc_item_power_math.h: Holds' `cast_enemies_at_most`, with SkillFactor / Owned / RollPowers) are compiled and
    driven with the generated rows: a Boulder Toss hit in a cast that hits 1 to 5 enemies takes (1 + N/100) x 2, one in a bigger cast or one no
    cast counted takes 1 + N/100 only, and every other rune of Ancient Spear takes 1 + N/100 whatever the count; no other skill takes anything;
    a Primal stores 200;
  * mutants of the rows, the rules and the header fail the same driver;
  * the source-text guards (the Boulder Toss burst and ResolveCast set the count around their hits, the count is thread_local, the hit reads the
    "skill - rune" name) are in test_item_power_skulars_salvation_wiring.py; the C++ is compile-checked by syntax_check.sh and the in-game steps
    are in docs/test-diablocraft-cnc98.md.
"""
import csv
import json
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
HARNESS = MODULE / "tests/item_power_skulars_salvation/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P73_Unique_Bracer_101"
SKILL = "Ancient Spear"
RUNE = "Boulder Toss"
QUALIFIED = "%s - %s" % (SKILL, RUNE)
OTHER_RUNES = ("Harpoon", "Jagged Edge", "Ranseur", "Rage Flip")
STAT = "damage_increase_pct"
COND = "cast_enemies_at_most"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(low, high, count, extra) as the planner words the pool item's power."""
    items = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"]
    item = next(i for i in items if i["id"] == OWNER)
    custom = item["required"]["custom"]
    m = re.fullmatch(r"Increase the damage of Ancient Spear by %d%%\. If your Ancient Spear - Boulder Toss hits (\d+) or fewer enemies, "
                     r"the damage is increased by (\d+)%%\.", custom["format"])
    assert m, custom["format"]
    return float(custom["min"]), float(custom["max"]), int(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_name_the_skill_the_rune_the_range_and_the_count(self):
        self.assertEqual((150.0, 200.0, 5, 100.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])
        self.assertIn((SKILL, RUNE), [(r["skill_name"], r["rune_name"]) for r in read_csv("data/d3/barbarian_runes.csv")])

    def test_two_damage_rows_name_ancient_spear_and_boulder_toss(self):
        low, high, count, extra = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
                          (OWNER, 0, "skill", QUALIFIED, STAT, extra, extra, COND, float(count), "", 0.0, 0, "", "", 100.0, 0.0)],
                         sorted(mine(), key=lambda r: r[3]))

    def test_the_owner_is_the_barbarian_bracer_that_drops(self):
        item = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Skular's Salvation", "wrists", "legendary", "barbarian", "yes", "no"),
                         (item["d3_name"], item["slot"], item["rarity"], item["designated_class"], item["pool_version"], item["craft_only"]))

    def test_the_rows_have_their_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertIn("leg_skularssalvation_p73", row["source"])
            self.assertIn("data.json", row["source"])
            self.assertTrue(row["note"])

    def test_the_roll_key_fits_the_affix_column(self):
        self.assertLessEqual(len("power:%s:%s" % (SKILL, STAT)), 64)
        self.assertLessEqual(len("power:%s:%s" % (QUALIFIED, STAT)), 64)


class Generator(unittest.TestCase):
    PLAIN = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "150", "value_max": "200", "cond": "",
             "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
             "icd_seconds": "", "source": "s", "note": "n"}
    FEW = {**PLAIN, "skill": QUALIFIED, "value_min": "100", "value_max": "100", "cond": COND, "cond_arg": "5"}

    def render_with(self, *edits):
        """The generator run on a copy of the module whose sheet is the real one with the owner's rows replaced by `edits` (dicts over FEW)."""
        work = Path(tempfile.mkdtemp(prefix="skular-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [self.PLAIN] + [{**self.FEW, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.assertEqual(2, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        few = "cast_enemies_at_most is a skill's damage_increase_pct row's"
        qualified = "a rune-qualified skill"
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min <= value_max"),
            "no count": ({"cond_arg": ""}, "needs cond_arg > 0"),
            "a part of an enemy": ({"cond_arg": "5.5"}, few),
            "another stat": ({"stat": "attack_speed_pct"}, qualified + "|" + few),
            "named skills": ({"cond_skills": "Ancient Spear"}, few),
            "an event": ({"fire_on": "cast", "fire_skills": "Ancient Spear"}, "an event fires an effect row|" + few),
            "an effect row": ({"kind": "effect", "skill": "", "stat": "resource_refund"}, few),
            "a rune the skill lacks": ({"skill": SKILL + " - Boulder Tossx"}, "is not a skill"),
            "a rune of another skill": ({"skill": SKILL + " - Stagger"}, "is not a skill"),
            "a skill that is not one": ({"skill": "Ancient Spearx - " + RUNE}, "is not a skill"),
            "a rune on a list": ({"skill": QUALIFIED + ";Weapon Throw"}, qualified),
            "a rune on another stat": ({"stat": "cooldown_reduction_pct", "cond": "", "cond_arg": ""}, qualified),
            "an unknown condition": ({"cond": "cast_enemy_at_most"}, "cond is one of"),
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
        work = Path(tempfile.mkdtemp(prefix="itemskular-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        low, high, count, extra = numbers()
        few = 1 + extra / 100
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: nothing, whatever the cast
        out += clear + [(T("hit", SKILL, RUNE, 1), "1")]
        # worn, no roll stored yet: the fixed 100 is the table's and stands, the rolled range gives no power
        out += clear + [(T("wears", OWNER), None)]
        for enemies in range(0, count + 4):
            out += [(T("hit", SKILL, RUNE, enemies), g(few) if 1 <= enemies <= count else "1")]
        out += [(T("hit", SKILL, "Harpoon", 1), "1")]
        # worn and rolled: every rune takes 1 + N/100; Boulder Toss takes the fixed 100 more in a cast that hits 1 to `count` enemies
        for roll in (low, 175, high):
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, roll), None)]
            for enemies in range(0, count + 12):
                out += [(T("hit", SKILL, RUNE, enemies), g((1 + roll / 100) * few) if 1 <= enemies <= count else g(1 + roll / 100))]
            for rune in OTHER_RUNES + ("-",):
                for enemies in (0, 1, count, count + 1):
                    out += [(T("hit", SKILL, rune, enemies), g(1 + roll / 100))]
            for wrong in ("Boulder", "Boulder Toss ", "boulder toss", ""):
                out += [(T("hit", SKILL, wrong or "-", 1), g(1 + roll / 100))]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, STAT, 175), None), (T("hit", SKILL, RUNE, 1), "1")]
        # only Ancient Spear: no other skill takes either row, not with the Boulder Toss rune name either
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, high), None)]
        for other in ("Seismic Slam", "Weapon Throw", "Whirlwind", "Leap", "Ancient", "Ancient Spears", ""):
            for enemies in (1, count + 1):
                out += [(T("hit", other, RUNE, enemies), "1"), (T("hit", other, "-", enemies), "1")]
        # one roll stored under the skill's name (the fixed row stores none): a Primal stores the top of the range
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, STAT, high)),
                (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, STAT, (low + high) / 2))]
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
        self.assertGreater(len(want), 150)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        rolled = next(r for r in rows if r[3] == SKILL)
        few = next(r for r in rows if r[3] == QUALIFIED)
        other = lambda keep: [r for r in rows if r is not keep]  # noqa: E731
        row_mutants = {
            "the_skill_lost": [rolled[:3] + ("Seismic Slam",) + rolled[4:], few],
            "the_range_halved": [rolled[:5] + (rolled[5] / 2, rolled[6] / 2) + rolled[7:], few],
            "the_rune_lost": [rolled, few[:3] + (SKILL,) + few[4:]],
            "another_rune": [rolled, few[:3] + (SKILL + " - Harpoon",) + few[4:]],
            "the_count_of_the_old_item": [rolled, few[:8] + (3.0,) + few[9:]],
            "the_count_off_by_one": [rolled, few[:8] + (6.0,) + few[9:]],
            "no_condition": [rolled, few[:7] + ("", 0.0) + few[9:]],
            "the_fixed_number_halved": [rolled, few[:5] + (few[5] / 2, few[6] / 2) + few[7:]],
            "only_the_rolled_row": other(few),
            "only_the_fixed_row": other(rolled),
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        rules = {
            "the_last_count_dropped": ("situation.castEnemies <= row.arg", "situation.castEnemies < row.arg"),
            "one_more_enemy": ("situation.castEnemies <= row.arg", "situation.castEnemies <= row.arg + 1"),
            "an_uncounted_hit_takes_it": ("situation.castEnemies >= 1 && situation.castEnemies <= row.arg", "situation.castEnemies <= row.arg"),
            "every_hit_takes_it": ("return situation.castEnemies >= 1 && situation.castEnemies <= row.arg;", "return true;"),
            "a_big_cast_takes_it": ("return situation.castEnemies >= 1 && situation.castEnemies <= row.arg;", "return situation.castEnemies >= 1;"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                want, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "an_unworn_item_counts": real.replace("situation.wornSince.count(row.owner)", "true"),
            "a_primal_stores_the_bottom": real.replace("atTop ? Best(row) : roll(row.min, row.max)", "atTop ? row.min : roll(row.min, row.max)"),
            "a_skill_matches_by_prefix": real.replace("names.compare(from, to - from, skill) == 0", "skill.rfind(names.substr(from, to - from), 0) == 0"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
