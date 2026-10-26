"""Consecration and its five runes (src/classes/crusader/dc_crusader_consecration.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_consecration/harness.cpp compiles the real dc_crusader_consecration.h
    with the sheets' own rune names and numbers: each rune name is its rune; the ground reaches its radius and no further;
    Aegis Purgatory catches an enemy that went through the edge either way and not one that kept its side; Bed of Nails deals
    the sheet's share of the Thorns; Fearful's roll procs under the chance. Seven mutations planted in a scratch copy (two runes
    share a name, the ground has no edge, the edge is crossed only outward, an enemy keeping its side is caught, the share is
    not divided by a hundred, the roll is inclusive, the roll is not checked) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_consecration.cpp reads by name is a row of
    crusader_skill_values.csv for Consecration (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: a 20 yard ground for 10 seconds healing 32185 a second, Aegis Purgatory 5 seconds,
    Bed of Nails 100% of the Thorns, Bathed in Light 24 yards and 48278, Shattered Ground 155%, Fearful 100% for 3 seconds. The
    tunables it reads are rows of data/tunables/crusader.csv: the tick (one second, the sheets' "per second") and the barrier's
    check interval, a PLACEHOLDER for the designer with the code's floor.
  * **The ground deals no damage on the cast.** BasePct answers 0 for the skill and every rune.

What it does not prove: anything on a running server, and whether the stock Fear it uses ends when the enemy takes damage.

    python mod-diablocraft/scripts/tests/classes/test_crusader_consecration.py
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
HEADER = "src/classes/crusader/dc_crusader_consecration.h"
SOURCES = [HEADER, "tests/crusader_consecration/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_consecration.cpp"
SKILL = "Consecration"


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
    binary = harness_env.build([MODULE / "tests/crusader_consecration/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "radius_yards"), value("Bed of Nails", "thorns_share_pct"), value("Fearful", "proc_chance_pct")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 15, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        crossed = "return wasInside != OnGround(distance, radius);"
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Fearful;", "return Rune::BedOfNails;")),
            ("the ground has no edge", (HEADER, "return radius > 0 && distance <= radius;", "return radius > 0;")),
            ("the edge is crossed only outward", (HEADER, crossed, "return wasInside && !OnGround(distance, radius);")),
            ("an enemy keeping its side is caught", (HEADER, crossed, "return true;")),
            ("the share is not divided by a hundred", (HEADER, "thorns * sharePct / 100.0", "thorns * sharePct")),
            ("the roll is inclusive", (HEADER, "return roll < chancePct;", "return roll <= chancePct;")),
            ("the roll is not checked", (HEADER, "return roll < chancePct;", "return chancePct > 0;")),
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
        self.assertEqual(runes(), ["Aegis Purgatory", "Bed of Nails", "Bathed in Light", "Shattered Ground", "Fearful"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "radius_yards", "duration_seconds", "heal_per_second_life")],
                         [30, 20, 10, 32185])
        self.assertEqual(value("Aegis Purgatory", "duration_seconds"), 5)
        self.assertEqual(value("Bed of Nails", "thorns_share_pct"), 100)
        self.assertEqual((value("Bathed in Light", "radius_yards"), value("Bathed in Light", "heal_per_second_life")), (24, 48278))
        self.assertEqual(value("Shattered Ground", "damage_pct"), 155)
        self.assertEqual((value("Fearful", "proc_chance_pct"), value("Fearful", "fear_duration_seconds")), (100, 3))

    def test_the_tunables(self):
        rows = tunables()
        tick = rows["consecration_tick_seconds"]
        self.assertEqual((tick["d3_value"], tick["value"]), ("1", ""))
        self.assertNotIn("PLACEHOLDER", tick["notes"])
        check = rows["consecration_barrier_check_seconds"]
        # The designer's final value (q-1021-21), no longer a placeholder; the code takes it as it is, above its 0.1 floor.
        self.assertEqual((check["d3_value"], check["value"]), ("", "0.25"))
        self.assertNotIn("PLACEHOLDER", check["notes"])
        self.assertGreater(float(check["value"]), float(re.search(r"CheckFloorSeconds = ([0-9.]+);", CODE.read_text(encoding="utf-8")).group(1)))
        text = CODE.read_text(encoding="utf-8")
        self.assertIn("std::max(CheckFloorSeconds, Tune(\"consecration_barrier_check_seconds\"))", re.sub(r"\s+", " ", text))
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)),
                         {"consecration_tick_seconds", "consecration_barrier_check_seconds"})

    def test_every_token_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"radius_yards", "duration_seconds", "heal_per_second_life", "thorns_share_pct", "damage_pct",
                                  "proc_chance_pct", "fear_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "radius_yards"), ("", "duration_seconds"), ("", "heal_per_second_life"),
                            ("Aegis Purgatory", "duration_seconds"), ("Bed of Nails", "thorns_share_pct"),
                            ("Bathed in Light", "radius_yards"), ("Bathed in Light", "heal_per_second_life"),
                            ("Shattered Ground", "damage_pct"), ("Fearful", "proc_chance_pct"),
                            ("Fearful", "fear_duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)
        # The ground's radius, time and heal reach every rune: on its own record or by inheritance.
        for rune in runes():
            for token in ("radius_yards", "duration_seconds", "heal_per_second_life"):
                self.assertIn((rune, token, ""), mapped, (rune, token))


if __name__ == "__main__":
    unittest.main()
