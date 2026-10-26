"""Legendary rest, bead diablocraft-7ksnv: Hexing Pants of Mr. Yan (pants, any class), N-MOVE (a moving / standing-still predicate on the player).

  "Your resource generation and damage is increased by 25% while moving and decreased by [20-25]% while standing still."
  * the text and range are read from d3planner (data.json items Unique_Pants_101_x1, leg_hexingpantsofmryan, min 20 max 25, best min) and the catalogue row; the power file
    (decode_pow.py power ItemPassive_Unique_Ring_635_x1) holds SF_0 'Buff: Resource Gen Increase' 0.25 and SF_1 'Buff: Damage Increase' 0.25; the table
    (data/legendary_powers.csv) holds TWO `player` rows for the pool item: `damage_generation_pct` 25 under the new condition `moving`, and `damage_generation_cut_pct` 20-25
    under the new condition `not_moving` (the cut is the text's positive number, rolled once per item; the lower is the better, so a Primal takes 20);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses each stat under the other
    condition, with a set level or an event, and a cut of 100 or more, and refuses `moving` and `not_moving` on anything but a player row;
  * the production rules (src/combat/dc_item_power_math.h: Holds, GenerationDamagePct, GenerationFactor, Best) are compiled and driven with the generated rows: moving, the
    additive pool gains 25 and the generation is x1.25; standing still, the pool loses the item's rolled cut and the generation is x(1 - cut/100); only while worn; two sources
    combine (the pools add, the factors multiply);
  * mutants of the rules and of the rows fail the same driver; the source guards on the readers, the additive pool and the classes' generation sites are in
    test_item_power_hexing_pants_of_mr_yan_wiring.py. The in-game steps are in docs/test-diablocraft-7ksnv.md.
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
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_hexing_pants_of_mr_yan/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Pants_101_x1"
UP, CUT = "damage_generation_pct", "damage_generation_cut_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (REPO / name if name.startswith("docs/") else MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def planner():
    """(text, min, max, best) of the pool item's power in d3planner's data.json."""
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"]), custom.get("best")


def bonus_in_text():
    return float(re.search(r"increased by (\d+)%% while moving", planner()[0])[1])


class Table(unittest.TestCase):
    def test_the_sources_say_25_moving_and_20_to_25_standing_still_lower_better(self):
        text, low, high, best = planner()
        self.assertEqual("Your resource generation and damage is increased by 25%% while moving and decreased by %d%% while standing still.", text)
        self.assertEqual((20.0, 25.0, "min"), (low, high, best))
        catalogue = [r for r in read_csv("docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Your resource generation and damage is increased by 25% while moving and decreased by [20-25]% while standing still.",
                         catalogue[0]["power_text"])

    def test_two_player_rows_hold_them(self):
        _, low, high, _ = planner()
        up = bonus_in_text()
        self.assertEqual(sorted([(OWNER, 0, "player", "", UP, up, up, "moving", *BLANK[1:]),
                                 (OWNER, 0, "player", "", CUT, low, high, "not_moving", *BLANK[1:])]), sorted(mine()))

    def test_the_sources_cite_the_power_file(self):
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == UP)
        for cited in ("SF_0 'Buff: Resource Gen Increase' = 0.25", "SF_1 'Buff: Damage Increase' = 0.25", "damage_formula.csv step 4"):
            self.assertIn(cited, row["source"])

    def test_the_damage_formula_names_the_pants_in_the_additive_pool(self):
        step = next(r for r in read_csv("data/d3/damage_formula.csv") if r["step"].startswith("4."))
        self.assertIn("Hexing Pants", step["notes_on_buckets"])


class Generator(unittest.TestCase):
    UP_ROW = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": UP, "value_min": "25", "value_max": "25", "cond": "moving",
              "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
              "icd_seconds": "", "source": "s", "note": "n"}
    CUT_ROW = {**UP_ROW, "stat": CUT, "value_min": "20", "value_max": "25", "cond": "not_moving"}

    def render_with(self, *mine_rows):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="pants-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + list(mine_rows))
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len([r for r in self.render_with(self.UP_ROW, self.CUT_ROW) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        up, cut = self.UP_ROW, self.CUT_ROW
        refused = {
            "the bonus standing still": ({**up, "cond": "not_moving"}, "under moving"),
            "the cut while moving": ({**cut, "cond": "moving"}, "under not_moving"),
            "the bonus with no condition": ({**up, "cond": ""}, "under moving"),
            "a set level": ({**up, "owner": "Immortal King's Call", "pieces": "4"}, "no set level"),
            "an event": ({**up, "fire_on": "kill"}, "moving is a player row's"),
            "a cut of a hundred": ({**cut, "value_min": "100", "value_max": "100"}, "a cut is below 100"),
            "a negative bonus": ({**up, "value_min": "-25", "value_max": "-25"}, "needs 0 < value_min <= value_max"),
            "a cond_arg": ({**up, "cond_arg": "2"}, "takes no cond_arg"),
            "cond skills": ({**up, "cond_skills": "Sprint"}, "moving is a player row's"),
            "moving on a skill row": ({**up, "kind": "skill", "skill": "Frenzy", "stat": "damage_increase_pct"}, "moving is a player row's"),
            "not_moving on a skill row": ({**cut, "kind": "skill", "skill": "Frenzy", "stat": "damage_increase_pct", "value_min": "5", "value_max": "5"},
                                          "not_moving is a player row's"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(edit)

    def test_another_player_number_may_move_too(self):
        # the conditions are not the pants': a later bead's number under them is one row of the same kind (Endless Walk's set levels)
        rows = self.render_with(self.UP_ROW, self.CUT_ROW, {**self.UP_ROW, "stat": "damage_taken_pct", "value_min": "-25", "value_max": "-25", "cond": "moving"})
        self.assertEqual(3, len([r for r in rows if r[0] == OWNER]))


class Rules(unittest.TestCase):
    OTHER = ("Other Pants", 0, "player", "", CUT, 1.0, 50.0, "not_moving", *BLANK[1:])    # a second source: the driver sets its stored roll
    ODD = ("Odd Pants", 0, "player", "", "damage_dealt_pct", 30.0, 30.0, "moving", *BLANK[1:])   # another stat under the same condition: not the pants'
    MORE = ("More Pants", 0, "player", "", UP, 10.0, 10.0, "moving", *BLANK[1:])      # a second bonus source: the factors multiply, the pools add
    WHOLE = ("Whole Pants", 0, "player", "", CUT, 100.0, 100.0, "not_moving", *BLANK[1:])   # a cut the generator refuses, which the rule still must not turn into "nothing is paid"

    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itempants-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        _, low, high, _ = planner()
        up = bonus_in_text()
        out = [(T("row", *r), None) for r in rows + [self.OTHER, self.ODD, self.MORE, self.WHOLE]]
        clear = (T("clear"), None)
        wear = lambda roll, moving: [clear, (T("wears", OWNER), None), (T("stored", OWNER, CUT, roll), None), (T("moving", moving), None)]  # noqa: E731
        # not worn: nothing, moving or not, even with the roll known
        out += [clear, (T("damage"), "0"), (T("gen"), "1"), (T("moving", 1), None), (T("damage"), "0"), (T("gen"), "1"),
                (T("stored", OWNER, CUT, low), None), (T("moving", 0), None), (T("damage"), "0"), (T("gen"), "1")]
        # moving: +25 in the pool, x1.25 on the generation, whatever the roll
        for roll in (low, 22.5, high):
            out += wear(roll, 1) + [(T("damage"), g(up)), (T("gen"), g(1 + up / 100))]
        # standing still: the roll comes off the pool and off the generation
        for roll in (low, 22.5, high):
            out += wear(roll, 0) + [(T("damage"), g(-roll)), (T("gen"), g(1 - roll / 100))]
        # the conditions
        out += wear(low, 1) + [(T("holds", 0), "1"), (T("holds", 1), "0")]
        out += wear(low, 0) + [(T("holds", 0), "0"), (T("holds", 1), "1")]
        # a second source combines: pools add, factors multiply (standing still, 22.5 and 10)
        out += wear(22.5, 0) + [(T("wears", "Other Pants"), None), (T("stored", "Other Pants", CUT, 10), None),
                                (T("damage"), g(-32.5)), (T("gen"), g((1 - 0.225) * 0.9))]
        # two bonus sources while moving: the pools add (25 + 10), the factors multiply (1.25 x 1.1)
        out += wear(low, 1) + [(T("wears", "More Pants"), None), (T("damage"), g(35)), (T("gen"), g(1.25 * 1.1))]
        # a cut of a hundred is no cut the rule carries: the pool still loses it, the generation keeps its factor
        out += [clear, (T("wears", "Whole Pants"), None), (T("moving", 0), None), (T("damage"), "-100"), (T("gen"), "1")]
        # another stat under the same condition is not the pants'
        out += [clear, (T("wears", "Odd Pants"), None), (T("moving", 1), None), (T("damage"), "0"), (T("gen"), "1")]
        # a Primal stores the better end: the top of the bonus, the bottom of the cut
        out += [(T("best", 0), g(up)), (T("best", 1), g(low))]
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
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(real, rows, "want")
        up = [r for r in rows if r[4] == UP]
        cut = [r for r in rows if r[4] == CUT]
        row_mutants = {
            "the_conditions_swapped": [r[:7] + ("not_moving",) + r[8:] for r in up] + [r[:7] + ("moving",) + r[8:] for r in cut],
            "the_bonus_always": [r[:7] + ("",) + r[8:] for r in up] + cut,
            "the_cut_always": up + [r[:7] + ("",) + r[8:] for r in cut],
            "the_bonus_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in up] + cut,
            "the_cut_range_fixed_at_the_top": up + [r[:5] + (r[6], r[6]) + r[7:] for r in cut],
            "the_wrong_owner": [("Other Pants",) + r[1:] for r in rows],
            "no_bonus": cut,
            "no_cut": up,
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")

        def body(name):
            text = real[real.index("inline double %s(" % name):]
            return text[:text.index("\n    }\n") + 7]
        pool, factor = body("GenerationDamagePct"), body("GenerationFactor")
        rules = {
            "the_cut_added": (pool, '- PlayerSum(rows, counts, "damage_generation_cut_pct", situation)', '+ PlayerSum(rows, counts, "damage_generation_cut_pct", situation)'),
            "the_bonus_dropped": (pool, 'PlayerSum(rows, counts, "damage_generation_pct", situation) -', "0.0 -"),
            "the_cut_dropped": (pool, '- PlayerSum(rows, counts, "damage_generation_cut_pct", situation)', ""),
            "the_bonus_stat_wrong": (pool, '"damage_generation_pct"', '"damage_generation_cut_pct"'),
            "the_bonus_added_not_multiplied": (factor, "factor *= 1.0 + pct / 100.0;", "factor += pct / 100.0;"),
            "the_cut_a_raise": (factor, "factor *= 1.0 - pct / 100.0;", "factor *= 1.0 + pct / 100.0;"),
            "the_cut_a_fraction": (factor, "factor *= 1.0 - pct / 100.0;", "factor *= 1.0 - pct;"),
            "a_hundred_takes_all": (factor, "if (pct > 0 && pct < 100)", ""),
            "the_cut_stat_wrong": (factor, '"damage_generation_cut_pct"', '"damage_generation_pct"'),
        }
        for name, (where, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, where, name + " does not apply")
                _, got = self.drive(real.replace(where, where.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "moving_never": real.replace("            return situation.moving;\n", "            return false;\n"),
            "not_moving_never": real.replace("            return !situation.moving;\n", "            return false;\n"),
            "moving_always": real.replace("            return situation.moving;\n", "            return true;\n"),
            "not_moving_as_moving": real.replace("            return !situation.moving;\n", "            return situation.moving;\n"),
            "the_cut_best_is_the_top": real.replace('row.stat == "resource_threshold_pct" || row.stat == "damage_generation_cut_pct" ? row.min : row.max',
                                                    'row.stat == "resource_threshold_pct" ? row.min : row.max'),
            "the_cut_best_is_the_middle": real.replace('row.stat == "resource_threshold_pct" || row.stat == "damage_generation_cut_pct" ? row.min : row.max',
                                                       'row.stat == "resource_threshold_pct" || row.stat == "damage_generation_cut_pct" ? (row.min + row.max) / 2 : row.max'),
            "the_bottom_not_the_roll": real.replace("number = found->value;", "number = row.min;"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
