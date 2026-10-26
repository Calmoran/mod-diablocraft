"""Legendary rest, bead diablocraft-wme53: Bracers of Destruction (Barbarian bracers), and the piece it builds, N-NHIT.

  "Seismic Slam deals [400 - 500]% increased damage to the first 10 enemies it hits."
  * the numbers (the roll range 400-500, the count 10) are read from d3planner (item_wrists.js, leg_bracersofdestruction_p67) and from the
    legendaries sheet (barbarian_legendaries.csv), the skill from barbarian_skills.csv, apart from the table; the table (data/legendary_powers.csv)
    holds ONE `skill` row for the pool item P67_Unique_Bracer_100: Seismic Slam, `damage_increase_pct`, 400-500, condition `first_hits` 10, which
    the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    accepts `first_hits` only on a skill's damage_increase_pct row with a whole count, no event and no cond_skills;
  * the production rules (src/combat/dc_item_power_math.h: Holds' `first_hits` and NearestPlace, with SkillFactor / Owned / RollPowers) are
    compiled and driven with the generated row: a hit at place 1 to 10 of its cast takes 1 + N/100, the 11th and on and a hit no cast counted
    take nothing; the places go nearest the cast's centre first, equal distances in the list's order; only Seismic Slam, only while worn and rolled;
    a Primal stores 500;
  * mutants of the rows, the rules and the header fail the same driver;
  * source-text guards that Seismic Slam resolves through ResolveCast's target loop (a cone, no projectile Speed), that the loop sets the place
    from the distances to the centre around each hit and puts it back, that the place is thread_local and read into every situation, and that
    the hit's legendary term reads damage_increase_pct with the base skill name; the C++ is compile-checked by syntax_check.sh and the in-game
    steps are in docs/test-diablocraft-wme53.md.
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
HARNESS = MODULE / "tests/item_power_bracers_of_destruction/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P67_Unique_Bracer_100"
SKILL = "Seismic Slam"
STAT = "damage_increase_pct"
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
    """(low, high, count) as the planner words them, checked against the legendaries sheet."""
    text = (REPO / "reference/d3planner/item_wrists.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Seismic Slam deals %d%% increased damage to the first (\d+) enemies it hits\.", min: (\d+), max: (\d+)', item)
    assert m, item
    sheet = next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == "Bracers of Destruction")
    assert sheet == "Seismic Slam deals [%s - %s]%% increased damage to the first %s enemies it hits." % (m[2], m[3], m[1]), sheet
    return float(m[2]), float(m[3]), int(m[1])


class Table(unittest.TestCase):
    def test_the_sources_name_seismic_slam_the_range_and_the_count(self):
        self.assertEqual((400.0, 500.0, 10), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])

    def test_one_damage_row_names_seismic_slam_and_its_count(self):
        low, high, count = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, "first_hits", float(count), "", 0.0, 0, "", "", 100.0, 0.0)], mine())

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("400–500%", m[1])
        self.assertIn("first 10 enemies", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "400", "value_max": "500", "cond": "first_hits",
            "cond_arg": "10", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        """The generator run on a copy of the module whose sheet is the real one with the owner's row replaced by `edits` (dicts over BASE)."""
        work = Path(tempfile.mkdtemp(prefix="bracers-gen-", dir=str(SCRATCH)))
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
        SCRATCH.mkdir(parents=True, exist_ok=True)
        first = "first_hits is a skill's damage_increase_pct row's"
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min <= value_max"),
            "not a skill": ({"skill": "Seismic Slamx"}, "is not a skill"),
            "no count": ({"cond_arg": ""}, "needs cond_arg > 0"),
            "a part of an enemy": ({"cond_arg": "10.5"}, first),
            "another stat": ({"stat": "cooldown_reduction_pct"}, first),
            "named skills": ({"cond_skills": "Seismic Slam"}, first),
            "an event": ({"fire_on": "cast", "fire_skills": "Seismic Slam"}, "an event fires an effect row|" + first),
            "an unknown condition": ({"cond": "first_hit"}, "cond is one of"),
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
        work = Path(tempfile.mkdtemp(prefix="itembracers-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        low, high, count = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: nothing, whatever the place
        out += clear + [(T("place", SKILL, 1), "1")]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("place", SKILL, 1), "1")]
        # worn and rolled: the first `count` enemies take 1 + N/100, the rest nothing, a hit no cast counted nothing
        for roll in (low, 450, high):
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, roll), None)]
            for place in range(0, count + 6):
                out += [(T("place", SKILL, place), g(1 + roll / 100) if 1 <= place <= count else "1")]
            out += [(T("place", SKILL, 100), "1")]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, STAT, 450), None), (T("place", SKILL, 1), "1")]
        # only Seismic Slam: no other skill, nothing for the empty name
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, high), None)]
        for other in ("Earthquake", "Ground Stomp", "Leap", "Ancient Spear", "Avalanche", "Whirlwind", "Seismic", "Seismic Slam Rune", ""):
            out += [(T("place", other, 1), "1")]
        # the places: nearest the centre first, 1 the nearest; equal distances keep the list's order; past the list, none
        for distances, places in (("5", [1]), ("3;1;2", [3, 1, 2]), ("10;10;4", [2, 3, 1]), ("0;0", [1, 2]),
                                  (";".join(str(40 - d) for d in range(12)), list(range(12, 0, -1)))):
            for index, place in enumerate(places):
                out += [(T("nearest", distances, index), str(place))]
        out += [(T("nearest", "3;1;2", 3), "0"), (T("nearest", "3;1;2", 7), "0")]
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
        self.assertGreater(len(want), 60)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Earthquake",) + r[4:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_count_of_the_old_item": [r[:8] + (5.0,) + r[9:] for r in rows],
            "no_condition": [r[:7] + ("", 0.0) + r[9:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        rules = {
            "the_last_place_dropped": ("situation.hitPlace <= row.arg", "situation.hitPlace < row.arg"),
            "an_uncounted_hit_takes_it": ("situation.hitPlace >= 1 && situation.hitPlace <= row.arg", "situation.hitPlace <= row.arg"),
            "every_hit_takes_it": ("return situation.hitPlace >= 1 && situation.hitPlace <= row.arg;", "return true;"),
            "farthest_first": ("distances[other] < distances[index] ||", "distances[other] > distances[index] ||"),
            "ties_by_reverse_order": ("&& other < index))", "&& other > index))"),
            "ties_all_first": ("|| (distances[other] == distances[index] && other < index)", ""),
            "past_the_list_is_first": ("if (index >= distances.size())\n            return 0;", "if (index >= distances.size())\n            return 1;"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                want, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
