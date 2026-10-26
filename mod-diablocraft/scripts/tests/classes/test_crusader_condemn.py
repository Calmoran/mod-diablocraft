"""Condemn and its five runes (src/classes/crusader/dc_crusader_condemn.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_condemn/harness.cpp compiles the real dc_crusader_condemn.h with
    the sheets' own rune names and numbers: each rune name is its rune; the explosion builds the sheet's seconds for every
    rune but Unleashed, which goes off at once; Reciprocate adds its share of the damage taken and no other rune does;
    Vacuum's pulses fit the build and its reach grows by the step, taking only enemies beyond the explosion and inside the
    reach; Eternal Retaliation cuts the cooldown for each enemy hit and no other rune does. Eleven mutations planted in a
    scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_condemn.cpp reads by name is a row of
    crusader_skill_values.csv for Condemn (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: 15 yards (Shattering Explosion 20), 3 seconds, 1160%, Reciprocate 50%, Eternal
    Retaliation 1 second. Every tunable it reads is a row of data/tunables/crusader.csv with the power file's number
    (Power/X1_Crusader_Condemn.pow) as its D3 value and none of the designer's.
  * **Condemn deals no damage on the cast.** BasePct answers 0 for the skill and every rune.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_crusader_condemn.py
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
HEADER = "src/classes/crusader/dc_crusader_condemn.h"
SOURCES = [HEADER, "tests/crusader_condemn/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_condemn.cpp"
SKILL = "Condemn"
POW = "Power/X1_Crusader_Condemn.pow"


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
    return {r["name"]: r for r in read(MODULE / "data/tunables/crusader.csv") if r["name"].startswith("condemn_")}


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
    binary = harness_env.build([MODULE / "tests/crusader_condemn/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    rows = tunables()
    numbers = [value("", "duration_seconds"), value("", "radius_yards"), value("Reciprocate", "damage_share_pct"),
               value("Eternal Retaliation", "cooldown_reduction_seconds"),
               float(rows["condemn_vacuum_interval_seconds"]["d3_value"]),
               float(rows["condemn_vacuum_radius_step_yards"]["d3_value"])] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 25, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Unleashed;", "return Rune::Vacuum;")),
            ("Unleashed waits", (HEADER, "rune == Rune::Unleashed || seconds < 0 ? 0.0 : seconds", "seconds < 0 ? 0.0 : seconds")),
            ("the build outlasts its end", (HEADER, "return now < until;", "return now <= until;")),
            ("any rune adds damage", (HEADER, "rune == Rune::Reciprocate && taken > 0", "taken > 0")),
            ("the share is the whole", (HEADER, "taken * sharePct / 100.0", "taken * sharePct")),
            ("one pulse too many", (HEADER, "seconds / interval + 1e-9", "seconds / interval + 1.0")),
            ("a negative step shrinks the reach", (HEADER, "explosionRadius + (step > 0 ? step : 0.0) * pulse", "explosionRadius + step * pulse")),
            ("an enemy at the edge is taken", (HEADER, "distance > explosionRadius &&", "distance >= explosionRadius &&")),
            ("one past the reach is taken", (HEADER, "distance <= reach", "distance < reach")),
            ("the cut is not for each enemy", (HEADER, "enemiesHit * perEnemySeconds", "perEnemySeconds")),
            ("any rune cuts the cooldown", (HEADER, "rune == Rune::EternalRetaliation && perEnemySeconds > 0", "perEnemySeconds > 0")),
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
        self.assertEqual(runes(), ["Reciprocate", "Vacuum", "Eternal Retaliation", "Shattering Explosion", "Unleashed"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "duration_seconds", "damage_pct", "radius_yards")],
                         [15, 3, 1160, 15])
        self.assertEqual(value("Reciprocate", "damage_share_pct"), 50)
        self.assertEqual(value("Eternal Retaliation", "cooldown_reduction_seconds"), 1)
        self.assertEqual(value("Shattering Explosion", "radius_yards"), 20)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"duration_seconds", "damage_pct", "radius_yards", "damage_share_pct", "cooldown_reduction_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "duration_seconds"), ("", "damage_pct"), ("", "radius_yards"),
                            ("Reciprocate", "damage_share_pct"), ("Eternal Retaliation", "cooldown_reduction_seconds"),
                            ("Shattering Explosion", "radius_yards")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)
        # The explosion's numbers reach every rune: on its own record or by inheritance.
        for rune in runes():
            for token in ("duration_seconds", "damage_pct", "radius_yards"):
                self.assertIn((rune, token, ""), mapped, (rune, token))


class Tunables(unittest.TestCase):
    NUMBERS = {
        "condemn_vacuum_interval_seconds": "0.5",   # SF_11
        "condemn_vacuum_radius_step_yards": "2.5",  # SF_17
        "condemn_vacuum_max_targets": "10",         # SF_18
        "condemn_vacuum_offset_min_yards": "2",     # SF_19
        "condemn_vacuum_offset_extra_yards": "1",   # SF_20
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


if __name__ == "__main__":
    unittest.main()
