"""Punish and its five runes (src/classes/crusader/dc_crusader_punish.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_punish/harness.cpp compiles the real dc_crusader_punish.h and
    feeds it the sheets' own rune names and Fury's number: each of the five runes answers a block in a way of its own, the
    base skill and a rune of another skill answer nothing, and Fury's bonus is its number while armed and nothing before.
    Five mutations planted in a scratch copy (two runes share an answer, an unknown rune answers, the base skill answers,
    an unarmed Fury still gives its number, Fury never gives its number) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_punish.cpp reads by name is a row of
    crusader_skill_values.csv for Punish (or for the rune that states it), the engine can read it back from the record
    the generated value map names (own for a rune's own number, inherited for the skill's), and the numbers are the
    researched ones: 335% weapon damage, 5 Wrath, Hardened Senses 15% Block Chance for 5 seconds, Retaliate 140%,
    Celerity 15% for 3 seconds, Rebirth 12874 Life a second for 2 seconds, Roar 75% within 15 yards, Fury 15%.

What it does not prove: anything on a running server. The block, the buff, the answers and the Wrath are
docs/test-diablocraft-7t4gv.1.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_crusader_punish.py
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
HEADER = "src/classes/crusader/dc_crusader_punish.h"
SOURCES = [HEADER, "tests/crusader_punish/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_punish.cpp"
SKILL = "Punish"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "crusader_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    """The five runes in the sheet's order, A to E."""
    rows = sorted((r for r in read(D3 / "crusader_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
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
    binary = harness_env.build([MODULE / "tests/crusader_punish/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Fury", "crit_chance_pct")] + runes()
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
            ("two runes share an answer", (HEADER, 'if (rune == "Rebirth")\n            return Answer::Rebirth;',
                                           'if (rune == "Rebirth")\n            return Answer::Celerity;')),
            ("an unknown rune answers", (HEADER, "        return Answer::None;\n    }\n\n    // Fury:",
                                         "        return Answer::Roar;\n    }\n\n    // Fury:")),
            ("the base skill answers", (HEADER, 'if (rune == "Retaliate")', 'if (rune.empty() || rune == "Retaliate")')),
            ("an unarmed Fury still gives its number", (HEADER, "return armed ? pct : 0.0;", "return pct;")),
            ("Fury never gives its number", (HEADER, "return armed ? pct : 0.0;", "return 0.0;")),
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
        self.assertEqual(runes(), ["Retaliate", "Celerity", "Rebirth", "Roar", "Fury"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", token) for token in ("generated_resource", "damage_pct", "block_pct", "duration_seconds")],
                         [5, 335, 15, 5])
        self.assertEqual(value("Retaliate", "damage_pct"), 140)
        self.assertEqual((value("Celerity", "attack_speed_pct"), value("Celerity", "duration_seconds")), (15, 3))
        self.assertEqual((value("Rebirth", "heal_per_second_life"), value("Rebirth", "duration_seconds")), (12874, 2))
        self.assertEqual((value("Roar", "damage_pct"), value("Roar", "radius_yards")), (75, 15))
        self.assertEqual(value("Fury", "crit_chance_pct"), 15)

    def test_hardened_senses_is_one_stack_that_restarts(self):
        # Power/X1_Crusader_Punish.pow SF_2 'Block Buff Stack Max' = 1: a second Punish restarts it and never stacks it.
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('Buffs::Stack(player, base, Stat::BlockChance, Bucket::Flat, Numbers::Num(base, "block_pct"), 1, '
                      'Numbers::Num(base, "duration_seconds"));', text)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "block_pct", "duration_seconds", "attack_speed_pct",
                                  "heal_per_second_life", "radius_yards", "crit_chance_pct"})
        ids = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
               if r["skill"] == SKILL and r["spell_id"]}
        # What each call reads, from the record the code names: (rune, token) -> where the engine finds it.
        reads = [("", "damage_pct", "own"), ("", "block_pct", "own"), ("", "duration_seconds", "own"),
                 ("Retaliate", "damage_pct", "own"), ("Celerity", "attack_speed_pct", "own"),
                 ("Celerity", "duration_seconds", "own"), ("Rebirth", "heal_per_second_life", "own"),
                 ("Rebirth", "duration_seconds", "own"), ("Roar", "damage_pct", "own"), ("Roar", "radius_yards", "own"),
                 ("Fury", "crit_chance_pct", "own")]
        for rune, token, origin in reads:
            with self.subTest(rune=rune, token=token):
                row = ids.get((rune, token, ""))
                self.assertIsNotNone(row, f"no value-map row for {rune or 'Punish'} {token}")
                self.assertEqual(row["origin"], origin)
        # Generation is the skill's, inherited by every rune (dc_crusader.cpp reads it with Get).
        for rune in runes():
            self.assertEqual(ids[(rune, "generated_resource", "")]["origin"], "inherited")


if __name__ == "__main__":
    unittest.main()
