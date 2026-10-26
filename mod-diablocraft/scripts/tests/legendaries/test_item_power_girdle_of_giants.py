"""Legendary rest, bead diablocraft-5mn2l: Girdle of Giants (Barbarian belt, K3: a cast opens a triggered window that raises a skill).

  "Seismic Slam increases Earthquake damage by [200-250]% for 3 seconds."
  * the numbers (200-250, 3 seconds) are read from d3planner (item_waist.js, leg_girdleofgiants_p6) and the catalogue row; the two skills from
    the catalogue and barbarian_skills.csv; Seismic Slam is a skill the player presses (a shell the cast hook knows), Earthquake a shell the hit reads;
  * the table (data/legendary_powers.csv) holds ONE `skill` row: Earthquake, `damage_increase_pct` 200-250 (a range: rolls once per item),
    condition `triggered` for 3 s, fired on a `cast` of Seismic Slam; the generator refuses a bad shape of it;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: Fire, Holds, SkillFactor, RollPowers) are compiled and driven with the generated row:
    a Seismic Slam cast opens the window at the item's stored roll, it holds 3000 ms (the end inclusive) and not 3001, a recast renews it,
    no other skill's cast or other event opens it, only Earthquake takes it, nothing unworn or unrolled, a Primal stores the top, one roll;
  * mutants fail the same driver (a rule changed, one at a time);
  * source-text guards for the half that cannot be compiled here: the cast hook, and Earthquake's snapshot at the cast (the zone calls
    ComputeHit once, when it is cast, so the bonus is read at that moment and kept for the zone's whole life: the snapshot rule). The C++ is
    compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-5mn2l.md.
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
HARNESS = MODULE / "tests/item_power_events/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
MIGRATION = MODULE / "data/sql/db-world/updates" / GENERATED.name
OWNER = "P61_Unique_BarbBelt_EQ"
TRIGGER, TARGET, STAT = "Seismic Slam", "Earthquake", "damage_increase_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
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


def numbers():
    """(damage low, damage high, window seconds) as the planner words them, checked against the catalogue's row."""
    text = (REPO / "reference/d3planner/item_waist.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("\n  },", start)]
    m = re.search(r'custom: \{id: "leg_girdleofgiants_p6", [^}]*format: "Seismic Slam increases Earthquake damage by %d%% for (\d+) seconds\.", '
                  r'min: (\d+), max: (\d+)\}', item)
    assert m, item
    row = next(r for r in read_csv_path(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
    assert row["power_text"] == "Seismic Slam increases Earthquake damage by [%s-%s]%% for %s seconds." % (m[2], m[3], m[1]), row["power_text"]
    assert row["skills"] == "%s;%s" % (TRIGGER, TARGET), row["skills"]
    return float(m[2]), float(m[3]), float(m[1])


class Table(unittest.TestCase):
    def test_the_sources_name_the_numbers(self):
        self.assertEqual((200.0, 250.0, 3.0), numbers())

    def test_both_names_are_skills_and_shells(self):
        sheet = {r["skill_name"]: r for r in read_csv("data/d3/barbarian_skills.csv")}
        self.assertEqual("Secondary", sheet[TRIGGER]["category"])       # a skill the player presses
        self.assertIn(TARGET, sheet)
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        for skill in (TRIGGER, TARGET):
            # a shell of the skill itself (rune ""): Shells::FindAbility answers for the cast hook and the hit's base skill name
            self.assertRegex(shells, r'\{\d+, "%s", "", ' % re.escape(skill))

    def test_one_row_is_the_whole_power(self):
        low, high, window = numbers()
        self.assertEqual([(OWNER, 0, "skill", TARGET, STAT, low, high, "triggered", window, "", 0.0, 0, "cast", TRIGGER, 100.0, 0.0)], mine())

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("200–250%", m[1])
        self.assertIn("for 3 seconds", m[1])

    def test_the_generator_refuses_a_bad_shape(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        refused = {
            "triggered with no event": dict(base, fire_on="", fire_skills=""),
            "a cast with no skill": dict(base, fire_skills=""),
            "an unknown casting skill": dict(base, fire_skills="Not A Skill"),
            "an unknown target skill": dict(base, skill="Not A Skill"),
            "triggered with no seconds": dict(base, cond_arg=""),
            "triggered with cond_skills": dict(base, cond_skills=TRIGGER),
            "an event without triggered": dict(base, cond="", cond_arg=""),
            "a chance over 100": dict(base, chance_pct="101"),
            "no source": dict(base, source=""),
        }
        for name, row in refused.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        self.assertEqual(1, len(self.rows_of([base])))

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


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemgirdle-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        low, high, window = numbers()
        ms = int(window * 1000)
        out = [(T("row", *r), None) for r in rows]
        start = [(T("clear"), None), (T("now", 10000), None), (T("wears", OWNER, 0), None), (T("value", OWNER, TARGET, STAT, 225), None)]
        fire = lambda event, skill: (T("fire", event, skill, 1, 0, 0), "")  # noqa: E731
        factor = lambda skill, stat=STAT: T("factor", skill, stat)  # noqa: E731
        up = g(1 + 225 / 100)

        # nothing fired: no bonus; the cast opens it at the item's stored roll
        out += start + [(factor(TARGET), "1"), fire("cast", TRIGGER), (factor(TARGET), up)]
        # the window is 3 s, the end inclusive: 3000 ms after the cast still holds, 3001 does not
        out += [(T("now", 10000 + ms), None), (factor(TARGET), up), (T("now", 10000 + ms + 1), None), (factor(TARGET), "1")]
        # a certain row (no chance) fires whatever the draw: no roll is made
        out += start + [(T("fire", "cast", TRIGGER, 1, 99, 0), ""), (factor(TARGET), up)]
        # a recast renews it: from the new cast
        out += [(T("now", 12000), None), fire("cast", TRIGGER), (T("now", 12000 + ms), None), (factor(TARGET), up),
                (T("now", 12000 + ms + 1), None), (factor(TARGET), "1")]
        # a cast of another skill (Earthquake itself, Whirlwind, a primary) opens nothing; neither does another event
        out += start
        for other in ("Earthquake", "Whirlwind", "Hammer of the Ancients", "Frenzy", "Leap", "Seismic", "Slam", ""):
            out += [fire("cast", other), (factor(TARGET), "1")]
        for event in ("hit", "kill", "kill_elite", "taken", "hit_spender", "hit_generator"):
            out += [fire(event, TRIGGER), (factor(TARGET), "1")]
        # once open, only Earthquake takes it, and only the damage stat
        out += start + [fire("cast", TRIGGER)]
        for other in ("Seismic Slam", "Whirlwind", "Hammer of the Ancients", "Avalanche", "Leap", "Ground Stomp", "Rend", "Earth", "Earthquakes", ""):
            out += [(factor(other), "1")]
        for stat in ("attack_speed_pct", "dot_duration_seconds", "damage_dealt_pct", "summon_attack_speed_pct"):
            out += [(factor(TARGET, stat), "1")]
        # the stored roll is the number, at both ends and between; a Primal's top is the range's top
        for roll in (low, 225, high):
            out += [(T("clear"), None), (T("now", 10000), None), (T("wears", OWNER, 0), None), (T("value", OWNER, TARGET, STAT, roll), None),
                    fire("cast", TRIGGER), (factor(TARGET), g(1 + roll / 100))]
        # not worn, a roll in the bag, worn with no stored roll: nothing opens, nothing is read
        out += [(T("clear"), None), (T("now", 10000), None), fire("cast", TRIGGER), (factor(TARGET), "1")]
        out += [(T("clear"), None), (T("now", 10000), None), (T("value", OWNER, TARGET, STAT, 225), None), fire("cast", TRIGGER), (factor(TARGET), "1")]
        out += [(T("clear"), None), (T("now", 10000), None), (T("wears", OWNER, 0), None), fire("cast", TRIGGER), (factor(TARGET), "1")]
        # the item is taken off inside the window: the bonus goes with it
        out += start + [fire("cast", TRIGGER), (factor(TARGET), up), (T("clear"), None), (T("now", 10000), None), (factor(TARGET), "1")]
        # ONE roll of the item (stored under Earthquake's key): a Primal takes the top, an ordinary item rolls in the range
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (TARGET, STAT, high)), (T("roll", OWNER, 0), "power:%s:%s=%g;" % (TARGET, STAT, (low + high) / 2))]
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
            "no_rows": [],
            "the_window_is_2_s": [r[:8] + (2.0,) + r[9:] for r in rows],
            "the_window_is_4_s": [r[:8] + (4.0,) + r[9:] for r in rows],
            "no_condition": [r[:7] + ("",) + r[8:] for r in rows],
            "fired_by_another_skill": [r[:13] + ("Leap",) + r[14:] for r in rows],
            "fired_by_a_hit": [r[:12] + ("hit",) + r[13:] for r in rows],
            "the_wrong_target": [r[:3] + ("Avalanche",) + r[4:] for r in rows],
            "the_wrong_stat": [r[:4] + ("attack_speed_pct",) + r[5:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "a_fixed_number_not_a_range": [r[:6] + (r[5],) + r[7:] for r in rows],
            "an_internal_cooldown": [r[:15] + (5.0,) for r in rows],
            "a_chance": [r[:14] + (50.0,) + r[15:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_end_is_exclusive": real.replace("(situation.now - last->second) <= static_cast<std::uint32_t>(row.arg * 1000.0);",
                                                 "(situation.now - last->second) < static_cast<std::uint32_t>(row.arg * 1000.0);"),
            "the_window_never_ends": real.replace("(situation.now - last->second) <= static_cast<std::uint32_t>(row.arg * 1000.0);",
                                                  "true;"),
            "the_skill_is_not_checked": real.replace("std::find(row.fireSkills.begin(), row.fireSkills.end(), skill) == row.fireSkills.end()",
                                                     "false"),
            "any_event_fires": real.replace("if (row.fireOn != fireOn || !Owned(row, counts, situation, number))", "if (!Owned(row, counts, situation, number))"),
            "the_stored_roll_is_ignored": real.replace("number = found->value;", "number = row.min;"),
            "the_condition_is_ignored": real.replace("Owned(row, counts, situation, number) &&\n                Holds(row, situation))", "Owned(row, counts, situation, number))"),
            "the_percent_is_read_as_tenths": real.replace("factor *= 1.0 + pct / 100.0;\n        return factor;\n    }\n\n    // The multiplier of the `damage_by_missing_resource_pct`",
                                                          "factor *= 1.0 + pct / 10.0;\n        return factor;\n    }\n\n    // The multiplier of the `damage_by_missing_resource_pct`"),
            "a_skill_matches_by_its_start": real.replace("names.compare(from, to - from, skill) == 0", "names.compare(from, skill.size(), skill) == 0"),
            "the_roll_key_is_the_stat_alone": real.replace('"power:" + FirstSkill(row.skill) + ":" + row.stat', '"power:" + row.stat'),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
