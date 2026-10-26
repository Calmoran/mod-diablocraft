"""Laws of Hope and its five runes (src/classes/crusader/dc_crusader_laws_of_hope.h and .cpp; the state and the pulse are Laws of
Valor's dc_crusader_laws.h and .cpp, tested in test_crusader_laws_of_valor.py).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_laws_of_hope/harness.cpp compiles the real dc_crusader_laws_of_hope.h
    with the sheets' own rune names and numbers: each rune name is its rune; a pulse heals the per-second rate for the seconds it
    stands for and nothing for no time or no rate; Wrath spent heals the sheet's Life for every point and nothing for none;
    Hopeful Cry covers Physical and only Physical, Promise of Faith every other element, no other rune any. Eight mutations
    planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_laws_of_hope.cpp reads by name is a row of
    crusader_skill_values.csv for Laws of Hope (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: 124128 absorbed for 5 seconds, 10728 Life per second, Wings of Angels 50% movement
    speed, Eternal Hope 10% maximum Life, Hopeful Cry and Promise of Faith 25%, Faith's Reward 1073 Life per Wrath.
  * **The Law deals no damage on the cast.** BasePct answers 0 for the skill and every rune.

What it does not prove: anything on a running server. Not built: Wings of Angels' "run through enemies unimpeded" (the speed is).
Faith's Reward counts the points the cast costs after reductions (the cast hook's number), not a measured drop of the pool.

    python mod-diablocraft/scripts/tests/classes/test_crusader_laws_of_hope.py
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
HEADER = "src/classes/crusader/dc_crusader_laws_of_hope.h"
SOURCES = [HEADER, "src/common/dc_common.h", "tests/crusader_laws_of_hope/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_laws_of_hope.cpp"
SKILL = "Laws of Hope"


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
    binary = harness_env.build([MODULE / "tests/crusader_laws_of_hope/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "heal_per_second_life"), value("Faith's Reward", "heal_per_hit_life")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 11, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        pulse = "return perSecond > 0 && pulseSeconds > 0 ? perSecond * pulseSeconds : 0.0;"
        wrath = "return perPoint > 0 && wrathSpent > 0 ? perPoint * wrathSpent : 0.0;"
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::PromiseOfFaith;", "return Rune::HopefulCry;")),
            ("a pulse heals the rate whatever its length", (HEADER, pulse, "return perSecond > 0 ? perSecond : 0.0;")),
            ("a pulse of no time heals", (HEADER, pulse, "return perSecond > 0 ? perSecond * std::max(pulseSeconds, 1.0) : 0.0;")),
            ("Wrath spent heals one point's worth", (HEADER, wrath, "return perPoint > 0 && wrathSpent > 0 ? perPoint : 0.0;")),
            ("no Wrath spent heals", (HEADER, wrath, "return perPoint > 0 ? perPoint * wrathSpent : 0.0;")),
            ("Hopeful Cry covers every element", (HEADER, "return element == Element::Physical;", "return true;")),
            ("Promise of Faith covers Physical too", (HEADER, "return element != Element::Physical;", "return true;")),
            ("a rune with no reduction reduces", (HEADER, "        return false;\n    }\n\n    // The production half",
                                                  "        return rune == Rune::FaithsReward;\n    }\n\n    // The production half")),
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
        self.assertEqual(runes(), ["Wings of Angels", "Eternal Hope", "Hopeful Cry", "Faith's Reward", "Promise of Faith"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "absorb_duration_seconds"), value("", "absorb_life"),
                          value("", "heal_per_second_life")], [30, 5, 124128, 10728])
        self.assertEqual(value("Wings of Angels", "movement_speed_pct"), 50)
        self.assertEqual(value("Eternal Hope", "max_life_pct"), 10)
        self.assertEqual((value("Hopeful Cry", "damage_reduction_pct"), value("Promise of Faith", "damage_reduction_pct")), (25, 25))
        self.assertEqual(value("Faith's Reward", "heal_per_hit_life"), 1073)

    def test_hope_states_its_window_as_its_shields_time(self):
        # Hope's sheet has no duration_seconds: the Law's empowered window is the shield's 5 seconds, so its flavour names that
        # token to the shared Press (the default token would read 0 and open no window).
        tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertNotIn("duration_seconds", tokens)
        self.assertIn("absorb_duration_seconds", tokens)
        self.assertIn('.window = "absorb_duration_seconds"', re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8")))

    def test_every_token_the_code_reads_is_a_sheet_row_the_engine_can_read(self):
        text = CODE.read_text(encoding="utf-8")
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"movement_speed_pct", "max_life_pct", "damage_reduction_pct", "absorb_duration_seconds", "absorb_life",
                                  "heal_per_hit_life", "heal_per_second_life"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "heal_per_second_life"), ("", "absorb_life"), ("", "absorb_duration_seconds"),
                            ("Wings of Angels", "movement_speed_pct"), ("Eternal Hope", "max_life_pct"),
                            ("Hopeful Cry", "damage_reduction_pct"), ("Promise of Faith", "damage_reduction_pct"),
                            ("Faith's Reward", "heal_per_hit_life")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)
        for rune in runes():
            for token in ("heal_per_second_life", "absorb_life", "absorb_duration_seconds"):
                self.assertIn((rune, token, ""), mapped, (rune, token))

    def test_the_aura_reaches_sixty_yards(self):
        targeting = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
        self.assertEqual(len(targeting), 1)
        self.assertEqual(float(targeting[0]["radius_yards"]), 60)


if __name__ == "__main__":
    unittest.main()
