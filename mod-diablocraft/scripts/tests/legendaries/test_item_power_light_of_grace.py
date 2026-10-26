"""Legendary rest, bead diablocraft-n8eqs: Light of Grace (Wizard Source), which builds N-PIERCE (a channelled beam that hits every enemy on its line).

  "Ray of Frost now pierces."
  * the text is read from d3planner (item_offhand.js, leg_lightofgrace, args 0: no number) and the catalogue row; the table (data/legendary_powers.csv) holds ONE
    `skill` row for the pool item Unique_Orb_103_x1: Ray of Frost, `pierces`, 1 (a flag, no range, nothing to roll);
  * the beam's width is in no source for Ray of Frost: it is the tunable wizard.ray_of_frost_pierce_width_yards, 4 yd, which is Disintegrate's beam width
    in skill_targeting.csv (borrowed, the PM's ruling of decisions.md 2026-10-13, the designer may overrule it): the CSV row, the migrations and Disintegrate's
    own width agree, and the note says it is borrowed;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the stat
    for Ray of Frost, refuses another number, another skill, a condition or event, and a set bonus's row;
  * the production rule (src/combat/dc_item_power_math.h: SkillSetTo, with Owned / Holds) is compiled and driven with the generated row: the reader the beam
    asks (`pierces`, base 0) is 1 only for Ray of Frost, only while the item is worn, never for another skill or stat;
  * mutants of the rule and of the row fail the same driver, and mutants of ChannelTargets (dc_combat.cpp) fail the source guards on it: the line is added to
    the blast the skill already has (the aimed enemy and those within 5 yd stay), every unit once, the width read from the tunable (a blank or 0 turns it
    off), the heading from the player to the aimed enemy, Sleet Storm (no beam) left out; the C++ is compile-checked by syntax_check.sh and the in-game steps
    are in docs/test-diablocraft-n8eqs.md.
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
HARNESS = MODULE / "tests/item_power_light_of_grace/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Orb_103_x1"
SKILL = "Ray of Frost"
STAT = "pierces"
TUNABLE = "ray_of_frost_pierce_width_yards"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
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


def targeting(skill):
    return next(r for r in read_csv("data/d3/skill_targeting.csv") if r["skill"] == skill)


class Table(unittest.TestCase):
    def test_the_sources_say_ray_of_frost_pierces_and_give_no_number(self):
        text = (REPO / "reference/d3planner/item_offhand.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start)]
        self.assertIn('custom: {id: "leg_lightofgrace", name: "Ray of Frost now pierces", format: "Ray of Frost now pierces.", args: 0}', item)
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Ray of Frost now pierces.", catalogue[0]["power_text"])
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv")])

    def test_one_row_names_ray_of_frost(self):
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, 1.0, 1.0, *BLANK)], mine())

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_offhand.js", rows[0]["source"])
        self.assertIn("leg_lightofgrace", rows[0]["source"])
        self.assertIn("Sleet Storm", rows[0]["note"])
        self.assertIn(TUNABLE, rows[0]["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("Ray of Frost now pierces", m[1])

    def test_the_beam_width_is_the_tunable_and_it_is_disintegrates_four_yards(self):
        beam = targeting("Disintegrate")
        self.assertEqual(("line_pierce", "4"), (beam["target_type"], beam["width_yards"]))
        rows = [r for r in read_csv("data/tunables/wizard.csv") if r["name"] == TUNABLE]
        self.assertEqual(1, len(rows))
        self.assertEqual(("", "4", "yards"), (rows[0]["d3_value"], rows[0]["value"], rows[0]["unit"]))
        for word in ("BORROWED", "Disintegrate", "skill_targeting.csv:32", "the designer may overrule"):
            self.assertIn(word, rows[0]["notes"])
        for path in ("data/generated/tunables_0012.sql", "data/sql/db-world/updates/tunables_0012.sql"):
            self.assertIn("('wizard', '%s', NULL, 4.0, 'yards', " % TUNABLE, (MODULE / path).read_text(encoding="utf-8"))

    def test_ray_of_frost_is_a_single_enemy_channel_the_beam_starts_from(self):
        row = targeting(SKILL)
        self.assertEqual(("single_enemy", "30", "5", "channel"), (row["target_type"], row["range_yards"], row["radius_yards"], row["cast_type"]))


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "1", "value_max": "1", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="grace-gen-", dir=str(SCRATCH)))
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
            "another number": ({"value_min": "2", "value_max": "2"}, "pierces is value 1"),
            "a range": ({"value_min": "1", "value_max": "2"}, "pierces is value 1"),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
            "another skill": ({"skill": "Disintegrate"}, "pierces is value 1"),
            "two skills": ({"skill": "Ray of Frost;Disintegrate"}, "pierces is value 1"),
            "not a skill": ({"skill": "Ray of Frostx"}, "is not a skill"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": "Ray of Frost"}, "pierces is value 1"),
            "an event": ({"fire_on": "cast", "fire_skills": "Ray of Frost"}, "an event fires"),
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
        work = Path(tempfile.mkdtemp(prefix="itemgrace-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: nothing pierces
        out += clear + [(T("setto", SKILL, STAT, 0), "0")]
        # worn: Ray of Frost pierces
        out += clear + [(T("wears", OWNER), None), (T("setto", SKILL, STAT, 0), "1")]
        # only Ray of Frost, only `pierces`
        for other in ("Disintegrate", "Arcane Torrent", "Ray of Frostx", "ray of frost", ""):
            out += [(T("setto", other, STAT, 0), "0")]
        for other in ("damage_increase_pct", "pierce", "piercess", ""):
            out += [(T("setto", SKILL, other, 0), "0")]
        # another owner's item does nothing
        out += clear + [(T("wears", "Other Source"), None), (T("setto", SKILL, STAT, 0), "0")]
        # a skill's own number is never lowered
        out += clear + [(T("wears", OWNER), None), (T("setto", SKILL, STAT, 3), "3")]
        # left the bag
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
            "the_skill_lost": [r[:3] + ("Disintegrate",) + r[4:] for r in rows],
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
            "skill_ignored": ('"skill", skill, stat', '"skill", "Ray of Frost", stat'),
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
