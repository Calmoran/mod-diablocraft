"""Smite and its five runes (src/classes/crusader/dc_crusader_smite.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_smite/harness.cpp compiles the real dc_crusader_smite.h and feeds
    it the sheets' own rune names, chain radius (20 yards), counts (3 additional enemies, 5 with Surge), Shared Fate's 15
    yards and the binding's length: each rune name is its rune; the chains take the nearest enemies inside the radius, up to
    the count, nearest first, and never one past the radius; a pair has moved apart when its gap grew by the distance since
    the binding; a binding lasts to its last millisecond. Six mutations planted in a scratch copy (two runes share a name, the
    chains take the farthest, the radius is ignored, the count is ignored, the gap is read as the distance itself, a binding
    outlasts its end) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_smite.cpp reads by name is a row of
    crusader_skill_values.csv for Smite (or the rune that states it), the generated value map says whose record holds it, and
    the numbers are the researched ones: 175% for the hit, 150% for the chains, 30 yards, 3 additional enemies within 20,
    Shared Fate 2 seconds and 15 yards, Shackle 20% for 1 second, Shatter 60% within 3 yards, Reaping 6437 Life a second for 2
    seconds up to 4 stacks, Surge 5. Every tunable it reads is a row of data/tunables/crusader.csv.

What it does not prove: anything on a running server. The chains, the stuns, the roots and the explosions are
docs/test-diablocraft-7t4gv.3.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_crusader_smite.py
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
HEADER = "src/classes/crusader/dc_crusader_smite.h"
NEAREST = "src/classes/crusader/dc_crusader_nearest.h"
SOURCES = [HEADER, NEAREST, "tests/crusader_smite/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_smite.cpp"
SKILL = "Smite"


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
    binary = harness_env.build([MODULE / "tests/crusader_smite/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "radius_yards", "chain"), value("", "target_count"), value("Surge", "target_count"),
               value("Shared Fate", "distance_yards"), tune("smite_shared_fate_seconds")] + runes()
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
            ("two runes share a name", (HEADER, "return Rune::Shackle;", "return Rune::Shatter;")),
            ("the chains take the farthest", (NEAREST, "return distances[a] < distances[b];", "return distances[a] > distances[b];")),
            ("the radius is ignored", (NEAREST, "if (distances[i] <= radius)", "if (true)")),
            ("the count is ignored", (NEAREST, "if (inside.size() > count)", "if (false)")),
            ("the gap is read as the distance itself", (HEADER, "return distance > 0 && now - then >= distance;",
                                                        "return distance > 0 && now >= distance;")),
            ("a binding outlasts its end", (HEADER, "return now < until;", "return now <= until;")),
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
        self.assertEqual(runes(), ["Shared Fate", "Shackle", "Shatter", "Reaping", "Surge"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "generated_resource"), value("", "damage_pct", "hit"), value("", "damage_pct", "chain"),
                          value("", "radius_yards", "range"), value("", "target_count"), value("", "radius_yards", "chain")],
                         [5, 175, 150, 30, 3, 20])
        self.assertEqual((value("Shared Fate", "stun_duration_seconds"), value("Shared Fate", "distance_yards")), (2, 15))
        self.assertEqual((value("Shackle", "proc_chance_pct"), value("Shackle", "immobilize_duration_seconds")), (20, 1))
        self.assertEqual((value("Shatter", "damage_pct"), value("Shatter", "radius_yards")), (60, 3))
        self.assertEqual([value("Reaping", t) for t in ("heal_per_second_life", "duration_seconds", "max_stacks_count")],
                         [6437, 2, 4])
        self.assertEqual(value("Surge", "target_count"), 5)

    def test_the_tunables(self):
        rows = tunables()
        self.assertEqual((rows["smite_shared_fate_seconds"]["d3_value"], rows["smite_shared_fate_seconds"]["value"]), ("5", ""))
        self.assertIn("SF_33", rows["smite_shared_fate_seconds"]["notes"])
        # No number is sourced: the designer's column is blank and the row says so (the code's floor works meanwhile).
        check = rows["smite_shared_fate_check_seconds"]
        self.assertEqual((check["d3_value"], check["value"]), ("", ""))
        self.assertTrue(check["notes"].startswith("PLACEHOLDER for the designer"))
        self.assertEqual((rows["smite_shatter_delay_seconds"]["d3_value"], rows["smite_shatter_delay_seconds"]["value"]), ("0.5", ""))
        self.assertIn("SF_10", rows["smite_shatter_delay_seconds"]["notes"])

    def test_the_floor_is_a_named_guard_and_not_a_tuning_number(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertIn("constexpr double CheckFloorSeconds = 0.05;", text)
        self.assertEqual(text.count("0.05"), 1)
        self.assertIn("std::max(CheckFloorSeconds, Tune(\"smite_shared_fate_check_seconds\"))", text)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {"smite_shared_fate_seconds", "smite_shared_fate_check_seconds", "smite_shatter_delay_seconds"})
        for name in read_tunables:
            self.assertIn(name, tunables())
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"radius_yards", "damage_pct", "target_count", "distance_yards", "stun_duration_seconds",
                                  "proc_chance_pct", "immobilize_duration_seconds", "heal_per_second_life",
                                  "max_stacks_count", "duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("Shared Fate", "distance_yards", ""), ("Shared Fate", "stun_duration_seconds", ""),
                                       ("Shackle", "proc_chance_pct", ""), ("Shackle", "immobilize_duration_seconds", ""),
                                       ("Shatter", "damage_pct", ""), ("Shatter", "radius_yards", ""),
                                       ("Reaping", "heal_per_second_life", ""), ("Reaping", "duration_seconds", ""),
                                       ("Reaping", "max_stacks_count", ""), ("Surge", "target_count", "")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token, qualifier)]["origin"], "own")
        # The skill's hit, chain and radius reach every rune by inheritance (Surge states only its own count).
        for rune in runes():
            for token, qualifier in (("damage_pct", "hit"), ("damage_pct", "chain"), ("radius_yards", "chain")):
                self.assertIn(mapped[(rune, token, qualifier)]["origin"], ("inherited", "own"), (rune, token, qualifier))


if __name__ == "__main__":
    unittest.main()
