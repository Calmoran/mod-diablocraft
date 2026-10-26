"""Legendary rest, bead diablocraft-lqe1r: Ancient Parthan Defenders (bracers, any class), N-TCTRL (a count of enemies in a control state within a range).

  "Each stunned enemy within 25 yards reduces your damage taken by [9-12]%."
  * the text and range are read from d3planner (data.json items Unique_Bracer_102_x1, leg_ancientparthandefenders, min 9 max 12) and the catalogue row; the 25 yards
    are the power file's SF_0 'Check Radius' (decode_pow.py power ItemPassive_Unique_Ring_588_x1) and the item's text; the table (data/legendary_powers.csv) holds THREE
    `player` rows for the pool item: `damage_reduction_per_stunned_pct` 9-12 (rolled once per item), and the two fixed numbers beside it, `stunned_radius_yards` 25 and
    `stunned_check_seconds` 0.25 (the designer's standing default for a trigger check: the power file gives no cadence);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses the stat with a
    set level, a condition, an event, a number of 100 or more, or without the two fixed rows, and refuses the fixed rows without it, rolled, or with a condition;
  * the production rules (src/combat/dc_item_power_math.h: StunnedReduction, ScanDue, StunAura) are compiled and driven with the generated rows: the damage taken is
    (1 - N/100) to the power of the stunned enemies, a multiplier of its own for each, with the item's stored roll, only while worn, and 1 with none stunned; a look is due
    after the cadence, a freeze is no stun;
  * mutants of the rules and of the rows fail the same driver; the source guards on the server side are in test_item_power_ancient_parthan_defenders_wiring.py.
    The in-game steps are in docs/test-diablocraft-lqe1r.md.
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
HARNESS = MODULE / "tests/item_power_ancient_parthan_defenders/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Bracer_102_x1"
CUT, RADIUS, EVERY = "damage_reduction_per_stunned_pct", "stunned_radius_yards", "stunned_check_seconds"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731
FREEZE_HOLD = 15878   # stock "Ice Blast", Torment's freeze hold: mechanic Stun on the record


def read_csv(name):
    with (REPO / name if name.startswith("docs/") else MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def planner():
    """(text, min, max) of the pool item's power in d3planner's data.json."""
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


def yards_in_text():
    return float(re.search(r"within (\d+) yards", planner()[0])[1])


class Table(unittest.TestCase):
    def test_the_sources_say_9_to_12_per_stunned_enemy_within_25_yards(self):
        text, low, high = planner()
        self.assertEqual("Each stunned enemy within 25 yards reduces your damage taken by %d%%.", text)
        self.assertEqual((9.0, 12.0), (low, high))
        catalogue = [r for r in read_csv("docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Each stunned enemy within 25 yards reduces your damage taken by [9-12]%.", catalogue[0]["power_text"])

    def test_three_player_rows_hold_the_numbers(self):
        _, low, high = planner()
        every = 0.25
        self.assertEqual(sorted([(OWNER, 0, "player", "", CUT, low, high, *BLANK),
                                 (OWNER, 0, "player", "", RADIUS, yards_in_text(), yards_in_text(), *BLANK),
                                 (OWNER, 0, "player", "", EVERY, every, every, *BLANK)]), sorted(mine()))

    def test_the_cadence_names_the_standing_default(self):
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == EVERY)
        self.assertIn("standing default", row["source"])
        self.assertIn("0.25 s", row["source"])
        radius = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == RADIUS)
        self.assertIn("SF_0 'Check Radius' = 25", radius["source"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        if m:   # the item side is Items'; when the tooltip row is there it carries the text
            self.assertIn("stunned enemy within 25 yards", m[1])


class Generator(unittest.TestCase):
    CUT_ROW = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": CUT, "value_min": "9", "value_max": "12", "cond": "",
               "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
               "icd_seconds": "", "source": "s", "note": "n"}
    RADIUS_ROW = {**CUT_ROW, "stat": RADIUS, "value_min": "25", "value_max": "25"}
    EVERY_ROW = {**CUT_ROW, "stat": EVERY, "value_min": "0.25", "value_max": "0.25"}

    def render_with(self, *mine_rows):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="parthan-gen-", dir=str(SCRATCH)))
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
        rows = [r for r in self.render_with(self.CUT_ROW, self.RADIUS_ROW, self.EVERY_ROW) if r[0] == OWNER]
        self.assertEqual(3, len(rows))

    def test_it_refuses_what_it_cannot_carry(self):
        cut, radius, every = self.CUT_ROW, self.RADIUS_ROW, self.EVERY_ROW
        refused = {
            "a set level": ([{**cut, "owner": "Immortal King's Call", "pieces": "4", "value_min": "9", "value_max": "9"}, radius, every], "no set level"),
            "a condition": ([{**cut, "cond": "quiet_stacks", "cond_arg": "2", "stack_seconds": "1", "stack_max": "2"}, radius, every], "simply on"),
            "an event": ([{**cut, "fire_on": "kill"}, radius, every], "an event fires an effect row"),
            "a hundred percent": ([{**cut, "value_min": "100", "value_max": "100"}, radius, every], "percent below 100"),
            "a negative number": ([{**cut, "value_min": "-12", "value_max": "-9"}, radius, every], "needs 0 < value_min <= value_max"),
            "no radius": ([cut, every], "needs the item's fixed player rows"),
            "no cadence": ([cut, radius], "needs the item's fixed player rows"),
            "a rolled radius": ([cut, {**radius, "value_min": "20"}, every], "needs the item's fixed player rows"),
            "a radius under a condition": ([cut, {**radius, "cond": "standing_still", "stack_seconds": "1", "stack_max": "1"}, every],
                                           "needs the item's fixed player rows"),
            "a cadence with an event": ([cut, radius, {**every, "fire_on": "kill"}], "needs the item's fixed player rows"),
            "a cadence with a set level": ([cut, radius, every, {**every, "owner": "Immortal King's Call", "pieces": "4"}], "one fixed number"),
            "the fixed rows alone": ([radius, every], "beside the damage_reduction_per_stunned_pct row"),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(*edit)


class Rules(unittest.TestCase):
    OTHER = ("Other Bracers", 0, "player", "", CUT, 1.0, 50.0, *BLANK)     # a ranged row: the driver sets its stored roll
    ODD = ("Odd Bracers", 0, "player", "", "damage_reduction_pct", 30.0, 30.0, *BLANK)   # another stat: not the stunned reduction
    ALL = ("Whole Bracers", 0, "player", "", CUT, 100.0, 100.0, *BLANK)    # a number the generator refuses, which the rule still must not turn into "nothing is taken"

    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemparthan-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        _, low, high = planner()
        out = [(T("row", *r), None) for r in rows + [self.OTHER, self.ODD, self.ALL]]
        clear = (T("clear"), None)
        wear = lambda roll: [clear, (T("wears", OWNER, 0), None), (T("stored", OWNER, CUT, roll), None)]  # noqa: E731
        # not worn: nothing, however many are stunned, even with the roll known
        out += [clear, (T("stunned", 4), None), (T("factor"), "1"), (T("stored", OWNER, CUT, low), None), (T("factor"), "1")]
        # the fixed numbers read while worn, none when not
        out += [(T("sum", RADIUS), "0"), (T("sum", EVERY), "0")]
        out += wear(low) + [(T("sum", RADIUS), g(yards_in_text())), (T("sum", EVERY), "0.25")]
        # worn, each end of the roll: none stunned = 1; each stunned enemy is a multiplier of its own
        for roll in (low, high):
            out += wear(roll)
            for n in (0, 1, 2, 5, 9, 20):
                out += [(T("stunned", n), None), (T("factor"), g((1 - roll / 100) ** n))]
        # a second source multiplies: two stunned, 12% and 20%
        out += wear(high) + [(T("wears", "Other Bracers", 0), None), (T("stored", "Other Bracers", CUT, 20), None), (T("stunned", 2), None),
                             (T("factor"), g(((1 - high / 100) * 0.8) ** 2))]
        # another stat of another item is not this reduction
        out += [clear, (T("wears", "Odd Bracers", 0), None), (T("stunned", 3), None), (T("factor"), "1")]
        # a hundred percent is no reduction the rule carries
        out += [clear, (T("wears", "Whole Bracers", 0), None), (T("stunned", 2), None), (T("factor"), "1")]
        # a look is due at the cadence, not before; a wrapped clock is no break; no cadence never looks
        out += [(T("due", 0, 249, 0.25), "0"), (T("due", 0, 250, 0.25), "1"), (T("due", 1000, 1249, 0.25), "0"), (T("due", 1000, 1250, 0.25), "1"),
                (T("due", 4294967200, 100, 0.25), "0"), (T("due", 4294967200, 200, 0.25), "1"), (T("due", 0, 5000, 0), "0"), (T("due", 0, 5000, -1), "0")]
        # a stun is a stun; a freeze (the Freeze mechanic, or Torment's freeze hold) is not
        out += [(T("aura", 12345, 0), "1"), (T("aura", 12345, 1), "0"), (T("aura", FREEZE_HOLD, 0), "0"), (T("aura", FREEZE_HOLD, 1), "0")]
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
        self.assertGreater(len(want), 30)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(3, len(rows))
        want, _ = self.drive(real, rows, "want")
        cut = [r for r in rows if r[4] == CUT]
        radius = [r for r in rows if r[4] == RADIUS]
        every = [r for r in rows if r[4] == EVERY]
        row_mutants = {
            "the_wrong_stat": [r[:4] + ("damage_reduction_pct",) + r[5:] for r in cut] + radius + every,
            "the_wrong_owner": [("Other Bracers",) + r[1:] for r in rows],
            "the_range_fixed_at_the_bottom": [r[:6] + (r[5],) + r[7:] for r in cut] + radius + every,
            "a_wider_radius": cut + [r[:5] + (50.0, 50.0) + r[7:] for r in radius] + every,
            "a_slower_cadence": cut + radius + [r[:5] + (1.0, 1.0) + r[7:] for r in every],
            "no_radius": cut + every,
            "no_cadence": cut + radius,
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double StunnedReduction("):]
        body = body[:body.index("\n    }\n") + 7]
        due = real[real.index("inline bool ScanDue("):]
        due = due[:due.index("\n    }\n") + 7]
        aura = real[real.index("inline bool StunAura("):]
        aura = aura[:aura.index("\n    }\n") + 7]
        rules = {
            "not_per_enemy": (body, "static_cast<double>(situation.stunnedNear)", "1.0"),
            "added_not_multiplied": (body, "factor *= std::pow(1.0 - pct / 100.0, static_cast<double>(situation.stunnedNear));",
                                     "factor -= pct / 100.0 * situation.stunnedNear;"),
            "a_raise_not_a_cut": (body, "1.0 - pct / 100.0", "1.0 + pct / 100.0"),
            "percent_as_a_fraction": (body, "1.0 - pct / 100.0", "1.0 - pct"),
            "any_stat": (body, '"damage_reduction_per_stunned_pct"', '"damage_reduction_pct"'),
            "a_hundred_cuts_all": (body, "pct > 0 && pct < 100", "pct > 0"),
            "the_cadence_a_tenth": (due, "seconds * 1000.0", "seconds * 100.0"),
            "the_cadence_exclusive": (due, ">= static_cast<std::uint32_t>(seconds * 1000.0)", "> static_cast<std::uint32_t>(seconds * 1000.0)"),
            "no_cadence_looks": (due, "seconds > 0 &&", ""),
            "a_freeze_stuns": (aura, '== "control_stun"', '!= ""'),
            "a_stun_does_not": (aura, '== "control_stun"', '== "control_freeze"'),
            "the_mechanic_ignored": (aura, "ControlEvent(spellId, true, freeze, false, false)", "ControlEvent(spellId, true, false, false, false)"),
        }
        for name, (where, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, where, name + " does not apply")
                _, got = self.drive(real.replace(where, where.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_bottom_not_the_roll": real.replace("number = found->value;", "number = row.min;"),
            "the_count_unread": real.replace("static_cast<double>(situation.stunnedNear)", "0.0"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
