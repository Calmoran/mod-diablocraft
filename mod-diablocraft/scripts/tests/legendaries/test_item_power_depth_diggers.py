"""Legendary rest, bead diablocraft-vijvi: Depth Diggers (class-free pants).

  "Primary skills that generate resource deal [80-100]% additional damage."
  * the numbers (the roll range 80-100) are read from d3planner (item_legs.js, leg_depthdiggers) and the catalogue row; the skills are the
    primaries that generate a resource, read from the class skill sheets (barbarian_skills.csv fury_generation, wizard_skills.csv
    resource_generation, category Primary): the Barbarian's four. The Wizard's four signature spells are free to cast and generate nothing,
    so D3's rule leaves them out (PM ruling on the bead); a later class's generating primaries join the row when that class lands;
  * the table (data/legendary_powers.csv) holds ONE `skill` row listing the four joined by ';' with `damage_increase_pct`, the range the roller
    rolls once per item (so the four share one roll); the generator refuses a bad list;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: SkillFactor, RollPowers, Best) are compiled and driven with the generated rows:
    each of the four takes x(1 + roll/100) while the item is worn and rolled, nothing unworn or unrolled, no other skill (a secondary, a
    Wizard primary) takes any of it, and a Primal stores the top of the range;
  * mutants fail the same driver (a skill lost, a Wizard primary added, a wrong number, the wrong stat, a rule that ignores the worn item or
    the roll);
  * a source-text guard that the hit's legendary term reads the base skill name of a primary's shell, so every rune of a primary gets the
    power (the C++ is compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-vijvi.md).
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

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_math/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Pants_006_p1"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
LIST = "Frenzy;Weapon Throw;Bash;Cleave"
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%g" % x  # noqa: E731


def read_csv_path(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def read_csv(name):
    return read_csv_path(MODULE / name)


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def primaries():
    """The primary skills that generate a resource, from the class skill sheets (the item's own words: 'Primary skills that generate resource')."""
    barbarian = [r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv") if r["category"] == "Primary" and r["fury_generation"]]
    wizard = [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv") if r["category"] == "Primary" and r["resource_generation"]]
    return barbarian + wizard


def wizard_primaries():
    return [r["skill_name"] for r in read_csv("data/d3/wizard_skills.csv") if r["category"] == "Primary"]


def numbers():
    """(damage low, damage high) as the planner words them, checked against the catalogue's row."""
    text = (REPO / "reference/d3planner/item_legs.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Primary skills that generate resource deal %d%% additional damage.", min: (\d+), max: (\d+)', item)
    assert m, item
    row = next(r for r in read_csv_path(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
    assert row["power_text"] == "Primary skills that generate resource deal [%s-%s]%% additional damage." % (m[1], m[2]), row["power_text"]
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_name_four_generating_primaries_and_their_numbers(self):
        self.assertEqual(["Frenzy", "Weapon Throw", "Bash", "Cleave"], primaries())
        self.assertEqual((80.0, 100.0), numbers())

    def test_the_wizard_primaries_generate_nothing_so_they_are_left_out(self):
        self.assertEqual(["Magic Missile", "Shock Pulse", "Spectral Blade", "Electrocute"], wizard_primaries())
        for r in read_csv("data/d3/wizard_skills.csv"):
            if r["category"] == "Primary":
                self.assertEqual("", r["resource_generation"], r["skill_name"])
                self.assertIn("free to cast", r["full_tooltip_text"])

    def test_one_damage_row_lists_the_four_primaries(self):
        low, high = numbers()
        self.assertEqual(LIST, ";".join(primaries()))
        self.assertEqual({(OWNER, 0, "skill", LIST, "damage_increase_pct", low, high, *BLANK)}, set(mine()))
        self.assertEqual(1, len(mine()))

    def test_each_primary_is_a_skill_and_a_shell(self):
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        for skill in primaries():
            # a shell of the skill itself (rune ""), the one the hit resolves to when no rune is chosen
            self.assertRegex(shells, r'\{\d+, "%s", "", ' % re.escape(skill))

    def test_the_generator_refuses_a_bad_list(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER and r["stat"] == "damage_increase_pct")
        refused = {
            "an unknown skill in the list": dict(base, skill="Frenzy;Not A Skill"),
            "a skill listed twice in a row": dict(base, skill="Frenzy;Frenzy"),
            "an empty name": dict(base, skill="Frenzy;"),
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
        self.assertIn("80–100%", m[1])      # the shipped tooltip omits "that generate resource"; it is not changed here


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemdepth-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        others = ("Whirlwind", "Hammer of the Ancients", "Rend", "Leap", *wizard_primaries(), "Throw", "Cleav", "Frenzy;Bash", "")
        for skill in primaries():
            # not worn: nothing
            out += clear + [(T("factor", skill, "damage_increase_pct"), "1")]
            # worn, no roll stored yet: the damage has no roll and gives nothing
            out += clear + [(T("wears", OWNER), None), (T("factor", skill, "damage_increase_pct"), "1")]
            # worn and rolled: x(1 + roll/100), at both ends and between
            for roll in (low, 90, high):
                out += clear + [(T("wears", OWNER), None), (T("value", OWNER, LIST, "damage_increase_pct", roll), None),
                                (T("factor", skill, "damage_increase_pct"), g(1 + roll / 100)), (T("factor", skill, "attack_speed_pct"), "1")]
            # a roll stored but the item in the bag
            out += clear + [(T("value", OWNER, LIST, "damage_increase_pct", 90), None), (T("factor", skill, "damage_increase_pct"), "1")]
        # only the four: no other skill takes the number, at the item's best roll
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, LIST, "damage_increase_pct", high), None)]
        for other in others:
            out += [(T("factor", other, "attack_speed_pct"), "1"), (T("factor", other, "damage_increase_pct"), "1")]
        # the power's other stats are not read: a cost, a duration
        out += [(T("factor", "Frenzy", "dot_duration_seconds"), "1"), (T("factor", "Frenzy", "summon_attack_speed_pct"), "1")]
        # the four share ONE roll, stored under the first name: a Primal stores the top of the range
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
        self.assertGreater(len(want), 60)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "a_primary_lost": [r[:3] + ("Frenzy;Weapon Throw;Bash",) + r[4:] for r in rows],
            "a_wizard_primary_added": [r[:3] + (LIST + ";Magic Missile",) + r[4:] for r in rows],
            "the_damage_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("attack_speed_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "only_the_whole_list_matches": real.replace("NamesSkill(row.skill, skill) && row.stat == stat && Owned", "row.skill == skill && row.stat == stat && Owned"),
            "a_name_matches_by_part": real.replace("names.compare(from, to - from, skill) == 0", "names.compare(from, to - from, skill) <= 0 && names.find(skill) != std::string::npos"),
            "the_roll_key_is_the_whole_list": real.replace('"power:" + FirstSkill(row.skill) + ":" + row.stat', '"power:" + row.skill + ":" + row.stat'),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
