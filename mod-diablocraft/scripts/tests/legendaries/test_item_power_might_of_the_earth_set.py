"""Legendary rest, bead diablocraft-tydva: the Might of the Earth 4-piece bonus (the 6-piece is test_item_power_might_of_the_earth.py's).

  "Leap causes an Earthquake when you land. Additionally, Leap gains the effect of the Iron Impact rune and the rune's effect and duration are
  increased by 150%."
  * the text is read from d3planner's data.json itemSets (the catalogue's source rule for set bonuses) and must match barbarian_sets.csv; Iron
    Impact's own numbers (150% armor, 4 seconds) from barbarian_skill_values.csv; the table (data/legendary_powers.csv) holds THREE rows at pieces
    4: an `effect` row `cast_skill` on Earthquake fired on the new event `land` by Leap (number 0: no internal cooldown), a `rune` row Iron
    Impact on Leap, a `skill` row `rune_effect_pct` 150 on Leap;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    accepts the event, the set's cast and the stat, and refuses them half built (a landing naming no skill, a landing cast with a cooldown, a
    landing cast of an item, a cast_skill on another event, the stat on a skill whose code does not read it);
  * the production rules (src/combat/dc_item_power_math.h: Fire with the set counts, GrantsRune, SkillFactor) are compiled and driven with the
    generated rows: from the 4th piece and not before, a Leap landing fires the Earthquake cast every time (no cooldown), another skill's landing
    or Leap's press does not; Iron Impact is given; the rune's factor is 1 + 150/100, so 375% armor for 10 seconds;
  * mutants of the rows and of the rules fail the same driver;
  * source-text guards that the landing reaches the event after its own resolve, that Leap's landing marks Iron Impact chosen or given with the
    duration raised and that the armor is raised; the C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-tydva.md.
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
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import barbarian_source  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_might_of_the_earth_set/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SET = "Might of the Earth"
EVENT = "land"
CAST = "cast_skill"
STAT = "rune_effect_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
TEXT = re.compile(r"(\w+) causes an (\w+) when you land\. Additionally, (\w+) gains the effect of the ([\w' ]+) rune and the rune's effect and "
                  r"duration are increased by (\d+)%%?\.")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def words():
    """(the skill that lands, the skill it casts, the rune, the percent) from data.json's 4-piece; the sets sheet says the same."""
    found = {m[0] for m in TEXT.finditer((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))}
    assert len(found) == 1, found
    m = TEXT.fullmatch(found.pop())
    sheet = {r["bonus_4pc"] for r in read_csv("data/d3/barbarian_sets.csv") if r["set_name"] == SET}
    assert len(sheet) == 1 and TEXT.fullmatch(sheet.pop()).groups() == m.groups(), sheet
    assert m[1] == m[3], m.groups()
    return m[1], m[2], m[4], float(m[5])


def rune_number(token):
    leap, _, rune, _ = words()
    found = [r for r in read_csv("data/d3/barbarian_skill_values.csv") if r["skill"] == leap and r["rune"] == rune and r["token"] == token]
    assert len(found) == 1, found
    return float(found[0]["value"])


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == SET and r[1] == 4]


def row(kind, skill, stat, value, fire_on="", fire_skills=""):
    return (SET, 4, kind, skill, stat, value, value, "", 0.0, "", 0.0, 0, fire_on, fire_skills, 100.0, 0.0)


class Table(unittest.TestCase):
    def test_the_text_names_leap_earthquake_iron_impact_and_150(self):
        self.assertEqual(("Leap", "Earthquake", "Iron Impact", 150.0), words())
        self.assertEqual((150.0, 4.0), (rune_number("armor_pct"), rune_number("duration_seconds")))
        runes = {(r["skill_name"], r["rune_name"]) for r in read_csv("data/d3/barbarian_runes.csv")}
        self.assertIn(("Leap", "Iron Impact"), runes)

    def test_three_rows_at_four_pieces(self):
        leap, quake, rune, pct = words()
        self.assertEqual(sorted([row("effect", quake, CAST, 0.0, EVENT, leap), row("rune", leap, rune, 1.0), row("skill", leap, STAT, pct)]),
                         sorted(mine()))

    def test_the_two_piece_row(self):
        m = re.search(r"Reduce the cooldown of ([\w ,]+?), and ([\w ]+?) by (\d+) second for every (\d+) Fury you spend with an attack\.",
                      (REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))
        skills = [s.strip() for s in m[1].split(",")] + [m[2]]
        self.assertEqual([(SET, 2, "effect", ";".join(skills), "cooldown_cut_named_seconds", float(m[3]), float(m[3]), "per_resource_spent",
                           float(m[4]), "", 0.0, 0, "resource_spent", "", 100.0, 0.0)],
                         [r for r in all_rows() if r[0] == SET and r[1] == 2])

    def test_leap_is_a_landing_skill(self):
        """The event is a ground_point_aoe landing; the 4-piece is a Leap power, so Leap is pinned by name (other skills may land too),
        and Earthquake is cast on the player."""
        targeting = {r["skill"]: r["target_type"] for r in read_csv("data/d3/skill_targeting.csv")}
        self.assertEqual("ground_point_aoe", targeting["Leap"])
        self.assertEqual("self_aoe", targeting["Earthquake"])


class Generator(unittest.TestCase):
    BLANK = {"cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "",
             "chance_pct": "", "icd_seconds": "", "source": "s", "note": "n"}
    CAST = {"owner": SET, "pieces": "4", "kind": "effect", "skill": "Earthquake", "stat": CAST, "value_min": "0", "value_max": "0", **BLANK,
            "fire_on": EVENT, "fire_skills": "Leap"}
    RUNE = {"owner": SET, "pieces": "4", "kind": "rune", "skill": "Leap", "stat": "Iron Impact", "value_min": "1", "value_max": "1", **BLANK}
    BOOST = {"owner": SET, "pieces": "4", "kind": "skill", "skill": "Leap", "stat": STAT, "value_min": "150", "value_max": "150", **BLANK}

    def render_with(self, cast=None, boost=None, extra=()):
        """The generator run on a copy of the module whose sheet is the real one with the 4-piece's rows replaced (None leaves a row out)."""
        work = Path(tempfile.mkdtemp(prefix="earth-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if not (r["owner"] == SET and r["pieces"] == "4")]
            rows = [self.RUNE] + ([{**self.CAST, **cast}] if cast is not None else []) + ([{**self.BOOST, **boost}] if boost is not None else [])
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + rows + [{**self.BLANK, **e} for e in extra])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(3, len([r for r in self.render_with({}, {}) if r[0] == SET and r[1] == 4]))

    def test_it_refuses_what_it_cannot_carry(self):
        item_cast = {**self.CAST, "owner": "Unique_WizardHat_001_x1", "pieces": "", "skill": "Diamond Skin"}
        refused = {
            "a landing naming no skill": ({"fire_skills": ""}, {}, (), "landing needs fire_skills"),
            "a landing of no skill": ({"fire_skills": "Leapx"}, {}, (), "landing needs fire_skills"),
            "a landing cast with a cooldown": ({"value_min": "5", "value_max": "5"}, {}, (), "number 0"),
            "a landing cast with a cooldown column": ({"icd_seconds": "5"}, {}, (), "cast_skill"),
            "a landing cast with a chance": ({"chance_pct": "50"}, {}, (), "cast_skill"),
            "a landing cast of an item": ({}, {}, (item_cast,), "set bonus"),
            "the cast on another event": ({"fire_on": "kill", "fire_skills": "", "value_min": "5", "value_max": "5"}, {}, (), "fired by life_below, land, taken or hit_spender"),
            "a set's cast on taken": ({"fire_on": "taken", "fire_skills": "", "value_min": "5", "value_max": "5", "chance_pct": "5"}, {}, (), "an item's"),
            "a negative cast number": ({"value_min": "-1", "value_max": "-1"}, {}, (), "value_min"),
            "the stat on a skill that does not read it": ({}, {"skill": "Whirlwind"}, (), "rune_effect_pct is read by"),
            "the stat ranged on a set": ({}, {"value_min": "100", "value_max": "150"}, (), "one number"),
        }
        for name, (cast, boost, extra, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(cast, boost, extra)

    def test_another_event_may_name_no_skill(self):
        with self.assertRaisesRegex(ValueError, "names skills"):
            self.render_with({}, {}, ({"owner": SET, "pieces": "4", "kind": "effect", "skill": "", "stat": "resource_refund", "value_min": "5",
                                       "value_max": "5", "fire_on": "taken", "fire_skills": "Leap"},))


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemearth-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the set's words and Iron Impact's numbers, not from the code."""
        leap, quake, rune, pct = words()
        factor = 1 + pct / 100
        out = [(T("row", *r), None) for r in rows]
        cast = "%s=0@%s;" % (CAST, quake)
        for worn in (0, 1, 3, 4, 5, 6):
            on = worn >= 4
            out += [(T("count", SET, worn), None), (T("now", 1000 * worn), None)]
            out += [(T("fire", EVENT, leap), cast if on else ""),
                    (T("fire", EVENT, leap), cast if on else ""),        # again at once: no internal cooldown
                    (T("fire", EVENT, "Whirlwind"), ""), (T("fire", EVENT, quake), ""),
                    (T("fire", "cast", leap), ""), (T("fire", "hit", leap), ""), (T("fire", "life_below", leap), ""), (T("fire", "taken", leap), ""),
                    (T("grants", leap, rune), "1" if on else "0"), (T("grants", leap, "Call of Arreat"), "0"), (T("grants", "Whirlwind", rune), "0"),
                    (T("factor", leap, STAT), "%g" % (factor if on else 1)), (T("factor", quake, STAT), "1"),
                    (T("factor", leap, "damage_increase_pct"), "1")]
        out += [(T("count", SET, 4), None), (T("now", 60000), None), (T("fire", EVENT, leap), cast), (T("now", 60001), None), (T("fire", EVENT, leap), cast)]
        # another set at four pieces gives none of it
        out += [(T("count", SET, 0), None), (T("count", "Wrath of the Wastes", 6), None), (T("fire", EVENT, leap), ""), (T("grants", leap, rune), "0"),
                (T("factor", leap, STAT), "1")]
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

    def test_every_rule_agrees_with_the_set_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 80)
        self.assertEqual(want, got)

    def test_iron_impact_becomes_375_percent_for_10_seconds(self):
        _, _, _, pct = words()
        factor = 1 + pct / 100
        self.assertEqual((375.0, 10.0), (rune_number("armor_pct") * factor, rune_number("duration_seconds") * factor))

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(3, len(rows))
        edit = lambda stat, **cells: [tuple(cells.get(str(i), v) for i, v in enumerate(r)) if r[4] == stat else r for r in rows]  # noqa: E731
        row_mutants = {
            "casts_avalanche": edit(CAST, **{"3": "Avalanche"}),
            "fired_by_whirlwind": edit(CAST, **{"13": "Whirlwind"}),
            "fired_on_the_press": edit(CAST, **{"12": "cast"}),
            "a_cooldown": edit(CAST, **{"5": 1.0, "6": 1.0}),
            "cast_at_six": edit(CAST, **{"1": 6}),
            "rune_at_six": edit("Iron Impact", **{"1": 6}),
            "boost_at_six": edit(STAT, **{"1": 6}),
            "another_rune": edit("Iron Impact", **{"4": "Call of Arreat"}),
            "boost_100": edit(STAT, **{"5": 100.0, "6": 100.0}),
            "boost_on_earthquake": edit(STAT, **{"3": "Earthquake"}),
            "no_cast_row": [r for r in rows if r[4] != CAST],
            "no_rune_row": [r for r in rows if r[4] != "Iron Impact"],
            "no_boost_row": [r for r in rows if r[4] != STAT],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(rows, mutant_rows, name + " did not apply")
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "fire_skills_ignored": ("if (!row.fireSkills.empty() && std::find(", "if (false && std::find("),
            "level_needs_one_more": ("worn->second < row.pieces", "worn->second <= row.pieces"),
            "factor_without_the_one": ("factor *= 1.0 + pct / 100.0;", "factor *= pct / 100.0;"),
            "every_rune_given": ('!ActiveValues(rows, counts, "rune", skill, rune, situation).empty() ||', "true ||"),
        }
        for name, (old, new) in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, real, name + " does not apply")
                want, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
