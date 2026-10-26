"""Legendary rest, bead diablocraft-s8lut: Vile Ward (Barbarian shoulders), on the piece Bracers of Destruction built, N-NHIT.

  "Furious Charge deals [30 - 35]% increased damage for every enemy hit while charging."
  * the numbers (the roll range 30-35) are read from d3planner (item_shoulders.js, leg_vileward) and from the legendaries sheet
    (barbarian_legendaries.csv), the skill from barbarian_skills.csv, apart from the table; the table (data/legendary_powers.csv) holds ONE
    `skill` row for the pool item Unique_Shoulder_003_p1: Furious Charge, `damage_increase_pct`, 30-35, condition `per_prior_hit`, which the
    roller rolls once per item;
  * the generator accepts `per_prior_hit` only on a skill's damage_increase_pct row, with no cond_arg, no event and no cond_skills;
  * the production rules (src/combat/dc_item_power_math.h: Holds' `per_prior_hit`, PriorHits and Counted, with SkillFactor / Owned / RollPowers)
    are compiled and driven with the generated row: a hit at place K of its charge takes 1 + K x N/100 (K = its place, so the first enemy
    takes one step, the 2nd two, the 4th four; the designer's card q-1021-03), a hit no cast counted takes nothing, there is no cap; only Furious Charge, only
    while worn and rolled; a Primal stores 35;
  * mutants of the rows, the rules and the header fail the same driver;
  * the source-text guards (Furious Charge resolves through ResolveCast's target loop, the loop counts the places from where the line starts and
    puts the place back, the place is thread_local and read into every situation, the hit reads the base skill name) are in
    test_item_power_vile_ward_wiring.py; the C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-s8lut.md.
"""
import csv
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
HARNESS = MODULE / "tests/item_power_vile_ward/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Shoulder_003_p1"
SKILL = "Furious Charge"
STAT = "damage_increase_pct"
COND = "per_prior_hit"
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
    """(low, high) as the planner words them, checked against the legendaries sheet."""
    text = (REPO / "reference/d3planner/item_shoulders.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Furious Charge deals %d%% increased damage for every enemy hit while charging\.", min: (\d+), max: (\d+)', item)
    assert m, item
    sheet = next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == "Vile Ward")
    assert sheet == "Furious Charge deals [%s - %s]%% increased damage for every enemy hit while charging." % (m[1], m[2]), sheet
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_name_furious_charge_and_the_range(self):
        self.assertEqual((30.0, 35.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])

    def test_one_damage_row_names_furious_charge(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, COND, 0.0, "", 0.0, 0, "", "", 100.0, 0.0)], mine())

    def test_the_owner_is_the_barbarian_shoulders_that_drop(self):
        item = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Vile Ward", "shoulders", "legendary", "barbarian", "yes", "no"),
                         (item["d3_name"], item["slot"], item["rarity"], item["designated_class"], item["pool_version"], item["craft_only"]))

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_shoulders.js", rows[0]["source"])
        self.assertIn("leg_vileward", rows[0]["source"])
        self.assertTrue(rows[0]["note"])

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("30–35%", m[1])
        self.assertIn("every enemy hit", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "30", "value_max": "35", "cond": COND,
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        """The generator run on a copy of the module whose sheet is the real one with the owner's row replaced by `edits` (dicts over BASE)."""
        work = Path(tempfile.mkdtemp(prefix="vileward-gen-", dir=str(SCRATCH)))
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

    def test_the_real_row_passes(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        prior = "per_prior_hit is a skill's damage_increase_pct row's"
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min <= value_max"),
            "not a skill": ({"skill": "Furious Chargex"}, "is not a skill"),
            "a count": ({"cond_arg": "3"}, "per_prior_hit takes no cond_arg"),
            "another stat": ({"stat": "cooldown_reduction_pct"}, prior),
            "named skills": ({"cond_skills": "Furious Charge"}, prior),
            "an event": ({"fire_on": "cast", "fire_skills": "Furious Charge"}, "an event fires an effect row|" + prior),
            "a player row": ({"kind": "player", "skill": ""}, prior),
            "an unknown condition": ({"cond": "per_prior_hits"}, "cond is one of"),
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
        work = Path(tempfile.mkdtemp(prefix="itemvileward-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: nothing, whatever the place
        out += clear + [(T("place", SKILL, 1), "1"), (T("place", SKILL, 5), "1")]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("place", SKILL, 5), "1")]
        # worn and rolled: the hit at place K takes 1 + K x N/100, the first enemy one step, the second two, the third three, a hit no cast
        # counted nothing, and no cap however many are hit
        for roll in (low, 32, high):
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, roll), None)]
            out += [(T("place", SKILL, 0), "1")]
            for place in range(1, 40):
                out += [(T("place", SKILL, place), g(1 + place * roll / 100))]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, STAT, 32), None), (T("place", SKILL, 4), "1")]
        # only Furious Charge: no other skill, nothing for the empty name
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, high), None)]
        for other in ("Seismic Slam", "Leap", "Ground Stomp", "Whirlwind", "Revenge", "Furious", "Furious Charge Rune", ""):
            out += [(T("place", other, 4), "1")]
        # the places the rule counts from: nearest the centre first, 1 the nearest (the same NearestPlace the first-N powers use)
        for distances, places in (("5", [1]), ("3;1;2", [3, 1, 2]), ("10;10;4", [2, 3, 1])):
            for index, place in enumerate(places):
                out += [(T("nearest", distances, index), str(place))]
        # one roll stored under the skill's name: a Primal stores the top of the range
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
        self.assertGreater(len(want), 100)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Leap",) + r[4:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_bracers_condition": [r[:7] + ("first_hits", 10.0) + r[9:] for r in rows],
            "no_condition": [r[:7] + ("", 0.0) + r[9:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        rules = {
            "back_to_the_place_less_one": ("return static_cast<double>(situation.hitPlace);",
                                           "return situation.hitPlace > 1 ? static_cast<double>(situation.hitPlace - 1) : 0.0;"),
            "two_places_less": ("return static_cast<double>(situation.hitPlace);",
                                "return situation.hitPlace > 2 ? static_cast<double>(situation.hitPlace - 2) : 0.0;"),
            "one_step_too_many": ("return static_cast<double>(situation.hitPlace);", "return static_cast<double>(situation.hitPlace) + 1.0;"),
            "one_stack_whatever_the_count": ("return PriorHits(situation);", "return 1.0;"),
            "the_first_hit_takes_none": ("return PriorHits(situation) > 0;", "return PriorHits(situation) > 1;"),
            "capped_at_four": ("return PriorHits(situation);", "return std::min(PriorHits(situation), 4.0);"),
            "an_uncounted_hit_takes_a_step": ("return static_cast<double>(situation.hitPlace);",
                                              "return static_cast<double>(situation.hitPlace > 0 ? situation.hitPlace : 1);"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                want, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "an_unworn_item_counts": real.replace("situation.wornSince.count(row.owner)", "true"),
            "a_primal_stores_the_bottom": real.replace("atTop ? Best(row) : roll(row.min, row.max)", "atTop ? row.min : roll(row.min, row.max)"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
