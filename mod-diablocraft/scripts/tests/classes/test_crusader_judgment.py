"""Judgment and its five runes (src/classes/crusader/dc_crusader_judgment.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_judgment/harness.cpp compiles the real dc_crusader_judgment.h with the
    sheets' own rune names and numbers: each rune name is its rune; Penitence heals 2682 for each enemy judged; an enemy is
    judged until its end time and not at it; Resolved adds its 8% crit chance on a judged enemy and nothing else does. Six
    mutations planted in a scratch copy (two runes share a name, Penitence heals once whatever the enemies, the judgment
    outlasts its end, Resolved applies to any enemy, any rune adds the crit chance, a negative heal heals) must each make it
    fail.
  * **The code reads what the sheets state.** Every token dc_crusader_judgment.cpp reads by name is a row of
    crusader_skill_values.csv for Judgment (or the rune that states it), the generated value map says whose record holds it, and
    the numbers are the researched ones: a 20 yard area, Immobilize 6 seconds (Deliberation 10), Penitence 2682 for 3 seconds,
    Resolved 8%, Debilitate 40% for 6 seconds. The one tunable it reads is a row of data/tunables/crusader.csv: the heal's tick,
    one second, the sheets' "per second".
  * **Judgment deals no damage.** BasePct answers 0 for the skill and every rune.

What it does not prove: anything on a running server, and the pull of Mass Verdict (all the way to the centre is a reading).

    python mod-diablocraft/scripts/tests/classes/test_crusader_judgment.py
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
HEADER = "src/classes/crusader/dc_crusader_judgment.h"
SOURCES = [HEADER, "tests/crusader_judgment/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_judgment.cpp"
SKILL = "Judgment"


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
    binary = harness_env.build([MODULE / "tests/crusader_judgment/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Penitence", "heal_per_second_life"), value("Resolved", "crit_chance_pct")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 14, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        crit = "return rune == Rune::Resolved && judged ? pct : 0.0;"
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Debilitate;", "return Rune::Resolved;")),
            ("Penitence heals once whatever the enemies", (HEADER, "perEnemy * enemies", "perEnemy")),
            ("the judgment outlasts its end", (HEADER, "return now < until;", "return now <= until;")),
            ("Resolved applies to any enemy", (HEADER, crit, "return rune == Rune::Resolved ? pct : 0.0;")),
            ("any rune adds the crit chance", (HEADER, crit, "return judged ? pct : 0.0;")),
            ("a negative heal heals", (HEADER, "return perEnemy > 0 ? perEnemy * enemies : 0.0;", "return perEnemy * enemies;")),
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
        self.assertEqual(runes(), ["Penitence", "Mass Verdict", "Deliberation", "Resolved", "Debilitate"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "radius_yards", "immobilize_duration_seconds")], [20, 20, 6])
        self.assertEqual((value("Penitence", "heal_per_second_life"), value("Penitence", "duration_seconds")), (2682, 3))
        self.assertEqual(value("Deliberation", "immobilize_duration_seconds"), 10)
        self.assertEqual(value("Resolved", "crit_chance_pct"), 8)
        self.assertEqual((value("Debilitate", "enemy_damage_pct"), value("Debilitate", "duration_seconds")), (40, 6))

    def test_the_tunable(self):
        row = tunables()["judgment_penitence_tick_seconds"]
        self.assertEqual((row["d3_value"], row["value"]), ("1", ""))
        self.assertNotIn("PLACEHOLDER", row["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {"judgment_penitence_tick_seconds"})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"radius_yards", "immobilize_duration_seconds", "duration_seconds", "heal_per_second_life",
                                  "enemy_damage_pct", "crit_chance_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "radius_yards"), ("", "immobilize_duration_seconds"),
                            ("Penitence", "heal_per_second_life"), ("Penitence", "duration_seconds"),
                            ("Deliberation", "immobilize_duration_seconds"), ("Resolved", "crit_chance_pct"),
                            ("Debilitate", "enemy_damage_pct"), ("Debilitate", "duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)
        # The area and the Immobilize reach every rune: on its own record or by inheritance.
        for rune in runes():
            for token in ("radius_yards", "immobilize_duration_seconds"):
                self.assertIn((rune, token, ""), mapped, (rune, token))


if __name__ == "__main__":
    unittest.main()
