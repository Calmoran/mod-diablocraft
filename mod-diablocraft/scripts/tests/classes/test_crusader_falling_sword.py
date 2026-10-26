"""Falling Sword and its five runes (src/classes/crusader/dc_crusader_falling_sword.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_falling_sword/harness.cpp compiles the real
    dc_crusader_falling_sword.h with the sheets' own rune names and numbers: each rune name is its rune; the cooldown waits
    for the four runes that leave something behind and for nothing else; Rapid Descent takes a second off for each enemy
    hit, stops at the floor and never raises a shorter cooldown; a rate a second paid in ticks adds up to the rate over the
    seconds; the storm's pick stays inside the enemies. Thirteen mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_falling_sword.cpp reads by name is a row of
    crusader_skill_values.csv for Falling Sword, the generated value map says whose record holds it, and the numbers are the
    researched ones: 25 Wrath and a 30 second cooldown, 1700% in 14 yards, Superheated 310% for 6 seconds, Part the Clouds
    605% for 5 seconds with a 2 second stun, Rise Brothers 3 avatars at 280% for 5 seconds, Rapid Descent 1 second to a floor
    of 10, Flurry 230% for 5 seconds. Every tunable it reads is a row of data/tunables/crusader.csv with the power file's
    number (Power/X1_Crusader_FallingSword.pow) as its D3 value and none of the designer's.
  * **The leap is a record.** skill_targeting.csv gives Falling Sword a ground point (reach 80, area 14); the six generated
    records jump to it (JUMP_DEST, Leap's shape), the client's Spell.dbc and the newest full spell render say the same.
  * **The landing's hit is the skill's.** BasePct is the skill's 1700 for every rune (a rune's own damage_pct is its effect's).

What it does not prove: anything on a running server, how the client draws the leap, or that a jump of 80 yards lands.

    python mod-diablocraft/scripts/tests/classes/test_crusader_falling_sword.py
"""

import csv
import re
import struct
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/crusader/dc_crusader_falling_sword.h"
SOURCES = [HEADER, "src/classes/crusader/dc_crusader_dot.h", "tests/crusader_falling_sword/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_falling_sword.cpp"
UPDATES = MODULE / "data/sql/db-world/updates"
SKILL = "Falling Sword"
POW = "Power/X1_Crusader_FallingSword.pow"
JUMP_DEST = 42


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
    return {r["name"]: r for r in read(MODULE / "data/tunables/crusader.csv") if r["name"].startswith("falling_sword_")}


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
    binary = harness_env.build([MODULE / "tests/crusader_falling_sword/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "cooldown_seconds"), value("Rapid Descent", "cooldown_reduction_seconds"),
               value("Rapid Descent", "min_cooldown_seconds"), value("Superheated", "damage_pct"),
               value("Superheated", "duration_seconds"),
               float(tunables()["falling_sword_superheated_tick_seconds"]["d3_value"])] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 18, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Flurry;", "return Rune::RapidDescent;")),
            ("Flurry's cooldown does not wait", (HEADER, "rune == Rune::PartTheClouds || rune == Rune::RiseBrothers ||\n                            rune == Rune::Flurry;", "rune == Rune::PartTheClouds || rune == Rune::RiseBrothers;")),
            ("Rapid Descent waits too", (HEADER, "bool const leaves = rune == Rune::Superheated", "bool const leaves = rune == Rune::RapidDescent || rune == Rune::Superheated")),
            ("a wait with no duration", (HEADER, "return leaves && durationSeconds > 0 ? durationSeconds : 0.0;", "return leaves ? durationSeconds : 0.0;")),
            ("every rune cuts", (HEADER, "if (rune != Rune::RapidDescent || perEnemySeconds <= 0)", "if (perEnemySeconds <= 0)")),
            ("the cut passes the floor", (HEADER, "std::max(std::min(wholeSeconds, floorSeconds), wholeSeconds - enemiesHit * perEnemySeconds)", "wholeSeconds - enemiesHit * perEnemySeconds")),
            ("a short cooldown is raised to the floor", (HEADER, "std::max(std::min(wholeSeconds, floorSeconds),", "std::max(floorSeconds,")),
            ("each enemy cuts one", (HEADER, "wholeSeconds - enemiesHit * perEnemySeconds)", "wholeSeconds - perEnemySeconds)")),
            ("a tick pays the whole rate", (HEADER, "Dot::TickPct(ratePerSecond * seconds, ticks)", "Dot::TickPct(ratePerSecond * seconds, 1)")),
            ("a negative rate pays", (HEADER, "return ratePerSecond > 0 ? Dot::TickPct", "return ratePerSecond != 0 ? Dot::TickPct")),
            ("the roll can pick past the end", (HEADER, "std::min(count - 1, static_cast<std::size_t>(std::max(0.0, roll) * count))", "static_cast<std::size_t>(std::max(0.0, roll) * count)")),
            ("nobody under the storm is picked", (HEADER, "if (!count)\n            return std::nullopt;", "if (!count)\n            return 0;")),
            ("the first enemy is never picked", (HEADER, "static_cast<std::size_t>(std::max(0.0, roll) * count)", "static_cast<std::size_t>(std::max(0.0, roll) * count) + 1")),
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
        self.assertEqual(runes(), ["Superheated", "Part the Clouds", "Rise Brothers", "Rapid Descent", "Flurry"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "cooldown_seconds"), value("", "damage_pct"),
                          value("", "radius_yards")], [25, 30, 1700, 14])
        self.assertEqual((value("Superheated", "duration_seconds"), value("Superheated", "damage_pct")), (6, 310))
        self.assertEqual((value("Part the Clouds", "duration_seconds"), value("Part the Clouds", "damage_pct"),
                          value("Part the Clouds", "stun_duration_seconds")), (5, 605, 2))
        self.assertEqual((value("Rise Brothers", "pet_count"), value("Rise Brothers", "duration_seconds"),
                          value("Rise Brothers", "damage_pct")), (3, 5, 280))
        self.assertEqual((value("Rapid Descent", "cooldown_reduction_seconds"), value("Rapid Descent", "min_cooldown_seconds")),
                         (1, 10))
        self.assertEqual((value("Flurry", "damage_pct"), value("Flurry", "duration_seconds")), (230, 5))

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "cooldown_reduction_seconds", "min_cooldown_seconds", "duration_seconds",
                                  "stun_duration_seconds", "pet_count"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_pct"), ("Superheated", "damage_pct"), ("Superheated", "duration_seconds"),
                            ("Part the Clouds", "damage_pct"), ("Part the Clouds", "stun_duration_seconds"),
                            ("Part the Clouds", "duration_seconds"), ("Rise Brothers", "pet_count"),
                            ("Rise Brothers", "duration_seconds"), ("Rise Brothers", "damage_pct"),
                            ("Rapid Descent", "cooldown_reduction_seconds"), ("Rapid Descent", "min_cooldown_seconds"),
                            ("Flurry", "damage_pct"), ("Flurry", "duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "falling_sword_superheated_tick_seconds": "0.3",          # SF_12
        "falling_sword_superheated_radius_yards": "14",           # SF_17
        "falling_sword_part_the_clouds_strike_seconds": "0.8",    # SF_20
        "falling_sword_part_the_clouds_radius_yards": "24",       # SF_22
        "falling_sword_flurry_tick_seconds": "0.25",              # SF_43
        "falling_sword_flurry_radius_yards": "15",                # SF_42
    }

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        self.assertEqual(set(rows), set(self.NUMBERS))
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertIn(POW, rows[name]["notes"])
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))


class TheLeap(unittest.TestCase):
    IDS = (85420, 85524, 85525, 85526, 85527, 85528)

    def test_the_sheet_gives_the_skill_a_ground_point(self):
        rows = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["target_type"], row["range_yards"], row["radius_yards"], row["source_spell_id"]),
                         ("ground_point_aoe", "80", "14", "6544"))

    def test_the_generated_records_and_the_newest_render_jump_to_it(self):
        generated = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        renders = [p for p in sorted(UPDATES.glob("combat_0*.sql")) if "INSERT INTO `spell_dbc`" in p.read_text(encoding="utf-8")]
        render = renders[-1].read_text(encoding="utf-8")
        ids = {r["spell_id"] for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        self.assertEqual(ids, {str(i) for i in self.IDS})
        for text in (generated, render):
            for spell in self.IDS:
                self.assertIn(f"INSERT INTO dc_spell_targeting VALUES ({spell},'ground_point_aoe','NUMERIC',80.0,14.0,0.0);", text)

    def test_the_client_records_are_jumps_and_the_others_are_not_touched(self):
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if not dbc.is_file():
            raise unittest.SkipTest("no client Spell.dbc")
        data = dbc.read_bytes()
        _magic, count, fields, size, _strings = struct.unpack("<4sIIII", data[:20])
        found = set()
        for i in range(count):
            row = struct.unpack_from("<%dI" % fields, data, 20 + i * size)
            if row[0] in self.IDS:
                # Effect_1 is SPELL_EFFECT_JUMP_DEST: the Crusader leaps to the aimed point.
                self.assertEqual(row[71], JUMP_DEST, row[0])
                found.add(row[0])
        self.assertEqual(found, set(self.IDS))


if __name__ == "__main__":
    unittest.main()
