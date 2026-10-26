"""Legendary rest, bead diablocraft-r2lly: Standoff (Barbarian two-hand polearm), the first N-DERIVED row.

  "Furious Charge deals increased damage equal to [400 - 500]% of your bonus movement speed."
  * the numbers (the roll range 400-500) are read from d3planner (item_twohand.js, leg_standoff_p6) and from the legendaries sheet
    (barbarian_legendaries.csv), the skill from barbarian_skills.csv, apart from the table; the table (data/legendary_powers.csv) holds ONE
    `skill` row for the pool item P61_Unique_Polearm_01: Furious Charge, `damage_per_movement_speed_pct`, 400-500, rolled once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    accepts the stat as a skill stat and still refuses a zero or negative number;
  * the production rule (src/combat/dc_item_power_math.h: DerivedFactor, with Owned / Holds / RollPowers) is compiled and driven with the
    generated row: 1 + N/100 x the bonus movement speed/100, continuous; no movement speed (or a negative sheet value) takes nothing; only
    Furious Charge, only while the item is worn and rolled; two sources multiply; a Primal stores 500;
  * mutants of the rule and of the row fail the same driver;
  * source-text guards that the hit multiplies the factor into its legendary term with the hit's own sheet, that the reader maps the stat to
    the sheet's Movement Speed and reads the player before the power lock, and that every stat the reader maps is one the generator carries;
    the C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-r2lly.md.
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
HARNESS = MODULE / "tests/item_power_standoff/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P61_Unique_Polearm_01"
SKILL = "Furious Charge"
STAT = "damage_per_movement_speed_pct"
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


def numbers():
    """(low, high) as the planner words them, checked against the legendaries sheet."""
    text = (REPO / "reference/d3planner/item_twohand.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'id: "leg_standoff_p6", [^}]*format: "Furious Charge deals increased damage equal to %d%% of your bonus movement speed\.", '
                  r'min: (\d+), max: (\d+)', item)
    assert m, item
    sheet = next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == "Standoff")
    assert sheet == "Furious Charge deals increased damage equal to [%s - %s]%% of your bonus movement speed." % (m[1], m[2]), sheet
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_name_furious_charge_and_the_range(self):
        self.assertEqual((400.0, 500.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")])

    def test_one_damage_row_names_furious_charge(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, *BLANK)], mine())

    def test_furious_charge_is_a_shell(self):
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertRegex(shells, r'\{\d+, "%s", "", ' % SKILL)

    def test_the_bonus_movement_speed_is_the_sheets_capped_stat(self):
        """D3's bonus movement speed: items capped at 25%, skill and proc bonuses beyond it; the sheet's Movement Speed is that sum."""
        rules = (MODULE / "data/generated/numeric_rules_0001.sql").read_text(encoding="utf-8")
        self.assertIn("('movement_cap_pct',25,", rules)
        common = (SRC / "common/dc_common.cpp").read_text(encoding="utf-8")
        self.assertIn('values[Index(Stat::MovementSpeed)] += std::clamp(cappedMovement, 0.0, NumericData::Rule("movement_cap_pct"));', common)

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("400–500%", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": STAT, "value_min": "400", "value_max": "500", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="standoff-gen-", dir=str(SCRATCH)))
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
        own = "needs 0 < value_min <= value_max"
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, own),
            "a negative number": ({"value_min": "-500", "value_max": "-400"}, own),
            "not a skill": ({"skill": "Furious Chargex"}, "is not a skill"),
            "a stat no reader maps": ({"stat": "damage_per_attack_speed_pct"}, "damage_per_attack_speed_pct"),
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
        work = Path(tempfile.mkdtemp(prefix="itemstandoff-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        factor = lambda roll, speed: g(1 + roll / 100 * speed / 100)  # noqa: E731
        # not worn: nothing, whatever the speed
        out += clear + [(T("derived", SKILL, STAT, 25), "1")]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("derived", SKILL, STAT, 25), "1")]
        # worn and rolled: N% of the bonus movement speed, continuous, at both ends of the roll and between
        for roll in (low, 450, high):
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, roll), None)]
            for speed in (0, 1, 5, 12.5, 24.9, 25, 30, 40, 75):
                out += [(T("derived", SKILL, STAT, speed), factor(roll, speed))]
            # a sheet below none (a slow) takes nothing, never a cut
            out += [(T("derived", SKILL, STAT, -30), "1")]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, SKILL, STAT, 450), None), (T("derived", SKILL, STAT, 25), "1")]
        # only Furious Charge, only this stat
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, high), None)]
        for other in ("Leap", "Bash", "Whirlwind", "Furious Charg", "Furious Charge Rune", ""):
            out += [(T("derived", other, STAT, 25), "1")]
        for stat in ("damage_increase_pct", "damage_per_attack_speed_pct"):
            out += [(T("derived", SKILL, stat, 25), "1")]
        # one roll stored under the skill's name: a Primal stores the top of the range
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, STAT, high)),
                (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, STAT, (low + high) / 2))]
        return out

    def run_cases(self, header_text, lines, name):
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(lines) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        return [w for _, w in cases if w is not None], self.run_cases(header_text, [line for line, _ in cases], name)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def two_sources(self, header_text, name):
        """Two weapons that each own a row of the stat, worn together, at 20% movement speed."""
        low, high = numbers()
        rows = mine() + [("Other Weapon", 0, "skill", SKILL, STAT, 100.0, 100.0, *BLANK)]
        lines = [T("row", *r) for r in rows] + [T("wears", OWNER), T("value", OWNER, SKILL, STAT, high), T("wears", "Other Weapon"),
                                                  T("value", "Other Weapon", SKILL, STAT, 100), T("derived", SKILL, STAT, 20)]
        return self.run_cases(header_text, lines, name)

    def test_two_sources_multiply(self):
        low, high = numbers()
        real = MATH.read_text(encoding="utf-8")
        self.assertEqual([g((1 + high / 100 * 20 / 100) * (1 + 100 / 100 * 20 / 100))], self.two_sources(real, "two"))
        old = "factor *= 1.0 + pct / 100.0 * value / 100.0;"
        self.assertIn(old, real)
        self.assertNotEqual(self.two_sources(real, "two"), self.two_sources(real.replace(old, "factor += pct / 100.0 * value / 100.0;"), "sum"))

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Leap",) + r[4:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_increase_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double DerivedFactor"):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "the_value_ignored": ("pct / 100.0 * value / 100.0", "pct / 100.0"),
            "percent_unscaled": ("pct / 100.0 * value / 100.0", "pct / 100.0 * value"),
            "a_slow_cuts": ("std::max(0.0, statValue)", "statValue"),
            "the_stat_ignored": ('"skill", skill, stat, situation', '"skill", skill, "' + STAT + '", situation'),
            "the_skill_ignored": ('"skill", skill, stat', '"skill", "' + SKILL + '", stat'),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                want, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
