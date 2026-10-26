"""Legendary rest, bead diablocraft-057cl: Valthek's Rebuke (Wizard staff), on diablocraft-3ypq2's travelling Energy Twister.

  "Energy Twister now travels in a straight path and deals [300-400]% increased damage."
  * the words and the 300-400 are read from d3planner (data.json, leg_valtheksrebuke_p610; item_twohand.js has the older words without the number) and the
    catalogue; the table (data/legendary_powers.csv) holds TWO `skill` rows for P610_Unique_Staff_102: Energy Twister `straight_path` 1 (a flag, nothing
    to roll) and Energy Twister `damage_increase_pct` 300-400 (rolled once per item);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts
    `straight_path` for Energy Twister only, as a 1, and refuses another number, a range, another skill, a condition or event and a set bonus's row;
  * the production rules are compiled and driven with the generated rows: dc_item_power_math.h's SkillSetTo turns the twister's turn limit to 0 as
    EnergyTwister::Start composes it, and dc_twister_math.h's Path then keeps one heading for every leg (worn: a straight line of speed x life yards; not
    worn, or another owner's staff, or a row for another skill or stat: the wandering path), while SkillFactor on Energy Twister's damage is 1 + roll/100
    (1 without the staff, 1 for another skill, 1 for a staff with no roll stored);
  * mutants of the rules and of the rows fail the same driver, and mutants of EnergyTwister::Start (src/classes/wizard/dc_wizard_energy_twister.cpp) fail
    the source guards on it. The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-057cl.md.
"""
import csv
import json
import math
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
MATH = MODULE / "src/combat/dc_item_power_math.h"
TWISTER_MATH = MODULE / "src/classes/wizard/dc_twister_math.h"
HARNESS = MODULE / "tests/item_power_valtheks_rebuke/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P610_Unique_Staff_102"
SKILL = "Energy Twister"
PATH = "straight_path"
DAMAGE = "damage_increase_pct"
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


def planner():
    """The staff's text and range in d3planner's data.json (items[...] P610_Unique_Staff_102)."""
    items = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"]
    item = next(i for i in items if i["id"] == OWNER)
    return item["required"]["custom"]


def tunable(name):
    row = next(r for r in read_csv("data/tunables/wizard.csv") if r["name"] == name)
    return float(row["value"] or row["d3_value"])


def skill_number(token):
    return float(next(r["value"] for r in read_csv("data/d3/wizard_skill_values.csv") if r["skill"] == SKILL and r["rune"] == "" and r["token"] == token))


def wander(limit, speed, life, turn, rolls):
    """The path dc_twister_math.h's Path draws, written out again: start (0, 0), heading 0, one turn at the start of every leg after the first."""
    legs = math.ceil(life / turn - 1e-9)
    points, heading = [(0.0, 0.0)], 0.0
    for i in range(legs):
        if i > 0:
            heading += limit * (rolls[2 * (i - 1)] - rolls[2 * (i - 1) + 1]) * math.pi / 180.0
        seconds = min(turn, life - i * turn)
        x, y = points[-1]
        points.append((x + speed * seconds * math.cos(heading), y + speed * seconds * math.sin(heading)))
    return points


def parse(line):
    cells = [float(v) for v in line.split()]
    return list(zip(cells[0::2], cells[1::2]))


class Table(unittest.TestCase):
    def test_the_sources_give_the_rule_and_the_range(self):
        custom = planner()
        self.assertEqual("leg_valtheksrebuke_p610", custom["id"])
        self.assertEqual("Energy Twister now travels in a straight path and deals %d%% increased damage.", custom["format"])
        self.assertEqual((300, 400), (custom["min"], custom["max"]))
        text = (REPO / "reference/d3planner/item_twohand.js").read_text(encoding="utf-8")
        self.assertIn('custom: {id: "leg_valtheksrebuke", name: "Energy Twister Travels in a Straight Path", format: "Energy Twister now travels in a '
                      'straight path.", args: 0}', text)
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Energy Twister now travels in a straight path and deals [300-400]% increased damage.", catalogue[0]["power_text"])

    def test_two_rows_a_flag_and_the_damage_range(self):
        low, high = planner()["min"], planner()["max"]
        self.assertEqual([(OWNER, 0, "skill", SKILL, PATH, 1.0, 1.0, *BLANK), (OWNER, 0, "skill", SKILL, DAMAGE, float(low), float(high), *BLANK)],
                         sorted(mine(), key=lambda r: r[4] == DAMAGE))

    def test_the_rows_have_their_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual({PATH, DAMAGE}, {r["stat"] for r in rows})
        for r in rows:
            self.assertIn("leg_valtheksrebuke_p610", r["source"])
            self.assertIn("data.json", r["source"])
        self.assertIn("Twister::Path", next(r for r in rows if r["stat"] == PATH)["note"])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": PATH, "value_min": "1", "value_max": "1", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="valthek-gen-", dir=str(SCRATCH)))
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
        why = "straight_path is an item's value 1"
        refused = {
            "two": ({"value_min": "2", "value_max": "2"}, why),
            "a range": ({"value_min": "1", "value_max": "2"}, why),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
            "another skill": ({"skill": "Electrocute"}, why),
            "two skills": ({"skill": "Energy Twister;Electrocute"}, why),
            "not a skill": ({"skill": "Energy Twisterx"}, "is not a skill"),
            "a condition": ({"cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": SKILL}, why),
            "an event": ({"fire_on": "cast", "fire_skills": SKILL}, "an event fires"),
            "a set bonus": ({"pieces": "2"}, "not a set|" + why),
        }
        for name, (edit, reason) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, reason):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math_text, "wizard/dc_twister_math.h": TWISTER_MATH.read_text(encoding="utf-8")}
        binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemvalthek-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def numbers(self):
        # the tunables the path reads (data/tunables/wizard.csv), the skill's life (data/d3/wizard_skill_values.csv); the max-turn rolls turn +limit every leg
        limit, speed, turn = (tunable("energy_twister_turn_limit_degrees"), tunable("energy_twister_speed_yards_per_second"),
                              tunable("energy_twister_turn_interval_seconds"))
        life = skill_number("dot_duration_seconds")
        legs = math.ceil(life / turn - 1e-9)
        return limit, speed, life, turn, [1.0, 0.0] * legs

    def cases(self, rows):
        limit, speed, life, turn, rolls = self.numbers()
        low, high = planner()["min"], planner()["max"]
        args = (limit, speed, life, turn, ",".join("%g" % r for r in rolls))
        wanders = " ".join("%.4f %.4f" % p for p in wander(limit, speed, life, turn, rolls)) + " "
        straight = " ".join("%.4f %.4f" % (speed * min(i * turn, life), 0) for i in range(math.ceil(life / turn - 1e-9) + 1)) + " "
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: the wandering path, the damage term 1
        out += clear + [(T("path", *args), wanders), (T("factor", SKILL, DAMAGE), "1")]
        # worn: one heading for every leg, speed x life yards ahead, with no roll stored (a flag has none) and with the damage rolled
        out += clear + [(T("wears", OWNER), None), (T("path", *args), straight), (T("factor", SKILL, DAMAGE), "1")]
        for roll in (low, (low + high) / 2, high):
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, DAMAGE, roll), None), (T("path", *args), straight),
                            (T("factor", SKILL, DAMAGE), "%.10g" % (1 + roll / 100))]
            for other in ("Hydra", "Energy Twisters", "energy twister", ""):
                out += [(T("factor", other, DAMAGE), "1")]
        # the tunable moves the wandering path, never the straight one
        out += clear + [(T("wears", OWNER), None), (T("path", 90, speed, life, turn, args[4]), straight)]
        out += clear + [(T("path", 90, speed, life, turn, args[4]), " ".join("%.4f %.4f" % p for p in wander(90, speed, life, turn, rolls)) + " ")]
        # another owner's staff does nothing
        out += clear + [(T("wears", "Other Staff"), None), (T("path", *args), wanders)]
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
        self.assertGreater(len(want), 10)
        self.assertEqual(want, got)

    def test_the_wandering_path_is_not_straight_and_the_worn_one_is(self):
        # guards the driver itself: with max turns each leg the wandering path leaves the line, so "straight" can tell the two apart
        limit, speed, life, turn, rolls = self.numbers()
        self.assertGreater(limit, 0)
        points = wander(limit, speed, life, turn, rolls)
        self.assertGreater(max(abs(y) for _, y in points), 1.0)
        self.assertAlmostEqual(speed * life, points[0][0] + sum(math.dist(a, b) for a, b in zip(points, points[1:])), places=3)

    def test_the_mutants_fail_the_same_driver(self):
        math_text = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(math_text, rows, "want")
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Hydra",) + r[4:] for r in rows],
            "the_path_stat_lost": [r[:4] + ("jump_rehit",) + r[5:] if r[4] == PATH else r for r in rows],
            "the_damage_stat_lost": [r[:4] + ("attack_speed_pct",) + r[5:] if r[4] == DAMAGE else r for r in rows],
            "no_path_row": [r for r in rows if r[4] != PATH],
            "no_damage_row": [r for r in rows if r[4] != DAMAGE],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(math_text, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = math_text[math_text.index("inline double SkillSetTo("):]
        body = body[:body.index("\n    }\n") + 7]
        factor = math_text[math_text.index("inline double SkillFactor("):]
        factor = factor[:factor.index("\n    }\n") + 7]
        # SkillFactor adding where it multiplies is the same for one source, so no mutant here: test_item_power_math.py drives two sources together
        rules = {
            "never_raises": (body, "if (value > base)", "if (value < base)"),
            "reads_the_player_rows": (body, '"skill", skill, stat', '"player", skill, stat'),
            "factor_is_the_percent": (factor, "factor *= 1.0 + pct / 100.0;", "factor *= pct / 100.0;"),
            "factor_reads_the_player_rows": (factor, '"skill", skill, stat', '"player", skill, stat'),
        }
        for name, (part, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, part, name + " does not apply")
                _, got = self.drive(math_text.replace(part, part.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
