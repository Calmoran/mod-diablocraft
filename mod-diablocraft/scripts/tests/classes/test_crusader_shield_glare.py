"""Shield Glare and its five runes (src/classes/crusader/dc_crusader_shield_glare.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_shield_glare/harness.cpp compiles the real dc_crusader_shield_glare.h
    with the sheets' own rune names and numbers: each rune name is its rune; the arc is the sheet's 120 degrees in radians; the
    glare catches an enemy within the 30 yards and the arc that the core's narrower cone did not take, and nobody past either or
    twice; Emblazoned Shield's explosion is for enemies strictly under 25% life; Zealous Glare's 9 Wrath is for each enemy
    blinded. Seven mutations planted in a scratch copy (two runes share a name, the arc is left in degrees, the reach is not
    checked, the arc is not checked, an enemy is blinded twice, the life threshold is inclusive, the Wrath is not multiplied) must
    each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_shield_glare.cpp reads by name is a row of
    crusader_skill_values.csv for Shield Glare (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: a 4 second blind over 30 yards, Divine Verdict 20% for 4 seconds, Emblazoned Shield
    60% within 8 yards for enemies under 25% at 50%, Zealous Glare 9 Wrath, Subdue 80% for 6 seconds. The one tunable it reads is a
    row of data/tunables/crusader.csv: the power file's 120 degree cone.
  * **The glare deals no damage of its own.** BasePct answers 0 for the skill and every rune, so Emblazoned Shield's own damage_pct
    is not read as the cone's.

What it does not prove: anything on a running server. Uncertainty's charm is the shared one (src/combat/dc_charm_effect, proved in
test_charm_effect.py); here the rune is a 50% roll per blinded enemy and an 8 second charm that takes the blind's place.

    python mod-diablocraft/scripts/tests/classes/test_crusader_shield_glare.py
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
HEADER = "src/classes/crusader/dc_crusader_shield_glare.h"
SOURCES = [HEADER, "tests/crusader_shield_glare/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_shield_glare.cpp"
SKILL = "Shield Glare"
CAUGHT = "return !alreadyBlinded && inArc && reach > 0 && distance <= reach;"


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
    binary = harness_env.build([MODULE / "tests/crusader_shield_glare/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "radius_yards"), tune("shield_glare_arc_degrees"), value("Emblazoned Shield", "life_threshold_pct"),
               value("Zealous Glare", "gain_resource")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 14, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Subdue;", "return Rune::Uncertainty;")),
            ("the arc is left in degrees", (HEADER, "return degrees * 3.14159265358979323846 / 180.0;", "return degrees;")),
            ("the reach is not checked", (HEADER, CAUGHT, "return !alreadyBlinded && inArc && reach > 0;")),
            ("the arc is not checked", (HEADER, CAUGHT, "return !alreadyBlinded && reach > 0 && distance <= reach;")),
            ("an enemy is blinded twice", (HEADER, CAUGHT, "return inArc && reach > 0 && distance <= reach;")),
            ("the life threshold is inclusive", (HEADER, "return healthPct < thresholdPct;", "return healthPct <= thresholdPct;")),
            ("the Wrath is not multiplied", (HEADER, "return perEnemy > 0 ? perEnemy * enemies : 0.0;", "return perEnemy > 0 ? perEnemy : 0.0;")),
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
        self.assertEqual(runes(), ["Divine Verdict", "Uncertainty", "Emblazoned Shield", "Zealous Glare", "Subdue"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "radius_yards"), value("", "blind_duration_seconds")], [12, 30, 4])
        self.assertEqual((value("Divine Verdict", "damage_taken_pct"), value("Divine Verdict", "duration_seconds")), (20, 4))
        self.assertEqual([value("Emblazoned Shield", t) for t in ("life_threshold_pct", "proc_chance_pct", "damage_pct", "radius_yards")],
                         [25, 50, 60, 8])
        self.assertEqual(value("Zealous Glare", "gain_resource"), 9)
        self.assertEqual((value("Subdue", "slow_pct"), value("Subdue", "slow_duration_seconds")), (80, 6))
        self.assertEqual((value("Uncertainty", "proc_chance_pct"), value("Uncertainty", "charm_duration_seconds")), (50, 8))

    def test_the_tunable_is_the_power_files_cone(self):
        row = tunables()["shield_glare_arc_degrees"]
        self.assertEqual((row["d3_value"], row["value"]), ("120", ""))
        self.assertIn("SF_3", row["notes"])
        self.assertNotIn("PLACEHOLDER", row["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {"shield_glare_arc_degrees"})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"blind_duration_seconds", "damage_taken_pct", "duration_seconds", "life_threshold_pct",
                                  "proc_chance_pct", "damage_pct", "radius_yards", "gain_resource", "slow_pct",
                                  "slow_duration_seconds", "charm_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "blind_duration_seconds"), ("", "radius_yards"), ("Divine Verdict", "damage_taken_pct"),
                            ("Divine Verdict", "duration_seconds"), ("Emblazoned Shield", "life_threshold_pct"),
                            ("Emblazoned Shield", "proc_chance_pct"), ("Emblazoned Shield", "damage_pct"),
                            ("Emblazoned Shield", "radius_yards"), ("Zealous Glare", "gain_resource"),
                            ("Subdue", "slow_pct"), ("Subdue", "slow_duration_seconds"),
                            ("Uncertainty", "proc_chance_pct"), ("Uncertainty", "charm_duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)
        # The blind reaches every rune: by inheritance or on its own record.
        for rune in runes():
            self.assertIn((rune, "blind_duration_seconds", ""), mapped, rune)


if __name__ == "__main__":
    unittest.main()
