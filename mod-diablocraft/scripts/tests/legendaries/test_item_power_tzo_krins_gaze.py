"""Legendary rest, bead diablocraft-08i4q: Tzo Krin's Gaze (Monk Spirit Stone), which builds N-CASTAT (a skill's area cast at the enemy, not at the caster).

  "Wave of Light is now cast at your enemy."
  * the text is read from d3planner (item_head.js, leg_tzokrinsgaze, args 0: no number) and the catalogue row; the table (data/legendary_powers.csv) holds ONE
    `skill` row for the pool item Unique_SpiritStone_007_x1: Wave of Light, `cast_at_enemy`, 1 (a flag, no range, nothing to roll);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the stat
    for Wave of Light, refuses another number, another skill, a condition or event, and a set bonus's row;
  * the production rule (src/combat/dc_item_power_math.h: SkillSetTo) is compiled and driven with the generated row: the reader the cast asks (`cast_at_enemy`,
    base 0) is 1 only for Wave of Light, only while the item is worn, never for another skill or stat;
  * mutants of the rule and of the row fail the same driver, and mutants of WaveOfLight::Cast (src/classes/monk/dc_monk_wave_of_light.cpp) fail the source
    guards on it: with the flag the bell (every rune's, Explosive Light's burst too) and the pillar fall at the point the cast was aimed at; without it they
    stay where they were (10 yd ahead, on the Monk for Explosive Light); Shattering Light's line is untouched; the C++ is compile-checked by syntax_check.sh
    and the in-game steps are in docs/test-diablocraft-08i4q.md.
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
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_tzo_krins_gaze/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_SpiritStone_007_x1"
SKILL = "Wave of Light"
STAT = "cast_at_enemy"
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


class Table(unittest.TestCase):
    def test_the_sources_say_wave_of_light_is_cast_at_the_enemy_and_give_no_number(self):
        text = (REPO / "reference/d3planner/item_head.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('custom: {id: "leg_tzokrinsgaze", name: "Wave of Light Cast at Enemy", format: "Wave of Light is now cast at your enemy.", args: 0}',
                      item)
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Wave of Light is now cast at your enemy.", catalogue[0]["power_text"])
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv")])

    def test_one_row_names_wave_of_light(self):
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, 1.0, 1.0, *BLANK)], mine())

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_head.js", rows[0]["source"])
        self.assertIn("leg_tzokrinsgaze", rows[0]["source"])
        self.assertIn("Shattering Light", rows[0]["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("Wave of Light is now cast at your enemy", m[1])

    def test_wave_of_light_is_a_ground_cast(self):
        row = next(r for r in read_csv("data/d3/skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual(("ground_area", "20"), (row["target_type"], row["range_yards"]))


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "1", "value_max": "1", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="tzo-gen-", dir=str(SCRATCH)))
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
        refused = {
            "another number": ({"value_min": "2", "value_max": "2"}, "cast_at_enemy is an item's value 1"),
            "a range": ({"value_min": "1", "value_max": "2"}, "cast_at_enemy is an item's value 1"),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
            "another skill": ({"skill": "Cyclone Strike"}, "cast_at_enemy is an item's value 1"),
            "two skills": ({"skill": "Wave of Light;Cyclone Strike"}, "cast_at_enemy is an item's value 1"),
            "not a skill": ({"skill": "Wave of Lightx"}, "is not a skill"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL}, "cast_at_enemy is an item's value 1"),
            "an event": ({"fire_on": "cast", "fire_skills": SKILL}, "an event fires"),
            "a set bonus": ({"pieces": "2"}, "not a set"),
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
        work = Path(tempfile.mkdtemp(prefix="itemtzo-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: cast as the skill always is
        out += clear + [(T("setto", SKILL, STAT, 0), "0")]
        # worn: Wave of Light is cast at the enemy
        out += clear + [(T("wears", OWNER), None), (T("setto", SKILL, STAT, 0), "1")]
        # only Wave of Light, only `cast_at_enemy`
        for other in ("Cyclone Strike", "Seven-Sided Strike", "Wave of Lightx", "wave of light", ""):
            out += [(T("setto", other, STAT, 0), "0")]
        for other in ("damage_increase_pct", "pierces", "cast_at_enemyx", ""):
            out += [(T("setto", SKILL, other, 0), "0")]
        # another owner's item does nothing
        out += clear + [(T("wears", "Other Stone"), None), (T("setto", SKILL, STAT, 0), "0")]
        # a skill's own number is never lowered
        out += clear + [(T("wears", OWNER), None), (T("setto", SKILL, STAT, 3), "3")]
        # taken off
        out += clear + [(T("setto", SKILL, STAT, 0), "0")]
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
        self.assertGreater(len(want), 10)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Cyclone Strike",) + r[4:] for r in rows],
            "the_flag_zero": [r[:5] + (0.0, 0.0) + r[7:] for r in rows],
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
            "skill_ignored": ('"skill", skill, stat', '"skill", "Wave of Light", stat'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {}
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
