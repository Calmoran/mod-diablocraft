"""Legendary rest, bead diablocraft-14cp4: the Immortal King's Call 6-piece bonus (Barbarian set).

  "While both Wrath of the Berserker and Call of the Ancients are active, you deal 4000% increased damage."
  * the words and the number are read apart from the table out of d3planner (data.json itemSets immortalking, the catalogue's source rule for
    set bonuses: the current text) and the set sheet (barbarian_sets.csv, the same on all seven pieces); the table (data/legendary_powers.csv)
    holds ONE `player` `damage_dealt_pct` row at pieces 6, 4000, under the condition `skills_active` over the two skills the text names (the
    model is Remorseless' row), each of them a skill of barbarian_skills.csv; the 2- and 4-piece bonuses are other beads' and have no row here;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: CountSets, BonusActive, Owned, Holds, PlayerFactor) are compiled and driven with the
    generated row and the set's real pieces: the multiplier is 1 + 4000/100 = 41 from the 6th distinct piece and only while BOTH skills are
    on (Wrath alone, the Ancients alone and neither give 1), two copies of a piece count once, a seventh piece changes nothing, and
    no other stat, no skill row and another set take nothing from it;
  * mutants fail the same driver (the number, the level, the stat, the condition lost, only one skill named; the condition read as "any",
    the level off by one, duplicates counted, the multiplier without its one);
  * source-text guards that the hit's legendary term multiplies the player's DealtFactor in, and that the watched skills are read live
    (the C++ is compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-14cp4.md).
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
import barbarian_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_counter/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
NUMBER = GENERATED.stem.split("_")[2]
SET = "Immortal King's Call"
STAT = "damage_dealt_pct"
ROW = re.compile(r"\('((?:[^']|'')*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
TEXT = re.compile(r"While both ([\w' ]+?) and ([\w' ]+?) are active, you deal (\d+)%+ increased damage\.")


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def planner_text():
    """The 6-piece bonus in d3planner's data.json, the current text (the catalogue's source rule for set bonuses)."""
    data = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))
    sets = [s for s in data["itemSets"].values() if s["name"] == SET]
    assert len(sets) == 1
    lines = sets[0]["bonuses"]["6"]
    assert len(lines) == 1
    return lines[0]["format"]


def sheet_text():
    """The same bonus in the set sheet: one text on all seven pieces."""
    texts = {r["bonus_6pc"] for r in read_csv("data/d3/barbarian_sets.csv") if r["set_name"] == SET}
    assert len(texts) == 1, texts
    return texts.pop()


def numbers():
    """([the two skills], the percent) the current text names, read apart from the table; the sheet must say the same."""
    m = TEXT.fullmatch(planner_text())
    assert m, planner_text()
    s = TEXT.fullmatch(sheet_text())
    assert s and s.groups() == m.groups(), sheet_text()
    return [m[1], m[2]], float(m[3])


def pieces():
    return [r["d3_name"] for r in read_csv("data/d3/base_items.csv") if r["set_name"] == SET and r["pool_version"] == "yes"]


def generated_rows(text=None):
    text = GENERATED.read_text(encoding="utf-8") if text is None else text
    return [(m[1].replace("''", "'"), int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(text)]


def mine(rows=None):
    return [r for r in (generated_rows() if rows is None else rows) if r[0] == SET and r[1] == 6]   # the 2- and 4-piece are the set bead xf9oy's (test_item_power_immortal_kings_call_set.py)


class Table(unittest.TestCase):
    def test_the_sources_name_the_two_skills_and_the_number(self):
        skills, pct = numbers()
        self.assertEqual(["Wrath of the Berserker", "Call of the Ancients"], skills)
        self.assertEqual(4000.0, pct)
        sheet = {r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")}
        for skill in skills:
            self.assertIn(skill, sheet)

    def test_one_player_row_at_six_pieces_under_skills_active(self):
        skills, pct = numbers()
        self.assertEqual([(SET, 6, "player", "", STAT, pct, pct, "skills_active", 0.0, ";".join(skills), 0.0, 0, "", "", 100.0, 0.0)], mine())

    def test_the_owner_is_a_seven_piece_set_whose_pieces_drop(self):
        rows = [r for r in read_csv("data/d3/base_items.csv") if r["set_name"] == SET]
        self.assertEqual(7, len(rows))
        self.assertEqual(7, len(pieces()))
        self.assertTrue(all(r["pool_version"] == "yes" and r["craft_only"] == "no" for r in rows))

    def test_the_row_has_its_source_and_a_note(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == SET and r["pieces"] == "6"]
        self.assertEqual(1, len(rows))
        self.assertIn("data.json", rows[0]["source"])
        self.assertIn("4000%", rows[0]["source"])
        self.assertIn("barbarian_sets.csv", rows[0]["source"])
        self.assertTrue(rows[0]["note"])

    def test_the_newest_table_is_not_yet_shipped(self):
        self.assertNotIn("legendary_powers_%s_table.sql" % NUMBER, (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemikc-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the text's words and number, not from the code."""
        (wrath, call), pct = numbers()
        factor = 1 + pct / 100
        names = pieces()
        out = [(T("row", r[0], r[1], r[2], r[3], r[4], g(r[5]), g(r[6]), r[7], g(r[8]), r[9]), None) for r in rows]
        states = {"neither": [], "wrath only": [wrath], "call only": [call], "both": [wrath, call], "both and another": [wrath, call, "Whirlwind"],
                  "others only": ["Whirlwind", "Frenzy"]}
        for worn in range(0, 9):
            for label, on in states.items():
                want = factor if worn >= 6 and "both" in label else 1
                out += [(T("clear"), None)] + [(T("skillon", s), None) for s in on] + [(T("player", STAT, 1, SET, worn), g(want))]
            out += [(T("clear"), None), (T("active", SET, 6, worn), "1" if worn >= 6 else "0")]
            # the 2- and 4-piece levels have no row in this bead: never active
            out += [(T("active", SET, 4, worn), "0"), (T("active", SET, 2, worn), "0")]
        both = [(T("clear"), None), (T("skillon", wrath), None), (T("skillon", call), None)]
        # no other stat of the player and no skill row takes it
        for stat in ("damage_taken_pct", "damage_reduction_pct", "pet_attack_speed_pct", "shield_potency_pct", "deaths_breath_pct"):
            out += both + [(T("player", stat, 1, SET, 7), "1")]
        out += both + [(T("factor", "Whirlwind", "damage_increase_pct", 1, SET, 7), "1"),
                       (T("factor", "Hammer of the Ancients", "damage_increase_pct", 1, SET, 7), "1"),
                       (T("factor", wrath, STAT, 1, SET, 7), "1")]
        # another set's pieces do not count, the same set's later piece changes nothing
        out += both + [(T("player", STAT, 1, "Other Set", 6), "1"), (T("player", STAT, 2, SET, 5, "Other Set", 6), "1"),
                       (T("player", STAT, 2, SET, 6, "Other Set", 6), g(factor)), (T("player", STAT, 1, SET, 7), g(factor))]
        # the real pieces, counted: six distinct names are 6, two copies of one are one, seven are 7
        out += [(T("count", len(names), *[x for p in names for x in (SET, p)]), "%s=7;" % SET)]
        out += [(T("count", 6, *[x for p in names[:6] for x in (SET, p)]), "%s=6;" % SET)]
        out += [(T("count", 7, *[x for p in names[:6] + names[:1] for x in (SET, p)]), "%s=6;" % SET)]
        out += [(T("count", 6, *[x for p in names[:5] + names[:1] for x in (SET, p)]), "%s=5;" % SET)]
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

    def test_every_rule_agrees_with_the_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 90)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        r = rows[0]
        row_mutants = {
            "no_rows": [],
            "the_number_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:]],
            "the_level_is_four": [(r[0], 4) + r[2:]],
            "the_stat_is_taken": [r[:4] + ("damage_taken_pct",) + r[5:]],
            "the_condition_lost": [r[:7] + ("", 0.0, "") + r[10:]],
            "only_wrath_named": [r[:9] + ("Wrath of the Berserker",) + r[10:]],
            "only_the_ancients_named": [r[:9] + ("Call of the Ancients",) + r[10:]],
            "a_skill_row_instead": [r[:2] + ("skill", "Whirlwind", "damage_increase_pct") + r[5:]],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "any_skill_is_enough": real.replace("return !row.condSkills.empty() && std::all_of(", "return !row.condSkills.empty() && std::any_of("),
            "level_needs_one_more": real.replace("if (worn < pieces || !pieces)", "if (worn <= pieces || !pieces)"),
            "a_set_row_needs_fewer": real.replace("worn->second < row.pieces", "worn->second + 1 < row.pieces"),
            "duplicates_count": real.replace("names[piece.set].insert(piece.name);", "names[piece.set].insert(piece.name + std::to_string(names[piece.set].size()));"),
            "the_factor_drops_the_one": real.replace(
                'ActiveValues(rows, counts, "player", "", stat, situation))\n            factor *= 1.0 + pct / 100.0;',
                'ActiveValues(rows, counts, "player", "", stat, situation))\n            factor *= pct / 100.0;'),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%g" % x  # noqa: E731

if __name__ == "__main__":
    unittest.main()
