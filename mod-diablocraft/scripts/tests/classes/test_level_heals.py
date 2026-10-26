"""The heals D3 builds from its Healing table scale with the caster's level: the Crusader's Punish (Rebirth) and Justice (Holy
Bolt), the Monk's Serenity (Peaceful Repose, Tranquility) and Breath of Heaven (the skill and Circle of Life)
(src/classes/dc_level_heal.h, src/combat/dc_healing_table.h).

What this proves, and how:

  * **The sheets are the file's coefficient at the top level.** Each number the sheets hold for these heals is the power file's
    coefficient times the table's last row, rounded (0.024 of 536421 is Punish's 12874, 0.13 is Breath of Heaven's 69735); with the
    game archives on this machine the coefficients are read back from the decoded power files (Power/X1_Crusader_Punish.pow SF_10,
    X1_Crusader_Justice SF_9 and SF_6, Monk_Serenity SF_1, SF_13 and SF_16, Monk_BreathOfHeaven SF_22, SF_23 and SF_6).
  * **The heal at a level is the file's.** tests/level_heal/harness.cpp compiles the real dc_level_heal.h over the real table and, for
    every one of those numbers at a low level (5), a middle one (35) and 70, the heal it gives is within a whole point of the file's
    coefficient times the table at that level (worked out here from data/d3/healing_table.csv); at 70 it is the sheet's number itself.
    Planted differences (the level ignored, the table without the division, the division by another level, a heal that does not grow,
    a missing clamp) must each make it fail.
  * **The wiring.** Each of the four skills' code scales the sheet's heal (or absorb) by the caster's level before it heals.

What it does not prove: the numbers in game, or the tooltips (which keep the level-70 numbers the sheets hold).

    python mod-diablocraft/scripts/tests/classes/test_level_heals.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import decode_pow
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/dc_level_heal.h"
TABLE = "src/combat/dc_healing_table.h"
HARNESS = MODULE / "tests/level_heal/harness.cpp"
LEVELS = (5, 35, 70)

# (label, sheet, skill, rune, token, power file, coefficient: the sum of the file's terms that make it)
# Breath of Heaven's Circle of Life doubles the base (SF_6 = 2), so its coefficients are twice the base's.
VALUES = [
    ("Punish - Rebirth", "crusader_skill_values.csv", "Punish", "Rebirth", "heal_per_second_life", "X1_Crusader_Punish", {10: 0.024}),
    ("Justice - Holy Bolt min", "crusader_skill_values.csv", "Justice", "Holy Bolt", "heal_min_life", "X1_Crusader_Justice", {9: 0.004}),
    ("Justice - Holy Bolt max", "crusader_skill_values.csv", "Justice", "Holy Bolt", "heal_max_life", "X1_Crusader_Justice", {9: 0.004, 6: 0.002}),
    ("Serenity - Peaceful Repose min", "monk_skill_values.csv", "Serenity", "Peaceful Repose", "heal_min_life", "Monk_Serenity", {1: 0.175}),
    ("Serenity - Peaceful Repose max", "monk_skill_values.csv", "Serenity", "Peaceful Repose", "heal_max_life", "Monk_Serenity", {1: 0.175, 13: 0.05}),
    ("Serenity - Tranquility absorb", "monk_skill_values.csv", "Serenity", "Tranquility", "absorb_life", "Monk_Serenity", {16: 0.224}),
    ("Breath of Heaven min", "monk_skill_values.csv", "Breath of Heaven", "", "heal_min_life", "Monk_BreathOfHeaven", {22: 0.13}),
    ("Breath of Heaven max", "monk_skill_values.csv", "Breath of Heaven", "", "heal_max_life", "Monk_BreathOfHeaven", {22: 0.13, 23: 0.04}),
    ("Breath of Heaven - Circle of Life min", "monk_skill_values.csv", "Breath of Heaven", "Circle of Life", "heal_min_life", "Monk_BreathOfHeaven", {22: 0.26}),
    ("Breath of Heaven - Circle of Life max", "monk_skill_values.csv", "Breath of Heaven", "Circle of Life", "heal_max_life", "Monk_BreathOfHeaven", {22: 0.26, 23: 0.08}),
]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def healing(level):
    return float(next(r for r in read(D3 / "healing_table.csv") if int(r["level"]) == level)["value"])


def sheet_value(sheet, skill, rune, token):
    rows = [r for r in read(D3 / sheet) if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (skill, rune, token, "")]
    assert len(rows) == 1, (skill, rune, token, len(rows))
    return float(rows[0]["value"])


def coefficient(terms):
    return sum(terms.values())


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (HEADER, TABLE)}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = []
    for _label, sheet, skill, rune, token, _power, terms in VALUES:
        for level in LEVELS:
            numbers += [sheet_value(sheet, skill, rune, token), level, coefficient(terms) * healing(level)]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Sheets(unittest.TestCase):
    def test_each_number_is_the_files_coefficient_at_the_top_level(self):
        for label, sheet, skill, rune, token, _power, terms in VALUES:
            with self.subTest(label):
                self.assertEqual(round(coefficient(terms) * healing(70)), sheet_value(sheet, skill, rune, token))

    @unittest.skipUnless(decode_pow.available(), "needs reference/blizzless-diiis and smpq")
    def test_the_coefficients_are_the_decoded_power_files(self):
        for label, _sheet, _skill, _rune, _token, power, terms in VALUES:
            with self.subTest(label):
                parsed = decode_pow.parse_power(decode_pow.extract(f"Power/{power}.pow"))
                for number, coefficient_of_term in terms.items():
                    text = parsed["sf"][number].replace(" ", "")
                    found = re.match(r"\(?([0-9.]+)\)?\*Table\(Healing,(?:Effective_)?Level\)", text)
                    self.assertTrue(found, (power, number, text))
                    # Circle of Life's terms are the file's doubled (SF_6 = 2); the others are the file's own.
                    scale = 2 if "Circle of Life" in label else 1
                    self.assertAlmostEqual(float(found[1]) * scale, coefficient_of_term, places=9)


class Harness(unittest.TestCase):
    def test_the_heal_at_a_level_is_the_files(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, len(VALUES) * len(LEVELS) * 2, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the level is ignored", (HEADER, "atTopLevel * Combat::Healing::At(level) / TopLevelHealing()", "atTopLevel * Combat::Healing::At(70) / TopLevelHealing()")),
            ("the table is not divided by the top level", (HEADER, "atTopLevel * Combat::Healing::At(level) / TopLevelHealing()", "atTopLevel * Combat::Healing::At(level)")),
            ("divided by another level", (HEADER, "sizeof(Combat::Healing::Table) / sizeof(Combat::Healing::Table[0]) - 1]", "sizeof(Combat::Healing::Table) / sizeof(Combat::Healing::Table[0]) - 2]")),
            ("the heal does not grow", (HEADER, "atTopLevel * Combat::Healing::At(level) / TopLevelHealing()", "atTopLevel * (level < 36 ? Combat::Healing::At(35) : Combat::Healing::At(level)) / TopLevelHealing()")),
            ("a negative sheet gives a heal", (HEADER, "atTopLevel > 0 ? atTopLevel", "atTopLevel != 0 ? atTopLevel")),
            ("a level past the table reads past it", (TABLE, "sizeof(Table) / sizeof(Table[0]) - 1)", "sizeof(Table) / sizeof(Table[0]) - 2)")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Wiring(unittest.TestCase):
    def code(self, path):
        text = (MODULE / "src/classes" / path).read_text(encoding="utf-8")
        self.assertIn('#include "../dc_level_heal.h"', text)
        return re.sub(r"\s+", " ", text)

    def test_punish_scales_the_regeneration(self):
        self.assertIn('Classes::HealAtLevel(Numbers::Num(spellId, "heal_per_second_life"), player->GetLevel())', self.code("crusader/dc_crusader_punish.cpp"))

    def test_justice_scales_both_bounds_by_the_casters_level(self):
        code = self.code("crusader/dc_crusader_justice.cpp")
        self.assertIn('Classes::HealAtLevel(Numbers::Num(spellId, "heal_min_life"), player->GetLevel())', code)
        self.assertIn('Classes::HealAtLevel(Numbers::Num(spellId, "heal_max_life"), player->GetLevel())', code)
        self.assertIn("HealAmount(minLife, maxLife, rand_norm())", code)
        self.assertNotIn('HealAmount(Numbers::Num(spellId, "heal_min_life")', code)

    def test_serenity_scales_the_heal_and_the_absorb(self):
        code = self.code("monk/dc_monk_serenity.cpp")
        self.assertIn('HealRoll(Classes::HealAtLevel(Numbers::Num(spellId, "heal_min_life"), player->GetLevel()), Classes::HealAtLevel(Numbers::Num(spellId, "heal_max_life"), player->GetLevel()),', code)
        self.assertIn('Classes::HealAtLevel(Numbers::Num(spellId, "absorb_life"), player->GetLevel())', code)

    def test_breath_of_heaven_scales_both_bounds(self):
        code = self.code("monk/dc_monk_breath_of_heaven.cpp")
        self.assertIn('minLife = Classes::HealAtLevel(Numbers::Num(spellId, "heal_min_life"), player->GetLevel())', code)
        self.assertIn('maxLife = Classes::HealAtLevel(Numbers::Num(spellId, "heal_max_life"), player->GetLevel())', code)

    def test_no_other_reader_of_these_numbers_skips_the_scaling(self):
        # The numbers are read by these four files only (the tooltips read the sheet's level-70 text).
        readers = set()
        for path in (MODULE / "src").rglob("*.cpp"):
            text = path.read_text(encoding="utf-8")
            for _label, _sheet, skill, _rune, token, _power, _terms in VALUES:
                if f'"{token}"' in text and (f'Skill = "{skill}"' in text):
                    readers.add(path.name)
        self.assertEqual(readers, {"dc_crusader_punish.cpp", "dc_crusader_justice.cpp", "dc_monk_serenity.cpp", "dc_monk_breath_of_heaven.cpp"})


if __name__ == "__main__":
    unittest.main()
