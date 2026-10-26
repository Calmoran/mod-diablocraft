"""Iron Skin and its five runes (src/classes/crusader/dc_crusader_iron_skin.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_iron_skin/harness.cpp compiles the real dc_crusader_iron_skin.h with the
    sheets' own rune names and numbers: each rune name is its rune; Steel Skin's 7 seconds replace the skill's 4 and no other
    rune changes them; the skin has expired only when nothing holds it; Charged Up's 20% roll procs below the chance and not at
    it. Six mutations planted in a scratch copy (two runes share a name, every rune takes Steel Skin's seconds, Steel Skin
    takes the skill's, a held skin counts as expired, the roll is inclusive, the roll is not checked) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_iron_skin.cpp reads by name is a row of
    crusader_skill_values.csv for Iron Skin (or the rune that states it), the generated value map says whose record holds it, and
    the numbers are the researched ones: 50% of the damage off for 4 seconds, Charged Up 20% to stun within 10 yards for 2 seconds,
    Steel Skin 7 seconds, Explosive Skin 1400% within 12 yards, Reflective Skin Thorns +300%, Flash 60% speed for 5 seconds. It
    reads no tunable: every number is the sheet's.
  * **The skin deals no damage on the cast.** BasePct answers 0 for the skill and every rune, so Explosive Skin's own damage_pct is
    not read as the cast's.

What it does not prove: anything on a running server, and Flash's "move through enemies unhindered", which is not built.

    python mod-diablocraft/scripts/tests/classes/test_crusader_iron_skin.py
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
HEADER = "src/classes/crusader/dc_crusader_iron_skin.h"
SOURCES = [HEADER, "tests/crusader_iron_skin/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_iron_skin.cpp"
SKILL = "Iron Skin"


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
    binary = harness_env.build([MODULE / "tests/crusader_iron_skin/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "absorb_duration_seconds"), value("Steel Skin", "duration_seconds"),
               value("Charged Up", "proc_chance_pct")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 11, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        seconds = "return rune == Rune::SteelSkin ? steelSeconds : skillSeconds;"
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Flash;", "return Rune::ChargedUp;")),
            ("every rune takes Steel Skin's seconds", (HEADER, seconds, "return steelSeconds;")),
            ("Steel Skin takes the skill's", (HEADER, seconds, "return skillSeconds;")),
            ("a held skin counts as expired", (HEADER, "return stacksHeld == 0;", "return stacksHeld <= 1;")),
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
        self.assertEqual(runes(), ["Charged Up", "Steel Skin", "Explosive Skin", "Reflective Skin", "Flash"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "absorb_pct"), value("", "absorb_duration_seconds")], [30, 50, 4])
        self.assertEqual([value("Charged Up", t) for t in ("proc_chance_pct", "radius_yards", "stun_duration_seconds")], [20, 10, 2])
        self.assertEqual(value("Steel Skin", "duration_seconds"), 7)
        self.assertEqual((value("Explosive Skin", "damage_pct"), value("Explosive Skin", "radius_yards")), (1400, 12))
        self.assertEqual(value("Reflective Skin", "thorns_pct"), 300)
        self.assertEqual((value("Flash", "movement_speed_pct"), value("Flash", "duration_seconds")), (60, 5))

    def test_the_code_reads_no_tunable_and_every_token_is_a_sheet_row_the_engine_can_read(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertNotIn("Tunables", text)
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"absorb_duration_seconds", "duration_seconds", "damage_pct", "radius_yards", "absorb_pct",
                                  "thorns_pct", "proc_chance_pct", "stun_duration_seconds", "movement_speed_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "absorb_pct"), ("", "absorb_duration_seconds"), ("Charged Up", "proc_chance_pct"),
                            ("Charged Up", "radius_yards"), ("Charged Up", "stun_duration_seconds"),
                            ("Steel Skin", "duration_seconds"), ("Explosive Skin", "damage_pct"),
                            ("Explosive Skin", "radius_yards"), ("Reflective Skin", "thorns_pct"),
                            ("Flash", "movement_speed_pct"), ("Flash", "duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)
        # The absorb and its time reach every rune: on its own record or by inheritance.
        for rune in runes():
            for token in ("absorb_pct", "absorb_duration_seconds"):
                self.assertIn((rune, token, ""), mapped, (rune, token))


if __name__ == "__main__":
    unittest.main()
