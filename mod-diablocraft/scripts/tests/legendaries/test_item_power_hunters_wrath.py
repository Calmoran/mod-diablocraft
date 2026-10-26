"""Legendary rest, bead diablocraft-q3ezz: Hunter's Wrath (a belt, any class).

  "Your primary skills attack 30% faster and deal [150-200]% increased damage."
  * the numbers (30, and the roll range 150-200) are read from d3planner (item_waist.js, leg_hunterswrath_p69) and the catalogue row, the
    primary skills of the classes Torment has (the Barbarian's four and the Wizard's four) from barbarian_skills.csv and wizard_skills.csv
    (category Primary), apart from the table; the table (data/legendary_powers.csv) holds two `skill` rows that list the eight primaries
    joined by ';' (the framework piece of diablocraft-kaz5u, Oathkeeper): `attack_speed_pct` (the fixed 30) and `damage_increase_pct` (the range
    the roller rolls once per item, so the eight share one roll); the list is 84 characters, so the table's skill column is VARCHAR(128);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: SkillFactor, RollPowers, Best) are compiled and driven with the generated rows:
    each primary is 1.3 times as fast and takes x(1 + roll/100) while the item is worn and rolled, nothing unworn or unrolled, no other skill
    (a secondary of either class) takes any of it, and a Primal stores the top of the range;
  * mutants fail the same driver (a primary lost, a wrong number, the wrong stat, a rule that ignores the worn item or the roll);
  * a source-text guard that the two readers (the hit's legendary term and a skill's swing recovery) read the base skill name of a primary's
    shell, so every rune of a primary gets the power, and that every Wizard primary shell states no cooldown (so it is swing-eligible and its
    recovery, which the speed row shortens, applies); the C++ is compile-checked by syntax_check.sh; the in-game steps are in
    docs/test-diablocraft-q3ezz.md.
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
from test_skill_swing_recovery import sql_rows
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_math/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P69_Unique_Belt_005"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
LIST = "Frenzy;Weapon Throw;Bash;Cleave;Magic Missile;Shock Pulse;Spectral Blade;Electrocute"
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def primaries():
    """The primary skills of the classes Torment has (Barbarian, then Wizard), from the skills sheets."""
    return [r["skill_name"] for sheet in ("barbarian", "wizard") for r in read_csv("data/d3/%s_skills.csv" % sheet) if r["category"] == "Primary"]


def secondaries():
    return [r["skill_name"] for sheet in ("barbarian", "wizard") for r in read_csv("data/d3/%s_skills.csv" % sheet) if r["category"] != "Primary"]


def numbers():
    """(attack speed percent, (damage low, damage high)) as the planner words them, checked against the catalogue row."""
    text = (REPO / "reference/d3planner/item_waist.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Your primary skills attack (\d+)%% faster and deal %d%% increased damage.", min: (\d+), max: (\d+)', item)
    assert m, item
    row = next(r for r in read_csv("../docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
    assert row["power_text"] == "Your primary skills attack %s%% faster and deal [%s-%s]%% increased damage." % (m[1], m[2], m[3]), row["power_text"]
    return float(m[1]), (float(m[2]), float(m[3]))


class Table(unittest.TestCase):
    def test_the_sources_name_eight_primaries_and_their_numbers(self):
        self.assertEqual(["Frenzy", "Weapon Throw", "Bash", "Cleave", "Magic Missile", "Shock Pulse", "Spectral Blade", "Electrocute"], primaries())
        self.assertEqual((30.0, (150.0, 200.0)), numbers())

    def test_one_speed_row_and_one_damage_row_list_the_eight_primaries(self):
        speed, (low, high) = numbers()
        self.assertEqual(LIST, ";".join(primaries()))
        want = {(OWNER, 0, "skill", LIST, "attack_speed_pct", speed, speed, *BLANK),
                (OWNER, 0, "skill", LIST, "damage_increase_pct", low, high, *BLANK)}
        self.assertEqual(want, set(mine()))
        self.assertEqual(2, len(mine()))

    def test_each_primary_is_a_skill_and_a_shell(self):
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        for skill in primaries():
            # a shell of the skill itself (rune ""), the one the hit resolves to when no rune is chosen
            self.assertRegex(shells, r'\{\d+, "%s", "", ' % re.escape(skill))

    def test_the_owner_is_a_belt_for_any_class_that_drops(self):
        item = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Hunter's Wrath", "waist", "legendary", "", "yes", "no"),
                         (item["d3_name"], item["slot"], item["rarity"], item["designated_class"], item["pool_version"], item["craft_only"]))
        # the legacy copy (45-60%) is not in the pool, so only the current numbers are built
        legacy = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == "P3_Unique_Belt_005")
        self.assertEqual("no", legacy["pool_version"])

    def test_the_skill_cell_fits_the_column(self):
        self.assertEqual(84, len(LIST))
        self.assertIn("skill VARCHAR(128) NOT NULL", GENERATED.read_text(encoding="utf-8"))

    def test_the_generator_refuses_a_bad_list(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == "damage_increase_pct")
        refused = {
            "an unknown skill in the list": dict(base, skill="Frenzy;Not A Skill"),
            "a skill listed twice in a row": dict(base, skill="Frenzy;Frenzy"),
            "an empty name": dict(base, skill="Frenzy;"),
            "a cell over the column": dict(base, skill=";".join(["Frenzy", "Weapon Throw", "Bash", "Cleave", "Magic Missile", "Shock Pulse", "Spectral Blade",
                                                                 "Electrocute", "Whirlwind", "Hammer of the Ancients", "Seismic Slam"])),
            "a list on an element row": dict(base, kind="element", skill="fire;cold", stat="damage_pct"),
        }
        for name, row in refused.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        overlap = dict(base, skill="Cleave;Bash")
        with self.subTest("a skill named in two rows of one stat"), self.assertRaises(ValueError):
            self.rows_of([base, overlap])
        self.assertEqual(1, len(self.rows_of([base])))
        other_stat = dict(base, stat="attack_speed_pct", value_min="50", value_max="50", skill="Cleave;Bash")
        self.assertEqual(2, len(self.rows_of([base, other_stat])))     # the same skills under another stat are fine

    @staticmethod
    def rows_of(sheet_rows):
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as folder:
            module = Path(folder)
            (module / "data/d3").mkdir(parents=True)
            for name in ("base_items.csv", "affix_pools.csv", "legendary_potions.csv", *sorted(p.name for p in (MODULE / "data/d3").glob("*_skills.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_skill_values.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_runes.csv"))):
                shutil.copy(MODULE / "data/d3" / name, module / "data/d3" / name)
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", module / "data/legendary_power_buffs.csv")
            with (module / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(sheet_rows[0]))
                writer.writeheader()
                writer.writerows(sheet_rows)
            return [row for row in generator.rows(module) if row[2] != "potion"]

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("150–200%", m[1])
        self.assertIn("30% faster", m[1])


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemoath-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        speed, (low, high) = numbers()
        fast = 1 + speed / 100
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        others = (*secondaries(), "Throw", "Cleav", "Magic", "Frenzy;Bash", "")
        for skill in primaries():
            # not worn: nothing
            out += clear + [(T("factor", skill, "attack_speed_pct"), "1"), (T("factor", skill, "damage_increase_pct"), "1")]
            # worn, no roll stored yet: the speed is a fixed number and stands, the damage has no roll and gives nothing
            out += clear + [(T("wears", OWNER), None), (T("factor", skill, "attack_speed_pct"), g(fast)), (T("factor", skill, "damage_increase_pct"), "1")]
            # worn and rolled: x(1 + roll/100), at both ends and between
            for roll in (low, 175, high):
                out += clear + [(T("wears", OWNER), None), (T("value", OWNER, LIST, "damage_increase_pct", roll), None),
                                (T("factor", skill, "damage_increase_pct"), g(1 + roll / 100)), (T("factor", skill, "attack_speed_pct"), g(fast))]
            # a roll stored but the item in the bag
            out += clear + [(T("value", OWNER, LIST, "damage_increase_pct", 175), None), (T("factor", skill, "damage_increase_pct"), "1"),
                            (T("factor", skill, "attack_speed_pct"), "1")]
        # only the eight: no other skill takes either number, at the item's best roll
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, LIST, "damage_increase_pct", high), None)]
        for other in others:
            out += [(T("factor", other, "attack_speed_pct"), "1"), (T("factor", other, "damage_increase_pct"), "1")]
        # the power's other stats are not read: a cost, a duration
        out += [(T("factor", "Frenzy", "dot_duration_seconds"), "1"), (T("factor", "Frenzy", "summon_attack_speed_pct"), "1")]
        # the eight share ONE roll, stored under the first name: a Primal stores the top of the range, and nothing for the fixed speed row
        out += [(T("roll", OWNER, 1), "power:Frenzy:damage_increase_pct=%g;" % high),
                (T("roll", OWNER, 0), "power:Frenzy:damage_increase_pct=%g;" % ((low + high) / 2))]
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

    def test_every_rule_agrees_with_the_sources(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 100)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        speed_rows = [r for r in rows if r[4] == "attack_speed_pct"]
        damage_rows = [r for r in rows if r[4] == "damage_increase_pct"]
        row_mutants = {
            "a_primary_lost": [r[:3] + (LIST.rsplit(";", 1)[0],) + r[4:] for r in rows],
            "a_wizard_primary_lost": [r[:3] + (LIST.replace(";Magic Missile", ""),) + r[4:] for r in rows],
            "only_the_barbarians": [r[:3] + ("Frenzy;Weapon Throw;Bash;Cleave",) + r[4:] for r in rows],
            "the_speed_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == "attack_speed_pct" else r for r in rows],
            "the_damage_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == "damage_increase_pct" else r for r in rows],
            "the_stats_swapped": [r[:4] + ({"attack_speed_pct": "damage_increase_pct", "damage_increase_pct": "attack_speed_pct"}[r[4]],) + r[5:] for r in rows],
            "no_damage_rows": speed_rows,
            "no_speed_rows": damage_rows,
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "only_the_whole_list_matches": real.replace("NamesSkill(row.skill, skill) && row.stat == stat && Owned", "row.skill == skill && row.stat == stat && Owned"),
            "a_name_matches_by_part": real.replace("names.compare(from, to - from, skill) == 0", "names.compare(from, to - from, skill) <= 0 && names.find(skill) != std::string::npos"),
            "the_roll_key_is_the_whole_list": real.replace('"power:" + FirstSkill(row.skill) + ":" + row.stat', '"power:" + row.skill + ":" + row.stat'),
            "a_fixed_row_rolls": real.replace("return !row.pieces && row.kind != \"stat\" && row.min < row.max;", "return !row.pieces && row.kind != \"stat\" && row.min <= row.max;"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
