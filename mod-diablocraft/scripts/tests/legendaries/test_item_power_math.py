"""Legendary build 2 (LoD HotA) bead 2, the K0-K2 rows and Ice Climbers (diablocraft-li0ie).

  * data/legendary_powers.csv gains eight rows: Magefist (Fire skills +[15-20]% to the hit's elemental bonus), Bracers of the First Men
    (Hammer of the Ancients attacks 50% faster and deals +[375-500]%), Remorseless (Hammer of the Ancients +[600-800]% while Wrath of the
    Berserker and Call of the Ancients are both active), Aquila Cuirass (50% less damage taken while the primary resource is at least the
    item's [90-95]% threshold, the lower the better) and Ice Climbers (immune to Freeze and Immobilize). Every number is read from its
    source and compared (the planner's item files and data.json, the legendaries sheet, the tooltip text the players see);
  * the generator refuses a row it cannot stand behind (an element that is not one, an immunity that is not on/off, a resource_above with
    no threshold of its own, a skills_active with no skills, ...);
  * the production rules (src/combat/dc_item_power_math.h: Holds for skills_active and resource_above, ElementSum, Immunities, Best and
    RollPowers, with SkillFactor and ReductionFactor) are compiled and driven with the generated rows;
  * mutants of those rules fail the same driver;
  * source-text guards that each new number has its one reader and that the player's own state is read before the item powers' lock
    (they prove the call is there, not that it runs; the C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-li0ie.md).
"""
import csv
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source  # noqa: E402
from split_sources import affixes_text  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_math/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
MIGRATION = MODULE / "data/sql/db-world/updates" / GENERATED.name
MAGEFIST, BRACERS, REMORSELESS, AQUILA, ICE = ("P41_Unique_Gloves_014", "P61_Unique_Bracer_105", "P72_Unique_Mighty_1H_102",
                                              "P4_Unique_Chest_012", "Unique_Boots_008_x1")
OWNERS = {MAGEFIST, BRACERS, REMORSELESS, AQUILA, ICE}
HOTA, WRATH, CALL = "Hammer of the Ancients", "Wrath of the Berserker", "Call of the Ancients"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def generated_rows():
    return [r for r in all_rows() if r[0] in OWNERS and not r[1]]


def planner(js, item_id):
    text = (REPO / "reference/d3planner" / js).read_text(encoding="utf-8")
    start = text.index('id: "%s"' % item_id)
    return text[start:text.index("},\n\n", start)]


def planner_json(item_id):
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("id") == item_id:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8")))
    assert len(found) == 1, item_id
    return found[0]


def tooltip(d3_id):
    """The power text the players see (dc_item_tooltip, generate_crafting.py)."""
    m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % re.escape(d3_id),
                  (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
    assert m, d3_id
    return m[1]


def numbers():
    """Every number of the five items, read from their sources."""
    magefist = planner("item_hands.js", MAGEFIST)
    assert "Fire skills deal %d%% increased damage." in magefist
    mf = re.search(r"min: (\d+), max: (\d+)", magefist)
    bracers = planner("item_wrists.js", BRACERS)
    bf = re.search(r'format: "Hammer of the Ancients attacks (\d+)%% faster and deals %d%% increased damage.", min: (\d+), max: (\d+)', bracers)
    sheet = next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == "Bracers of the First Men")
    assert sheet == "Hammer of the Ancients attacks %s%% faster and deals [%s - %s]%% increased damage." % (bf[1], bf[2], bf[3]), sheet
    remorseless = planner_json(REMORSELESS)["required"]["custom"]
    assert remorseless["format"] == ("While both Wrath of the Berserker and Call of the Ancients are active, Hammer of the Ancients deals "
                                     "%d%% increased damage."), remorseless
    aquila = planner("item_torso.js", AQUILA)
    aq = re.search(r'format: "While above %d%% primary resource, all damage taken is reduced by (\d+)%%.", min: (\d+), max: (\d+), best: "(\w+)"', aquila)
    ice = planner("item_feet.js", ICE)
    assert 'format: "Gain immunity to Freeze and Immobilize effects."' in ice
    return {
        "magefist": (float(mf[1]), float(mf[2])),
        "bracers_speed": float(bf[1]), "bracers": (float(bf[2]), float(bf[3])),
        "remorseless": (float(remorseless["min"]), float(remorseless["max"])),
        "aquila_reduction": float(aq[1]), "aquila": (float(aq[2]), float(aq[3])), "aquila_best": aq[4],
    }


class Table(unittest.TestCase):
    def test_rows_are_their_sources_numbers(self):
        n = numbers()
        self.assertEqual(((15, 20), 50, (375, 500), (600, 800), 50, (90, 95), "min"),
                         (n["magefist"], n["bracers_speed"], n["bracers"], n["remorseless"], n["aquila_reduction"], n["aquila"], n["aquila_best"]))
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        want = {
            (MAGEFIST, 0, "element", "fire", "damage_pct", *n["magefist"], *blank),
            (BRACERS, 0, "skill", HOTA, "attack_speed_pct", n["bracers_speed"], n["bracers_speed"], *blank),
            (BRACERS, 0, "skill", HOTA, "damage_increase_pct", *n["bracers"], *blank),
            (REMORSELESS, 0, "skill", HOTA, "damage_increase_pct", *n["remorseless"], "skills_active", 0.0, "%s;%s" % (WRATH, CALL), 0.0, 0,
             "", "", 100.0, 0.0),
            (AQUILA, 0, "player", "", "resource_threshold_pct", *n["aquila"], *blank),
            (AQUILA, 0, "player", "", "damage_reduction_pct", n["aquila_reduction"], n["aquila_reduction"], "resource_above", 0.0, "", 0.0, 0,
             "", "", 100.0, 0.0),
            (ICE, 0, "immune", "", "freeze", 1.0, 1.0, *blank),
            (ICE, 0, "immune", "", "root", 1.0, 1.0, *blank),
        }
        self.assertEqual(want, set(generated_rows()))
        self.assertEqual(8, len(generated_rows()))

    def test_the_tooltip_shows_each_rolled_range(self):
        # the text the tooltip puts the stored roll into (rolledPower): the row's range, as the generator wrote it
        n = numbers()
        for owner, (low, high) in ((MAGEFIST, n["magefist"]), (BRACERS, n["bracers"]), (REMORSELESS, n["remorseless"]), (AQUILA, n["aquila"])):
            self.assertIn("%g–%g%%" % (low, high), tooltip(owner), owner)
        self.assertIn("Fire skills", tooltip(MAGEFIST))
        self.assertIn("%g%% faster" % n["bracers_speed"], tooltip(BRACERS))
        self.assertIn("Wrath of the Berserker and Call of the Ancients", tooltip(REMORSELESS))
        self.assertIn("reduced by %g%%" % n["aquila_reduction"], tooltip(AQUILA))
        self.assertEqual("Gain immunity to Freeze and Immobilize effects.", tooltip(ICE))

    def test_the_owners_are_the_pool_versions(self):
        pool = {r["d3_id"]: r for r in read_csv("data/d3/base_items.csv") if r["pool_version"] == "yes"}
        self.assertEqual(OWNERS, OWNERS & set(pool))
        self.assertEqual({"Magefist", "Bracers of the First Men", "Remorseless", "Aquila Cuirass", "Ice Climbers"}, {pool[o]["d3_name"] for o in OWNERS})
        # the sheet carries the older Remorseless (P67, [200 - 250]%): the pool's is P72 and its tooltip says 600-800
        old = next(r["legendary_power_text"] for r in read_csv("data/d3/barbarian_legendaries.csv") if r["item_name"] == "Remorseless")
        self.assertIn("[200 - 250]%", old)
        self.assertEqual("no", next(r["pool_version"] for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == "P67_Unique_Mighty_1H_102"))

    def test_the_earlier_table_stays_as_shipped(self):
        applied = (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        self.assertIn("db-world/updates/legendary_powers_0004_table.sql", applied)
        self.assertNotIn(GENERATED.name, applied)
        self.assertNotIn("Unique_Boots_008_x1", (MODULE / "data/sql/db-world/updates/legendary_powers_0004_table.sql").read_text(encoding="utf-8"))

    def test_every_row_has_a_source_and_a_note(self):
        for row in read_csv("data/legendary_powers.csv"):
            if row["owner"] in OWNERS:
                self.assertTrue(row["source"].strip() and row["note"].strip(), (row["owner"], row["stat"]))

    def test_generator_refuses_a_row_it_cannot_stand_behind(self):
        base = {"owner": MAGEFIST, "pieces": "", "kind": "element", "skill": "fire", "stat": "damage_pct", "value_min": "15", "value_max": "20",
                "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                "icd_seconds": "", "source": "x", "note": ""}
        immune = dict(base, owner=ICE, kind="immune", skill="", stat="freeze", value_min="1", value_max="1")
        remorseless = dict(base, owner=REMORSELESS, kind="skill", skill=HOTA, stat="damage_increase_pct", value_min="600", value_max="800",
                           cond="skills_active", cond_skills="%s;%s" % (WRATH, CALL))
        threshold = dict(base, owner=AQUILA, kind="player", skill="", stat="resource_threshold_pct", value_min="90", value_max="95")
        aquila = dict(base, owner=AQUILA, kind="player", skill="", stat="damage_reduction_pct", value_min="50", value_max="50", cond="resource_above")
        speed = dict(base, owner=BRACERS, kind="skill", skill=HOTA, stat="attack_speed_pct", value_min="50", value_max="50")
        bad = {
            "an element in capitals": [dict(base, skill="Fire")],
            "an element that is not one": [dict(base, skill="shadow")],
            "an element row with no element": [dict(base, skill="")],
            "an element stat nothing reads": [dict(base, stat="attack_speed_pct")],
            "an element of a set that rolls": [dict(base, owner="Wrath of the Wastes", pieces="2")],
            "an immunity that is not on or off": [dict(immune, value_min="2", value_max="2")],
            "an immunity that is not one": [dict(immune, stat="stun")],
            "an immunity with a condition": [dict(immune, cond="triggered", cond_arg="3", fire_on="kill")],
            "an immunity that fires": [dict(immune, fire_on="kill")],
            "an immunity that names a skill": [dict(immune, skill="fire")],
            "skills_active with seconds": [dict(remorseless, cond_arg="3")],
            "skills_active with no skills": [dict(remorseless, cond_skills="")],
            "skills_active of a skill that does not exist": [dict(remorseless, cond_skills="%s;Not A Skill" % WRATH)],
            "resource_above with no threshold of its own": [aquila],
            "resource_above with another item's threshold": [dict(threshold, owner=MAGEFIST), aquila],
            "resource_above with seconds": [threshold, dict(aquila, cond_arg="1")],
            "resource_above with skills": [threshold, dict(aquila, cond_skills=WRATH)],
            "a threshold above 100": [dict(threshold, value_max="120"), aquila],
            "a threshold under a condition": [dict(threshold, cond="triggered", cond_arg="3", fire_on="kill"), aquila],
            "an attack speed on a skill that does not exist": [dict(speed, skill="Not A Skill")],
            "an attack speed on the player": [dict(speed, kind="player", skill="")],
        }
        for name, sheet in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of(sheet)
        self.assertEqual([(MAGEFIST, 0, "element", "fire", "damage_pct", 15.0, 20.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)], self.rows_of([base]))
        self.assertEqual(1, len(self.rows_of([immune])))
        self.assertEqual(1, len(self.rows_of([remorseless])))
        self.assertEqual(2, len(self.rows_of([threshold, aquila])))
        self.assertEqual(1, len(self.rows_of([speed])))

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
            return [row for row in generator.rows(module) if row[2] != "potion"]  # the potions' own rows (87qlt)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itempowermath-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self):
        """[(command line, expected output line or None)]: worked out from the sources' words and numbers, not from the code."""
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        n = numbers()
        out = [(T("row", *r), None) for r in all_rows()]
        assert all(len(c[0].split("\t")) == 17 for c in out), "row width"
        clear = [(T("clear"), None)]
        g = lambda x: "%g" % x  # noqa: E731

        # Magefist: Fire skills' hits add the item's own roll to the elemental bonus; no other element; nothing unworn or unrolled
        low, high = n["magefist"]
        out += clear + [(T("element", "fire", "damage_pct"), "0"), (T("wears", MAGEFIST), None), (T("element", "fire", "damage_pct"), "0")]
        for roll in (low, 17, high):
            out += clear + [(T("wears", MAGEFIST), None), (T("value", MAGEFIST, "fire", "damage_pct", roll), None)]
            out += [(T("element", e, "damage_pct"), g(roll if e == "fire" else 0)) for e in generator.ELEMENTS]
            out += [(T("factor", HOTA, "damage_increase_pct"), "1")]                  # not a multiplier of its own
        out += clear + [(T("value", MAGEFIST, "fire", "damage_pct", 17), None), (T("element", "fire", "damage_pct"), "0")]   # rolled but not worn

        # Bracers of the First Men: Hammer of the Ancients 1.5 times as fast, x(1 + roll/100); no other skill
        speed = 1 + n["bracers_speed"] / 100
        out += clear + [(T("factor", HOTA, "attack_speed_pct"), "1"), (T("wears", BRACERS), None), (T("factor", HOTA, "attack_speed_pct"), g(speed)),
                        (T("factor", "Frenzy", "attack_speed_pct"), "1"), (T("factor", "Whirlwind", "attack_speed_pct"), "1"),
                        (T("factor", HOTA, "damage_increase_pct"), "1")]                  # the range has no stored roll yet: no damage
        for roll in (*n["bracers"], 420):
            out += clear + [(T("wears", BRACERS), None), (T("value", BRACERS, HOTA, "damage_increase_pct", roll), None),
                            (T("factor", HOTA, "damage_increase_pct"), g(1 + roll / 100)), (T("factor", "Frenzy", "damage_increase_pct"), "1"),
                            (T("factor", HOTA, "attack_speed_pct"), g(speed))]

        # Remorseless: only while both buffs are up, at the item's roll; it multiplies with the Bracers' own multiplier
        for active, on in (((), False), ((WRATH,), False), ((CALL,), False), ((WRATH, CALL), True), ((WRATH, CALL, "Frenzy"), True),
                           (("Frenzy", "Leap"), False)):
            for roll in n["remorseless"]:
                out += clear + [(T("wears", REMORSELESS), None), (T("value", REMORSELESS, HOTA, "damage_increase_pct", roll), None)]
                out += [(T("active", a), None) for a in active]
                out += [(T("factor", HOTA, "damage_increase_pct"), g(1 + roll / 100 if on else 1)), (T("factor", "Whirlwind", "damage_increase_pct"), "1")]
        out += clear + [(T("active", WRATH), None), (T("active", CALL), None), (T("value", REMORSELESS, HOTA, "damage_increase_pct", 700), None),
                        (T("factor", HOTA, "damage_increase_pct"), "1")]                    # both up, the item in the bag
        out += clear + [(T("active", WRATH), None), (T("active", CALL), None), (T("wears", REMORSELESS), None), (T("wears", BRACERS), None),
                        (T("value", REMORSELESS, HOTA, "damage_increase_pct", 700), None), (T("value", BRACERS, HOTA, "damage_increase_pct", 400), None),
                        (T("factor", HOTA, "damage_increase_pct"), g((1 + 700 / 100) * (1 + 400 / 100)))]

        # Aquila Cuirass: 50% less damage taken at or above the item's own threshold; below it, or with no threshold stored, nothing
        cut = 1 - n["aquila_reduction"] / 100
        for threshold in (*n["aquila"], 92):
            for resource in (0, threshold - 0.01, threshold, threshold + 0.01, 100):
                out += clear + [(T("wears", AQUILA), None), (T("value", AQUILA, "", "resource_threshold_pct", threshold), None),
                                (T("resource", resource), None), (T("reduction"), g(cut if resource >= threshold else 1))]
        out += clear + [(T("wears", AQUILA), None), (T("resource", 100), None), (T("reduction"), "1")]                     # no threshold stored
        out += clear + [(T("value", AQUILA, "", "resource_threshold_pct", 90), None), (T("resource", 100), None), (T("reduction"), "1")]   # not worn

        # Ice Climbers: immune to freeze and root while worn, nothing otherwise
        out += clear + [(T("immune"), ""), (T("wears", MAGEFIST), None), (T("immune"), ""), (T("wears", ICE), None), (T("immune"), "freeze;root;")]

        # a Primal stores the best end: the top of a damage range, the bottom of Aquila's threshold; a fixed row stores nothing
        out += [(T("roll", MAGEFIST, 1), "power:fire:damage_pct=%g;" % n["magefist"][1]),
                (T("roll", MAGEFIST, 0), "power:fire:damage_pct=%g;" % (sum(n["magefist"]) / 2)),
                (T("roll", BRACERS, 1), "power:%s:damage_increase_pct=%g;" % (HOTA, n["bracers"][1])),
                (T("roll", REMORSELESS, 1), "power:%s:damage_increase_pct=%g;" % (HOTA, n["remorseless"][1])),
                (T("roll", AQUILA, 1), "power::resource_threshold_pct=%g;" % min(n["aquila"])),
                (T("roll", AQUILA, 0), "power::resource_threshold_pct=%g;" % (sum(n["aquila"]) / 2)),
                (T("roll", ICE, 1), "")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_sources(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 90)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "one_skill_is_enough": real.replace("std::all_of(row.condSkills.begin()", "std::any_of(row.condSkills.begin()"),
            "skills_active_always_holds": real.replace('if (row.cond == "skills_active")\n            return !row.condSkills.empty() &&',
                                                       'if (row.cond == "skills_active")\n            return true ||'),
            "the_threshold_itself_is_not_enough": real.replace("situation.resourcePct >= pct;", "situation.resourcePct > pct;"),
            "no_threshold_holds": real.replace("return Threshold(row.owner, situation, pct) && situation.resourcePct >= pct;",
                                               "Threshold(row.owner, situation, pct);\n            return situation.resourcePct >= pct;"),
            "the_threshold_of_another_stat": real.replace('value.stat == "resource_threshold_pct"', 'value.stat == "damage_reduction_pct"'),
            "the_primal_threshold_is_the_top": real.replace('return row.stat == "resource_threshold_pct" || row.stat == "damage_generation_cut_pct" ? row.min : row.max;', "return row.max;"),
            "every_primal_is_the_bottom": real.replace('return row.stat == "resource_threshold_pct" || row.stat == "damage_generation_cut_pct" ? row.min : row.max;', "return row.min;"),
            "every_element_is_fire": real.replace('ActiveValues(rows, counts, "element", element, stat, situation)',
                                                  'ActiveValues(rows, counts, "element", "fire", stat, situation)'),
            "an_unworn_immunity": real.replace('if (row.kind == "immune" && !ActiveValues(rows, counts, "immune", "", row.stat, situation).empty())',
                                               'if (row.kind == "immune")'),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
