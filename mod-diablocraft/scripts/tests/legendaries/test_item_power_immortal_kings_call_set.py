"""Legendary rest, set bead diablocraft-xf9oy: Immortal King's Call 2- and 4-piece (Barbarian set, 7 pieces that drop), built whole beside the 6-piece. It builds
N-SPENT (a row fired per N points of the resource spent) and N-CDNAMED (a cooldown cut of the skills a row names) and uses the N-DUR family for the 2-piece.

  2-piece: "Call of the Ancients last until they die."
  4-piece: "Reduce the cooldown of Wrath of the Berserker and Call of the Ancients by 3 seconds for every 10 Fury you spend with an attack."
  * the words and numbers (3 seconds, 10 Fury) are read from d3planner (data_itemsets.js, immortalking) and the sets sheet (barbarian_sets.csv), apart from
    the table; the table (data/legendary_powers.csv) holds ONE row for the 2-piece (`skill` Call of the Ancients `lasts_until_death` 1) and ONE for the 4-piece
    (`effect` `cooldown_cut_named_seconds` 3 over both skills, condition `per_resource_spent` 10, fired on `resource_spent`), each its own row of the set;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts both
    rows and refuses what the code cannot carry (a step of zero or a fraction, a skill that is no skill, a cut on another event, a flag with another number);
  * the production rule (src/combat/dc_item_power_math.h: SpentFires with Owned, and SkillSetTo) is compiled and driven with the generated rows: the cut is 3 s
    per whole 10 points, the rest of a step is carried to the next spend (25 pays 2 steps and keeps 5), nothing below the 4th distinct piece and nothing
    carried while it is not worn, the named skills as the row words them; the flag is 1 for Call of the Ancients from the 2nd piece only;
  * mutants of the rules and of the rows fail the same driver;
  * source-text guards: Abilities::Spent reports to ItemPowers::Spent, which reads the situation before the lock, carries per row and cuts each named skill's
    cooldown in milliseconds outside the lock; the Ancients are summoned with TEMPSUMMON_DEAD_DESPAWN (no timer) when the flag is read, before the lock of
    their file. The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-xf9oy.md.
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
import barbarian_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_immortal_kings_call_set/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SET = "Immortal King's Call"
CALL = "Call of the Ancients"
WRATH = "Wrath of the Berserker"
ROW = re.compile(r"\('((?:[^']|'')*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1].replace("''", "'"), int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13],
             m[14], float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None, pieces=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == SET and r[1] in ((2, 4) if pieces is None else pieces)]


def planner():
    """The set's two bonus texts as the planner words them."""
    text = (REPO / "reference/d3planner/data_itemsets.js").read_text(encoding="utf-8")
    start = text.index('name: "%s"' % SET)
    block = text[start:text.index("  earth: {", start)]
    two = re.search(r'"2": \[\s*\{format: "([^"]*)"', block)[1]
    four = re.search(r'"4": \[\s*\{format: "([^"]*)"', block)[1]
    return two, four


class Table(unittest.TestCase):
    def test_the_sources_word_both_bonuses_and_the_numbers(self):
        two, four = planner()
        self.assertEqual("Call of the Ancients last until they die.", two)
        m = re.fullmatch(r"Reduce the cooldown of (.*) and (.*) by (\d+) seconds for every (\d+) Fury you spend with an attack\.", four)
        self.assertTrue(m, four)
        self.assertEqual((WRATH, CALL, "3", "10"), tuple(m.groups()))
        sheet = [r for r in read_csv("data/d3/barbarian_sets.csv") if r["set_name"] == SET]
        self.assertEqual({(two, four)}, {(r["bonus_2pc"], r["bonus_4pc"]) for r in sheet})

    def test_the_two_rows_are_the_sets_two_and_four_piece(self):
        rows = mine()
        self.assertEqual([(SET, 2, "skill", CALL, "lasts_until_death", 1.0, 1.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
                          (SET, 4, "effect", "%s;%s" % (WRATH, CALL), "cooldown_cut_named_seconds", 3.0, 3.0, "per_resource_spent", 10.0, "", 0.0, 0,
                           "resource_spent", "", 100.0, 0.0)], rows)

    def test_the_numbers_are_the_planners(self):
        _, four = planner()
        seconds, step = re.search(r"by (\d+) seconds for every (\d+) Fury", four).groups()
        row = mine(pieces=(4,))[0]
        self.assertEqual((float(seconds), float(step)), (row[5], row[8]))

    def test_the_six_piece_is_untouched_and_the_set_is_whole(self):
        levels = sorted(r[1] for r in all_rows() if r[0] == SET)
        self.assertEqual([2, 4, 6], levels)

    def test_the_owner_is_the_barbarian_set_that_drops(self):
        pieces = [r for r in read_csv("data/d3/base_items.csv") if r["set_name"] == SET]
        self.assertEqual(7, len(pieces))
        self.assertTrue(all(r["pool_version"] == "yes" and r["craft_only"] == "no" for r in pieces))

    def test_the_rows_have_their_sources_and_notes(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == SET and r["pieces"] in ("2", "4")]
        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertIn("data_itemsets.js:430", row["source"])
            self.assertTrue(row["note"])


class Generator(unittest.TestCase):
    TWO = {"owner": SET, "pieces": "2", "kind": "skill", "skill": CALL, "stat": "lasts_until_death", "value_min": "1", "value_max": "1", "cond": "",
           "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
           "icd_seconds": "", "source": "s", "note": "n"}
    FOUR = {**TWO, "pieces": "4", "kind": "effect", "skill": "%s;%s" % (WRATH, CALL), "stat": "cooldown_cut_named_seconds", "value_min": "3",
            "value_max": "3", "cond": "per_resource_spent", "cond_arg": "10", "fire_on": "resource_spent"}

    def render_with(self, two, four):
        work = Path(tempfile.mkdtemp(prefix="ikc-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if not (r["owner"] == SET and r["pieces"] in ("2", "4"))]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.TWO, **two}, {**self.FOUR, **four}])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len([r for r in self.render_with({}, {}) if r[0] == SET and r[1] in (2, 4)]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a flag of 2": ({"value_min": "2", "value_max": "2"}, {}, "lasts_until_death"),
            "a flag that rolls": ({"value_min": "1", "value_max": "2"}, {}, "set bonus is one number|lasts_until_death"),
            "a flag for another skill": ({"skill": "Wrath of the Berserker"}, {}, "lasts_until_death"),
            "a flag with a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": CALL}, {}, "lasts_until_death"),
            "a step of zero": ({}, {"cond_arg": "0"}, "needs cond_arg > 0"),
            "a fractional step": ({}, {"cond_arg": "7.5"}, "whole cond_arg"),
            "no step": ({}, {"cond": "", "cond_arg": ""}, "per_resource_spent"),
            "the step on the wrong stat": ({}, {"stat": "cooldown_cut_seconds", "skill": ""}, "resource_spent"),
            "a cut on another event": ({}, {"fire_on": "hit_spender"}, "per_resource_spent|resource_spent"),
            "a skill that is none": ({}, {"skill": "%s;Nonsense" % WRATH}, "named cooldown cut"),
            "a cut that rolls": ({}, {"value_max": "4"}, "named cooldown cut|set bonus is one number"),
            "a negative cut": ({}, {"value_min": "-3", "value_max": "-3"}, "needs 0 < value_min"),
            "skills named by the condition": ({}, {"cond_skills": WRATH}, "per_resource_spent"),
        }
        for name, (two, four, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(two, four)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemikc-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        out = [(T("row", *r), None) for r in rows]
        both = "%s;%s" % (WRATH, CALL)
        cut = lambda n: "cooldown_cut_named_seconds=%g:%s;" % (n, both)  # noqa: E731
        worn = lambda n: [(T("clear"), None), (T("set", SET, n), None)]  # noqa: E731
        # the 4-piece: 3 s for a whole 10
        out += worn(4) + [(T("spent", 10), cut(3)), (T("spent", 20), cut(6)), (T("spent", 30), cut(9))]
        # less than a step pays nothing and is kept: 5 + 5 pays one
        out += worn(4) + [(T("spent", 5), ""), (T("spent", 5), cut(3)), (T("spent", 9.5), ""), (T("spent", 0.5), cut(3))]
        # 25 pays two steps and keeps 5; 5 more pays the third
        out += worn(4) + [(T("spent", 25), cut(6)), (T("spent", 5), cut(3)), (T("spent", 4), ""), (T("spent", 6), cut(3))]
        # a big spend pays every step at once
        out += worn(4) + [(T("spent", 100), cut(30))]
        # nothing or less than nothing spent: nothing fires and nothing is kept (a negative never turns into points)
        out += worn(4) + [(T("spent", 0), ""), (T("spent", -10), ""), (T("spent", 9), ""), (T("spent", 1), cut(3))]
        out += worn(4) + [(T("spent", -5), ""), (T("spent", 5), ""), (T("spent", 5), cut(3))]
        # fewer than four distinct pieces: nothing, and no points carried for later
        for n in (0, 1, 2, 3):
            out += worn(n) + [(T("spent", 100), ""), (T("set", SET, 4), None), (T("spent", 5), ""), (T("spent", 5), cut(3))]
        # five and six and seven pieces are the four-piece too
        for n in (5, 6, 7):
            out += worn(n) + [(T("spent", 10), cut(3))]
        # another set's pieces do not count
        out += worn(0) + [(T("set", "Other Set", 6), None), (T("spent", 100), "")]
        # the 2-piece: the flag is 1 for Call of the Ancients from the 2nd piece, never for another skill
        for n, want in ((0, "0"), (1, "0"), (2, "1"), (3, "1"), (4, "1"), (6, "1")):
            out += worn(n) + [(T("until", CALL), want)]
        for other in (WRATH, "Ignore Pain", "Call of the Ancient", "Call of the Ancients ", ""):
            out += worn(6) + [(T("until", other), "0")]
        return out

    def apart(self, rows):
        """Rows the sheet does not hold, in the same table: two rows of one set carry their own points, only an effect row is fired, an item's row needs the item, another event or a step of nothing never fire it."""
        two_steps = (SET, 4, "effect", "Ignore Pain", "cooldown_cut_named_seconds", 1.0, 1.0, "per_resource_spent", 7.0, "", 0.0, 0, "resource_spent", "", 100.0, 0.0)
        not_effect = (SET, 4, "player", "", "damage_dealt_pct", 50.0, 50.0, "per_resource_spent", 10.0, "", 0.0, 0, "resource_spent", "", 100.0, 0.0)
        item = ("Some_Belt", 0, "effect", "Sprint", "cooldown_cut_named_seconds", 2.0, 2.0, "per_resource_spent", 10.0, "", 0.0, 0, "resource_spent", "", 100.0, 0.0)
        other_event = (SET, 4, "effect", "Sprint", "cooldown_cut_named_seconds", 5.0, 5.0, "per_resource_spent", 10.0, "", 0.0, 0, "hit_spender", "", 100.0, 0.0)
        no_step = (SET, 4, "effect", "War Cry", "cooldown_cut_named_seconds", 5.0, 5.0, "per_resource_spent", 0.0, "", 0.0, 0, "resource_spent", "", 100.0, 0.0)
        out = [(T("row", *r), None) for r in rows + [two_steps, not_effect, item, other_event, no_step]]
        both = "cooldown_cut_named_seconds=3:%s;%s;" % (WRATH, CALL)
        ones = "cooldown_cut_named_seconds=%g:Ignore Pain;"
        out += [(T("clear"), None), (T("set", SET, 4), None), (T("spent", 7), ones % 1), (T("spent", 3), both), (T("spent", 4), ones % 1),
                (T("spent", 10), both + ones % 1)]
        out += [(T("clear"), None), (T("set", SET, 4), None), (T("spent", 10), both + ones % 1)]
        # the item's row: not worn, nothing and no points kept; worn, 2 s a whole 10
        out += [(T("clear"), None), (T("spent", 50), ""), (T("wears", "Some_Belt"), None), (T("spent", 5), ""), (T("spent", 5), "cooldown_cut_named_seconds=2:Sprint;")]
        return out

    def drive(self, header_text, rows, name, cases=None):
        cases = self.cases(rows) if cases is None else cases
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
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_rows_of_one_set_carry_apart_and_only_effects_fire(self):
        rows = mine()
        want, got = self.drive(MATH.read_text(encoding="utf-8"), rows, "apart", self.apart(rows))
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        two, four = rows
        row_mutants = {
            "the_skill_lost": [two[:3] + ("Ignore Pain",) + two[4:], four],
            "the_flag_removed": [four],
            "the_cut_dropped": [two],
            "a_step_of_twenty": [two, four[:8] + (20.0,) + four[9:]],
            "a_cut_of_one": [two, four[:5] + (1.0, 1.0) + four[7:]],
            "only_wrath_named": [two, four[:3] + (WRATH,) + four[4:]],
            "a_six_piece_cut": [two, (four[0], 6) + four[2:]],
            "the_wrong_event": [two, four[:12] + ("hit_spender",) + four[13:]],
        }
        want, _ = self.drive(real, rows, "want")
        apart, _ = self.drive(real, rows, "apart", self.apart(rows))
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("// N-SPENT (Immortal King's Call"):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "no_event_check": ('row.fireOn != "resource_spent"', 'false'),
            "not_owned_still_fires": ("|| !Owned(row, counts, situation, number)", ""),
            "no_step_check": ("row.arg <= 0 || ", ""),
            "the_remainder_dropped": ("held -= steps * row.arg;", ""),
            "a_step_rounded_up": ("std::floor(held / row.arg)", "std::ceil(held / row.arg)"),
            "one_step_whatever_was_spent": ("number * steps", "number"),
            "a_zero_step_still_fires": ("if (steps >= 1)", "if (steps >= 0)"),
            "negative_spend_counts": ("if (spent <= 0)\n            return out;", ""),
            "spend_not_added": ("held += spent;", "held = spent;"),
            "shared_carry": ("carry[FireKey(row)]", "carry[row.owner]"),
            "any_effect_stat": ('row.kind != "effect" || ', ""),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                mutant = real.replace(body, body.replace(old, new, 1))
                _, got = self.drive(mutant, rows, name)
                _, got_apart = self.drive(mutant, rows, name + "-apart", self.apart(rows))
                self.assertTrue(want != got or apart != got_apart, name + " survived")
        header_mutants = {
            "the_pieces_ignored": real.replace("worn->second < row.pieces", "false"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                _, got_apart = self.drive(header, rows, name + "-apart", self.apart(rows))
                self.assertTrue(want != got or apart != got_apart, name + " survived")


if __name__ == "__main__":
    unittest.main()
