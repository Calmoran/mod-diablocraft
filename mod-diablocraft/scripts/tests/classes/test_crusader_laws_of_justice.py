"""Laws of Justice and its five runes (src/classes/crusader/dc_crusader_laws_of_justice.h and .cpp; the state and the pulse are
Laws of Valor's dc_crusader_laws.h and .cpp, tested in test_crusader_laws_of_valor.py).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_laws_of_justice/harness.cpp compiles the real
    dc_crusader_laws_of_justice.h with the sheets' own rune names and numbers: each rune name is its rune; Protect the Innocent
    sends its 20% of a hit to the Crusader (never more than the hit, nothing for no hit or no share); Decaying Strength's 15% per
    stack stacks to 4 for the 60% maximum, a partial stack does not count, and at least one stack. Seven mutations planted in a
    scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_laws_of_justice.cpp reads by name is a row of
    crusader_skill_values.csv for Laws of Justice (or the rune that states it), the generated value map says whose record holds
    it, and the numbers are the researched ones: resistance 140 points passive and 490 active for 5 seconds, Protect the Innocent
    20%, Immovable Object 7000 Armor, Faith's Armor 26821 absorbed for 5 seconds, Decaying Strength 15% to 60%, Bravery 5 seconds.
    Protect the Innocent's 5 seconds are the Law's own window (the code ties it to the window), so the sheet must say 5 for both.
  * **The Law deals no damage on the cast.** BasePct answers 0 for the skill and every rune.

What it does not prove: anything on a running server. Protect the Innocent's damage is dealt to the Crusader as plain damage
(no further mitigation), after the ally's own.

    python mod-diablocraft/scripts/tests/classes/test_crusader_laws_of_justice.py
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
HEADER = "src/classes/crusader/dc_crusader_laws_of_justice.h"
SOURCES = [HEADER, "tests/crusader_laws_of_justice/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_laws_of_justice.cpp"
SKILL = "Laws of Justice"


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
    binary = harness_env.build([MODULE / "tests/crusader_laws_of_justice/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Protect the Innocent", "damage_share_pct"), value("Decaying Strength", "enemy_damage_pct"),
               value("Decaying Strength", "max_bonus_pct")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 12, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        share = "return damage > 0 ? damage * std::clamp(sharePct, 0.0, 100.0) / 100.0 : 0.0;"
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Bravery;", "return Rune::FaithsArmor;")),
            ("the whole hit goes to the Crusader", (HEADER, share, "return damage > 0 ? damage : 0.0;")),
            ("the share is not capped at the hit", (HEADER, share, "return damage > 0 ? damage * std::max(sharePct, 0.0) / 100.0 : 0.0;")),
            ("a negative share sends a negative", (HEADER, share, "return damage > 0 ? damage * sharePct / 100.0 : 0.0;")),
            ("a hit of nothing sends something", (HEADER, share, "return damage * std::clamp(sharePct, 0.0, 100.0) / 100.0;")),
            ("a partial stack counts", (HEADER, "std::floor(maxBonusPct / perStackPct + 1e-9)", "std::ceil(maxBonusPct / perStackPct)")),
            ("no stacking", (HEADER, "return unsigned(std::max(1.0, std::floor(maxBonusPct / perStackPct + 1e-9)));", "return 1;")),
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
        self.assertEqual(runes(), ["Protect the Innocent", "Immovable Object", "Faith's Armor", "Decaying Strength", "Bravery"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "duration_seconds")], [30, 5])
        self.assertEqual([value("", "resistance_points", "passive"), value("", "resistance_points", "active")], [140, 490])
        self.assertEqual(value("Protect the Innocent", "damage_share_pct"), 20)
        self.assertEqual((value("Immovable Object", "armor_points"), value("Immovable Object", "duration_seconds")), (7000, 5))
        self.assertEqual((value("Faith's Armor", "absorb_life"), value("Faith's Armor", "absorb_duration_seconds")), (26821, 5))
        self.assertEqual([value("Decaying Strength", t) for t in ("enemy_damage_pct", "duration_seconds", "max_bonus_pct")], [15, 5, 60])
        self.assertEqual(value("Bravery", "duration_seconds"), 5)

    def test_protect_the_innocent_lasts_the_laws_own_window(self):
        # Redirect reads the Law's window, not a time of its own, so the sheet's two fives must agree.
        self.assertEqual(value("Protect the Innocent", "duration_seconds"), value("", "duration_seconds"))

    def test_every_token_the_code_reads_is_a_sheet_row_the_engine_can_read(self):
        text = CODE.read_text(encoding="utf-8")
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"resistance_points", "armor_points", "duration_seconds", "absorb_duration_seconds", "absorb_life",
                                  "enemy_damage_pct", "max_bonus_pct", "damage_share_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "resistance_points", "passive"), ("", "resistance_points", "active"),
                                       ("", "duration_seconds", ""), ("Protect the Innocent", "damage_share_pct", ""),
                                       ("Immovable Object", "armor_points", ""), ("Immovable Object", "duration_seconds", ""),
                                       ("Faith's Armor", "absorb_life", ""), ("Faith's Armor", "absorb_duration_seconds", ""),
                                       ("Decaying Strength", "enemy_damage_pct", ""), ("Decaying Strength", "duration_seconds", ""),
                                       ("Decaying Strength", "max_bonus_pct", ""), ("Bravery", "duration_seconds", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertIn((rune, token, qualifier), mapped)
        for rune in runes():
            for token, qualifier in (("resistance_points", "passive"), ("resistance_points", "active"), ("duration_seconds", "")):
                self.assertIn((rune, token, qualifier), mapped, (rune, token, qualifier))

    def test_the_aura_reaches_sixty_yards(self):
        targeting = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
        self.assertEqual(len(targeting), 1)
        self.assertEqual(float(targeting[0]["radius_yards"]), 60)


if __name__ == "__main__":
    unittest.main()
