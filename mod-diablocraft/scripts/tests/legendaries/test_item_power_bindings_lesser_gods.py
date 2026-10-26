"""Legendary rest, bead diablocraft-zhizu: Bindings of the Lesser Gods (Monk bracers, list row 246, K3, N-DEBUFF).

  "Enemies hit by your Cyclone Strike take [150-200]% increased damage from your Mystic Ally for 5 seconds. Split Fire Allies gain 3 times
  this bonus."
  * the text and numbers are read from the catalogue's P71 row and d3planner's entry (item_wrists.js, leg_bindingsofthelessergods); the table
    (data/legendary_powers.csv) holds, for the pool item P71_Unique_Bracer_108, an `effect` row `mark_enemy` (skill Mystic Ally: the skill whose
    damage the mark raises; 150-200, rolled once per item; stack_seconds 5: the mark's seconds; fired on a `hit` of Cyclone Strike) and a
    `skill` row `mark_split_factor` 3 on Mystic Ally;
  * the mark is a real debuff record on the enemy (data/legendary_power_buffs.csv, aura `mark`, spell 83555, the first of its kind, shaped for
    the powers that follow): an enemy-aimed dummy aura flagged a debuff, its text stating no number; the migration carries it;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    refuses a mark row it cannot carry;
  * the production rules are compiled and driven with the generated rows: MarkFactor (dc_item_power_math.h) is 1 + N/100, N times the split
    factor for a split hit, and nothing without a mark; the split factor is read only while the bracers are worn;
  * the module's files read them (source guards with their own mutants): a `mark_enemy` effect puts the owner's record on the hit's target
    with the player as its caster, the rolled percent in its effect amount and the row's seconds; the reader finds only the player's own mark,
    only for the marked skill, and ComputeHit multiplies it in, a Fire Ally hit as the split one;
  * mutants of the rows, of the rules and of the header fail. The C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-zhizu.md.
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
from test_control_immunity_gap import insert_rows, newest_spell_render

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_bindings_lesser_gods/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P71_Unique_Bracer_108"
SKILL = "Mystic Ally"
MARK_ID = 83555
BROUGHT_BY = "combat_0074_bindings_mark.sql"   # the migration that brought the record
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
TEXT = ("Enemies hit by your Cyclone Strike take [150-200]% increased damage from your Mystic Ally for 5 seconds. Split Fire Allies gain 3 "
        "times this bonus.")


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def mark_row(rows):
    return next(r for r in rows if r[4] == "mark_enemy")


def split_row(rows):
    return next(r for r in rows if r[4] == "mark_split_factor")


class Table(unittest.TestCase):
    def test_the_sources_say_150_to_200_for_5_seconds_and_3_times(self):
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual(TEXT, catalogue[0]["power_text"])
        planner = (REPO / "reference/d3planner/item_wrists.js").read_text(encoding="utf-8")
        self.assertIn('format: "Enemies hit by your Cyclone Strike take %d%% increased damage from your Mystic Ally for 5 seconds."', planner)

    def test_the_two_rows(self):
        rows = mine()
        self.assertEqual(2, len(rows))
        self.assertEqual((OWNER, 0, "effect", SKILL, "mark_enemy", 150.0, 200.0, "", 0.0, "", 5.0, 0, "hit", "Cyclone Strike", 100.0, 0.0), mark_row(rows))
        self.assertEqual((OWNER, 0, "skill", SKILL, "mark_split_factor", 3.0, 3.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0), split_row(rows))

    def test_the_mark_has_its_record_row(self):
        rows = [r for r in read_csv("data/legendary_power_buffs.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertEqual((str(MARK_ID), "mark_enemy", "mark"), (rows[0]["spell_id"], rows[0]["stat"], rows[0]["aura"]))
        self.assertNotIn("$s", rows[0]["text"])

    def test_the_record_is_an_enemy_debuff_in_the_migration(self):
        # the newest full spell render carries the record unchanged from the migration that brought it (combat_0074); nothing is
        # asserted about the render's other records, so a later render of another record leaves this green
        updates = MODULE / "data/sql/db-world/updates"
        sql = newest_spell_render(updates).read_text(encoding="utf-8")
        brought = {int(r["ID"]): r for r in insert_rows((updates / BROUGHT_BY).read_text(encoding="utf-8"), "spell_dbc")}
        rendered = {int(r["ID"]): r for r in insert_rows(sql, "spell_dbc")}
        self.assertIn(MARK_ID, brought)
        self.assertEqual(brought[MARK_ID], rendered.get(MARK_ID))
        header = re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql, re.S)[1].replace("`", "").split(", ")
        line = next(l for l in sql.split("\n") if l.startswith("(%d," % MARK_ID))
        values = line[1:line.index("'")].split(",")[:-1]
        by = dict(zip(header, values))
        self.assertEqual(str(MARK_ID), by["ID"])
        self.assertTrue(int(by["Attributes"]) & 0x04000000, "SPELL_ATTR0_AURA_IS_DEBUFF")
        self.assertEqual("6", by["ImplicitTargetA_1"])   # TARGET_UNIT_TARGET_ENEMY
        self.assertEqual("6", by["Effect_1"])             # SPELL_EFFECT_APPLY_AURA
        self.assertEqual("4", by["EffectAura_1"])         # SPELL_AURA_DUMMY
        self.assertNotIn("$s", line)


class Generator(unittest.TestCase):
    MARK = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": SKILL, "stat": "mark_enemy", "value_min": "150", "value_max": "200",
            "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "5", "stack_max": "", "fire_on": "hit", "fire_skills": "Cyclone Strike",
            "chance_pct": "", "icd_seconds": "", "source": "s", "note": "n"}
    SPLIT = {**MARK, "kind": "skill", "stat": "mark_split_factor", "value_min": "3", "value_max": "3", "stack_seconds": "", "fire_on": "",
             "fire_skills": ""}

    def render_with(self, mark=None, split=None, buff=True):
        work = Path(tempfile.mkdtemp(prefix="bindings-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            buffs = read_csv("data/legendary_power_buffs.csv")
            with (work / "data/legendary_power_buffs.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(buffs[0].keys()))
                writer.writeheader()
                writer.writerows([b for b in buffs if buff or b["owner"] != OWNER])
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            extra = ([{**self.MARK, **mark}] if mark is not None else []) + ([{**self.SPLIT, **split}] if split is not None else [])
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + extra)
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len([r for r in self.render_with({}, {}) if r[0] == OWNER]))

    def test_it_refuses_a_mark_it_cannot_carry(self):
        refused = {
            "no seconds": {"stack_seconds": ""},
            "stacks": {"stack_max": "3"},
            "a condition": {"cond": "triggered", "cond_arg": "3"},
            "a chance": {"chance_pct": "50"},
            "a cooldown": {"icd_seconds": "1"},
            "a set bonus": {"pieces": "2"},
            "no skill": {"skill": ""},
            "another skill list": {"skill": "Mystic Ally;Cyclone Strike"},
            "not a skill": {"skill": "Mystic Allyx"},
            "a cast": {"fire_on": "cast"},
            "a kill": {"fire_on": "kill", "fire_skills": ""},
            "no skills fired": {"fire_skills": ""},
            "not a number": {"value_min": "0", "value_max": "0"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit, {})

    def test_it_refuses_a_mark_without_its_record(self):
        with self.assertRaises(ValueError):
            self.render_with({}, {}, buff=False)

    def test_it_refuses_a_split_it_cannot_carry(self):
        refused = {
            "another skill": {"skill": "Cyclone Strike"},
            "two skills": {"skill": "Mystic Ally;Cyclone Strike"},
            "one": {"value_min": "1", "value_max": "1"},
            "a range": {"value_min": "2", "value_max": "3"},
            "a part": {"value_min": "2.5", "value_max": "2.5"},
            "a condition": {"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL},
            "an event": {"fire_on": "cast", "fire_skills": SKILL},
            "a set bonus": {"pieces": "2"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with({}, edit)

    def test_a_split_needs_its_mark(self):
        with self.assertRaises(ValueError):
            self.render_with(None, {})


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itembindings-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # the mark's seconds are the row's own 5
        out += [(T("seconds", OWNER), "5"), (T("seconds", "Other Bracers"), "0")]
        # not worn: the split factor is the base 1
        out += clear + [(T("split"), "1"), (T("hit", 150, 1), "2.5"), (T("hit", 150, 0), "2.5")]
        # worn: a split hit reads three times the percent, any other hit the percent
        out += clear + [(T("wears", OWNER), None), (T("split"), "3"), (T("hit", 150, 1), "5.5"), (T("hit", 200, 1), "7"),
                        (T("hit", 150, 0), "2.5"), (T("hit", 200, 0), "3")]
        # the pure rule: 1 + N/100, times the split; no mark, no change; a split below 1 is 1
        out += [(T("mark", 0, 3), "1"), (T("mark", -10, 3), "1"), (T("mark", 100, 1), "2"), (T("mark", 100, 3), "4"), (T("mark", 175, 3), "6.25"),
                (T("mark", 100, 0.5), "2"), (T("mark", 100, 0), "2")]
        # another owner's bracers do nothing
        out += clear + [(T("wears", "Other Bracers"), None), (T("split"), "1"), (T("hit", 150, 1), "2.5")]
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
        self.assertGreater(len(want), 15)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        want, _ = self.drive(real, rows, "want")
        others = [r for r in rows if r[4] != "mark_split_factor"]
        marks = [r for r in rows if r[4] != "mark_enemy"]
        row_mutants = {
            "no_split_row": others,
            "split_two": others + [r[:5] + (2.0, 2.0) + r[7:] for r in rows if r[4] == "mark_split_factor"],
            "split_of_another_skill": others + [r[:3] + ("Cyclone Strike",) + r[4:] for r in rows if r[4] == "mark_split_factor"],
            "split_of_another_stat": others + [r[:4] + ("max_stacks_add",) + r[5:] for r in rows if r[4] == "mark_split_factor"],
            "mark_seconds_lost": marks + [r[:10] + (0.0,) + r[11:] for r in rows if r[4] == "mark_enemy"],
            "mark_seconds_ten": marks + [r[:10] + (10.0,) + r[11:] for r in rows if r[4] == "mark_enemy"],
            "no_mark_row": marks,
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double MarkFactor("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "no_split": ("pct * std::max(split, 1.0) / 100.0", "pct / 100.0"),
            "additive_split": ("pct * std::max(split, 1.0) / 100.0", "(pct + split) / 100.0"),
            "marks_nothing_as_zero": ("pct > 0 ? 1.0 + pct * std::max(split, 1.0) / 100.0 : 1.0", "1.0 + pct * std::max(split, 1.0) / 100.0"),
            "split_below_one_shrinks": ("std::max(split, 1.0)", "split"),
            "percent_as_factor": ("1.0 + pct * std::max(split, 1.0) / 100.0", "pct * std::max(split, 1.0) / 100.0"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
