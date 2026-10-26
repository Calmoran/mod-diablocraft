"""Slash and its five runes (src/classes/crusader/dc_crusader_slash.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_slash/harness.cpp compiles the real dc_crusader_slash.h and
    feeds it the sheets' own rune names, Crush's number and the reaches (the targeting sheet's 6 yards and the two Carve
    tunables): each rune name is its rune, Crush's number is for Crush alone, Carve takes the enemies past the skill's
    reach and inside its own and none twice, degrees become radians. Six mutations planted in a scratch copy (two runes
    share a name, every rune gives Crush's number, Carve takes an enemy past its reach, Carve takes one the cone struck,
    the base reach is lost, the arc is in the wrong unit) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_slash.cpp reads by name is a row of
    crusader_skill_values.csv for Slash (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: 230% weapon damage, 5 Wrath, Zeal 1% for 3 seconds up to 10 stacks, Electrify
    25% for 2 seconds, Crush 20%, Guard 5% up to 5 stacks. Every tunable it reads is a row of data/tunables/crusader.csv:
    Guard's length is 3 seconds and Carve's arc 120 degrees (the designer's answers, q-1021-01 and q-1021-02), and Carve's reach 8.75 yards (the power file's SF_13).

What it does not prove: anything on a running server. The stacks, the stun, the critical chance and the larger area are
docs/test-diablocraft-7t4gv.2.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_crusader_slash.py
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
HEADER = "src/classes/crusader/dc_crusader_slash.h"
SOURCES = [HEADER, "tests/crusader_slash/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_slash.cpp"
SKILL = "Slash"


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


def base_reach():
    rows = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
    assert len(rows) == 1
    return float(rows[0]["radius_yards"])


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
    binary = harness_env.build([MODULE / "tests/crusader_slash/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Crush", "crit_chance_pct"), base_reach(), tune("slash_carve_radius_yards"),
               tune("slash_carve_arc_degrees")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 10, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Carve;", "return Rune::Crush;")),
            ("every rune gives Crush's number", (HEADER, "return rune == Rune::Crush ? pct : 0.0;", "return pct;")),
            ("Carve takes an enemy past its reach", (HEADER, "distance <= reach;", "distance <= reach + 1;")),
            ("Carve takes one the cone struck", (HEADER, "return !alreadyStruck && reach > baseReach", "return reach > baseReach")),
            ("the base reach is lost", (HEADER, "reach > baseReach && distance <= reach", "distance <= reach")),
            ("the arc in the wrong unit", (HEADER, "return degrees * 3.14159265358979323846 / 180.0;",
                                           "return degrees * 3.14159265358979323846 / 360.0;")),
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
        self.assertEqual(runes(), ["Zeal", "Electrify", "Crush", "Carve", "Guard"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "generated_resource"), value("", "damage_pct")], [5, 230])
        self.assertEqual([value("Zeal", t) for t in ("attack_speed_pct", "duration_seconds", "max_stacks_count")], [1, 3, 10])
        self.assertEqual((value("Electrify", "proc_chance_pct"), value("Electrify", "stun_duration_seconds")), (25, 2))
        self.assertEqual(value("Crush", "crit_chance_pct"), 20)
        self.assertEqual((value("Guard", "armor_pct"), value("Guard", "max_stacks_count")), (5, 5))
        self.assertEqual(base_reach(), 6)

    def test_the_tunables(self):
        rows = tunables()
        # The designer's answers (cards q-1021-01 and q-1021-02): his column is filled and no row is a placeholder any more.
        guard, arc = rows["slash_guard_seconds"], rows["slash_carve_arc_degrees"]
        self.assertEqual((guard["d3_value"], guard["value"]), ("", "3"))
        self.assertEqual((arc["d3_value"], arc["value"]), ("", "120"))
        for row in (guard, arc):
            self.assertNotIn("PLACEHOLDER", row["notes"])
        self.assertIn("q-1021-01", guard["notes"])
        self.assertIn("q-1021-02", arc["notes"])
        self.assertEqual((rows["slash_carve_radius_yards"]["d3_value"], rows["slash_carve_radius_yards"]["value"]), ("8.75", ""))
        self.assertIn("SF_13", rows["slash_carve_radius_yards"]["notes"])

    def test_guard_lasts_three_seconds_as_zeal_does(self):
        self.assertEqual(tune("slash_guard_seconds"), 3)
        self.assertEqual(tune("slash_guard_seconds"), value("Zeal", "duration_seconds"))

    def test_carve_strikes_in_a_120_degree_arc_and_the_plain_skill_keeps_the_cores_cone(self):
        self.assertEqual(tune("slash_carve_arc_degrees"), 120)
        code = CODE.read_text(encoding="utf-8")
        # Only Carve reads the arc: the plain skill and the other runes add no arc of their own.
        carve = code[code.index("case Rune::Carve:"):]
        self.assertIn('Tune("slash_carve_arc_degrees")', carve)
        self.assertEqual(code.count('Tune("slash_carve_arc_degrees")'), 1)
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-500:])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {"slash_guard_seconds", "slash_carve_radius_yards", "slash_carve_arc_degrees"})
        for name in read_tunables:
            self.assertIn(name, tunables())
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"attack_speed_pct", "max_stacks_count", "duration_seconds", "armor_pct",
                                  "proc_chance_pct", "stun_duration_seconds", "crit_chance_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("Zeal", "attack_speed_pct"), ("Zeal", "duration_seconds"), ("Zeal", "max_stacks_count"),
                            ("Electrify", "proc_chance_pct"), ("Electrify", "stun_duration_seconds"),
                            ("Crush", "crit_chance_pct"), ("Guard", "armor_pct"), ("Guard", "max_stacks_count")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token, "")]["origin"], "own")
        # The skill's hit and Wrath are inherited by every rune: the engine loads them with no code of ours.
        for rune in runes():
            self.assertEqual(mapped[(rune, "damage_pct", "")]["origin"], "inherited", rune)
            self.assertEqual(mapped[(rune, "generated_resource", "")]["origin"], "inherited", rune)


if __name__ == "__main__":
    unittest.main()
