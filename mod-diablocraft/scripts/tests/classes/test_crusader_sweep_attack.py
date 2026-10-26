"""Sweep Attack and its five runes (src/classes/crusader/dc_crusader_sweep_attack.h and .cpp, and the burn rule).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_sweep_attack/harness.cpp compiles the real dc_crusader_sweep_attack.h
    and dc_crusader_dot.h with the sheets' own rune names and numbers: each rune name is its rune; the half circle takes the
    enemies the core's cone did not, inside the reach and the arc and never one the cone struck; Holy Shock heals for each
    enemy hit; the fire has the ticks that fit its seconds, each tick a share of the total, and none without a tick length.
    Seven mutations planted in a scratch copy (two runes share a name, the sweep takes an enemy past the reach, takes one the
    cone struck, takes one outside the arc, the heal is once, the ticks round up, the ticks are not divided) must each make it
    fail.
  * **The code reads what the sheets state.** Every token dc_crusader_sweep_attack.cpp reads by name is a row of
    crusader_skill_values.csv for Sweep Attack (or the rune that states it), the generated value map says whose record
    holds it, and the numbers are the researched ones: 480% weapon damage over 18 yards for 20 Wrath, Blazing Sweep 120% over
    2 seconds, Holy Shock 5364 Life, Trip Attack 50% for 2 seconds, Inspiring Sweep 20% for 3 seconds. Every tunable it reads
    is a row of data/tunables/crusader.csv: the power file's 180 degrees and pull of 1 yard, and the fire's tick length,
    The designer's 0.5 seconds (card q-1021-08): four hits of 30%.
  * **The skills that need a weapon** in the code are the skills whose tooltip says "Requires Weapon".

What it does not prove: anything on a running server. The half circle, the pull, the fire, the Life, the stun and the Armor
are docs/test-diablocraft-7t4gv.6.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_crusader_sweep_attack.py
"""

import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/crusader/dc_crusader_sweep_attack.h"
DOT = "src/classes/crusader/dc_crusader_dot.h"
SOURCES = [HEADER, DOT, "tests/crusader_sweep_attack/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_sweep_attack.cpp"
SKILL = "Sweep Attack"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "crusader_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "crusader_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "crusader.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/crusader_sweep_attack/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "radius_yards"), value("Holy Shock", "heal_per_hit_life"), value("Blazing Sweep", "damage_pct"),
               value("Blazing Sweep", "dot_duration_seconds")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::TripAttack;", "return Rune::HolyShock;")),
            ("the sweep takes an enemy past the reach", (HEADER, "reach > 0 && distance <= reach;", "reach > 0 && distance <= reach + 1;")),
            ("the sweep takes one the cone struck", (HEADER, "return !alreadyStruck && inArc", "return inArc")),
            ("the sweep takes one outside the arc", (HEADER, "return !alreadyStruck && inArc && reach > 0", "return !alreadyStruck && reach > 0")),
            ("the heal is once", (HEADER, "return perEnemy > 0 ? perEnemy * enemies : 0.0;", "return perEnemy > 0 && enemies ? perEnemy : 0.0;")),
            ("the ticks round up", (DOT, "std::floor(seconds / tickSeconds + 1e-9)", "std::ceil(seconds / tickSeconds)")),
            ("the ticks are not divided", (DOT, "return ticks ? totalPct / ticks : 0.0;", "return ticks ? totalPct : 0.0;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), ["Gathering Sweep", "Blazing Sweep", "Holy Shock", "Trip Attack", "Inspiring Sweep"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("cost_resource", "radius_yards", "damage_pct")], [20, 18, 480])
        self.assertEqual((value("Blazing Sweep", "damage_pct"), value("Blazing Sweep", "dot_duration_seconds")), (120, 2))
        self.assertEqual(value("Holy Shock", "heal_per_hit_life"), 5364)
        self.assertEqual((value("Trip Attack", "proc_chance_pct"), value("Trip Attack", "stun_duration_seconds")), (50, 2))
        self.assertEqual((value("Inspiring Sweep", "armor_pct"), value("Inspiring Sweep", "duration_seconds")), (20, 3))

    def test_the_tunables(self):
        rows = tunables()
        self.assertEqual((rows["sweep_attack_arc_degrees"]["d3_value"], rows["sweep_attack_arc_degrees"]["value"]), ("180", ""))
        self.assertIn("SF_27", rows["sweep_attack_arc_degrees"]["notes"])
        self.assertEqual((rows["sweep_attack_pull_yards"]["d3_value"], rows["sweep_attack_pull_yards"]["value"]), ("1", ""))
        self.assertIn("SF_25", rows["sweep_attack_pull_yards"]["notes"])
        # The designer's answer (card q-1021-08): the fire ticks every 0.5 seconds; his column is filled and the placeholder mark is gone.
        fire = rows["sweep_attack_burn_tick_seconds"]
        self.assertEqual((fire["d3_value"], fire["value"]), ("", "0.5"))
        self.assertNotIn("PLACEHOLDER", fire["notes"])
        self.assertIn("q-1021-08", fire["notes"])

    def test_blazing_sweep_ticks_every_half_second_for_four_hits_of_thirty_percent(self):
        tick = tune("sweep_attack_burn_tick_seconds")
        self.assertEqual(tick, 0.5)
        seconds, total = value("Blazing Sweep", "dot_duration_seconds"), value("Blazing Sweep", "damage_pct")
        # The harness's own rule on these numbers: the ticks that fit and each one's share.
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-500:])
        self.assertEqual(int(seconds / tick + 1e-9), 4)
        self.assertEqual(total / int(seconds / tick + 1e-9), 30)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {"sweep_attack_arc_degrees", "sweep_attack_pull_yards", "sweep_attack_burn_tick_seconds"})
        for name in read_tunables:
            self.assertIn(name, tunables())
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "dot_duration_seconds", "heal_per_hit_life", "proc_chance_pct",
                                  "stun_duration_seconds", "armor_pct", "duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("Blazing Sweep", "damage_pct"), ("Blazing Sweep", "dot_duration_seconds"),
                            ("Holy Shock", "heal_per_hit_life"), ("Trip Attack", "proc_chance_pct"),
                            ("Trip Attack", "stun_duration_seconds"), ("Inspiring Sweep", "armor_pct"),
                            ("Inspiring Sweep", "duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token, "")]["origin"], "own")
        # The skill's hit is the base record's for every rune: Blazing Sweep's own damage_pct is the fire's, not the hit.
        self.assertEqual(mapped[("Blazing Sweep", "damage_pct", "")]["origin"], "own")
        self.assertEqual(value("", "damage_pct"), 480)

    def test_the_skills_that_need_a_weapon_are_the_sheets(self):
        code = (MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8")
        listed = set(re.findall(r'"([A-Za-z\' ]+)"', re.search(r"NeedWeapon = \{([^}]*)\}", code)[1]))
        sheet = {r["skill_name"] for r in read(D3 / "crusader_skills.csv") if "Requires Weapon" in r["full_tooltip_text"]}
        self.assertEqual(listed, sheet)
        self.assertEqual(sheet, {"Sweep Attack"})


if __name__ == "__main__":
    unittest.main()
