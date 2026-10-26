"""Justice and its five runes (src/classes/crusader/dc_crusader_justice.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_justice/harness.cpp compiles the real dc_crusader_justice.h and
    feeds it the sheets' own rune names and numbers: each rune name is its rune; the hammer's own hit is Hammer of Pursuit's
    335% for that rune and the skill's 245% for every other (Burst's 60% is its explosion's); Holy Bolt's heal is a roll
    between 2146 and 3219 and never outside them. Six mutations planted in a scratch copy (two runes share a name, Burst's
    number becomes the hit, Pursuit hits for the skill's number, the heal's top is lost, a roll outside 0 to 1 is not held,
    the heal ignores the roll) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_justice.cpp reads by name is a row of
    crusader_skill_values.csv for Justice (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: 245% weapon damage, 5 Wrath, Sword of Justice 5% for 3 seconds up to 3 stacks,
    Crack 100% into 2 hammers of 245%, Hammer of Pursuit 335%, Burst 60% within 10 yards with a 20% stun of 1 second, Holy
    Bolt 2146 to 3219. Every tunable it reads is a row of data/tunables/crusader.csv with the power file's number.

What it does not prove: anything on a running server. The hammer's landing, the speed, the cracks, the explosion and the heal
are docs/test-diablocraft-7t4gv.4.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_crusader_justice.py
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
HEADER = "src/classes/crusader/dc_crusader_justice.h"
SOURCES = [HEADER, "src/classes/crusader/dc_crusader_nearest.h", "tests/crusader_justice/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_justice.cpp"
SKILL = "Justice"


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
    binary = harness_env.build([MODULE / "tests/crusader_justice/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_pct"), value("Hammer of Pursuit", "damage_pct"), value("Burst", "damage_pct"),
               value("Holy Bolt", "heal_min_life"), value("Holy Bolt", "heal_max_life")] + runes()
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
            ("two runes share a name", (HEADER, "return Rune::Crack;", "return Rune::Burst;")),
            ("Burst's number becomes the hit", (HEADER, "return rune == Rune::HammerOfPursuit ? runePct : skillPct;",
                                                "return rune == Rune::HammerOfPursuit || rune == Rune::Burst ? runePct : skillPct;")),
            ("Pursuit hits for the skill's number", (HEADER, "return rune == Rune::HammerOfPursuit ? runePct : skillPct;",
                                                     "return skillPct;")),
            ("the heal's top is lost", (HEADER, "(maxLife - minLife)", "(maxLife - minLife) / 2")),
            ("a roll outside 0 to 1 is not held", (HEADER, "std::clamp(roll, 0.0, 1.0)", "roll")),
            ("the heal ignores the roll", (HEADER, "return minLife + std::clamp(roll, 0.0, 1.0) * (maxLife - minLife);",
                                           "return minLife;")),
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
        self.assertEqual(runes(), ["Sword of Justice", "Crack", "Hammer of Pursuit", "Burst", "Holy Bolt"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "generated_resource"), value("", "damage_pct")], [5, 245])
        self.assertEqual([value("Sword of Justice", t) for t in ("movement_speed_pct", "duration_seconds", "max_stacks_count")],
                         [5, 3, 3])
        self.assertEqual([value("Crack", t) for t in ("proc_chance_pct", "spawn_count", "damage_pct")], [100, 2, 245])
        self.assertEqual(value("Hammer of Pursuit", "damage_pct"), 335)
        self.assertEqual([value("Burst", t) for t in ("damage_pct", "radius_yards", "proc_chance_pct", "stun_duration_seconds")],
                         [60, 10, 20, 1])
        self.assertEqual((value("Holy Bolt", "heal_min_life"), value("Holy Bolt", "heal_max_life")), (2146, 3219))

    def test_the_tunables(self):
        rows = tunables()
        for name, number, source in (("justice_crack_radius_yards", "40", "SF_2"), ("justice_holy_bolt_radius_yards", "60", "SF_19")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""), name)
            self.assertIn(source, rows[name]["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {"justice_crack_radius_yards", "justice_holy_bolt_radius_yards"})
        for name in read_tunables:
            self.assertIn(name, tunables())
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "movement_speed_pct", "max_stacks_count", "duration_seconds", "proc_chance_pct",
                                  "spawn_count", "radius_yards", "stun_duration_seconds", "heal_min_life", "heal_max_life"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("Sword of Justice", "movement_speed_pct"), ("Sword of Justice", "duration_seconds"),
                            ("Sword of Justice", "max_stacks_count"), ("Crack", "proc_chance_pct"), ("Crack", "spawn_count"),
                            ("Crack", "damage_pct"), ("Hammer of Pursuit", "damage_pct"), ("Burst", "damage_pct"),
                            ("Burst", "radius_yards"), ("Burst", "proc_chance_pct"), ("Burst", "stun_duration_seconds"),
                            ("Holy Bolt", "heal_min_life"), ("Holy Bolt", "heal_max_life")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token, "")]["origin"], "own")
        # Wrath is the skill's, inherited by every rune (dc_crusader.cpp reads it).
        for rune in runes():
            self.assertEqual(mapped[(rune, "generated_resource", "")]["origin"], "inherited", rune)

    def test_the_hammer_is_a_projectile_so_the_runes_act_where_it_lands(self):
        # A projectile's hits come from Impact, which never calls the cast seam: the runes hang on Landed.
        records = (MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8")
        self.assertIn("85403,", records)
        code = CODE.read_text(encoding="utf-8")
        self.assertIn("void Landed(", code)
        self.assertNotIn("void Cast(", code)


if __name__ == "__main__":
    unittest.main()
