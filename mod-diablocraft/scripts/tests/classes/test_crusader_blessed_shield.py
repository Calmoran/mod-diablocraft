"""Blessed Shield and its five runes (src/classes/crusader/dc_crusader_blessed_shield.h and .cpp, and the Block Chance share).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_blessed_shield/harness.cpp compiles the real dc_crusader_blessed_shield.h
    with the sheets' own rune names and numbers: each rune name is its rune; the ricochet goes from each enemy to the nearest one
    not hit yet inside 20 yards and stops when none is left; Staggering Shield's first enemy has a 25% chance and each after it 5
    points less, never below nothing; the line Piercing Shield flies along has a length and half a width each side. Seven
    mutations planted in a scratch copy (two runes share a name, the ricochet goes to the farthest, to an enemy already hit, past
    the radius, the stun chance does not fall, it falls below nothing, the pierce has no width) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_blessed_shield.cpp reads by name is a row of
    crusader_skill_values.csv for Blessed Shield (or the rune that states it), the generated value map says whose record holds it,
    and the numbers are the researched ones: 430% plus 250% of the Block Chance, 3 ricochets, Staggering Shield 25% less 5 for 2
    seconds, Combust 33% for 310% within 10 yards, Divine Aegis 5% and 5% for 4 seconds, Shattering Throw 3 fragments of 170%,
    Piercing Shield a 50% knock. Every tunable it reads is a row of data/tunables/crusader.csv: the power file's bounce radius and
    range, and the designer's answers for the pierce's width and the knock's distance (3 yards each).
  * **The chain ruling holds** (the PM's of 2026-10-17): every rune but Piercing Shield keeps the three ricochets in the record's chain
    slot 1 (test_crusader_records), and Piercing Shield's code does not call the ricochet.

What it does not prove: anything on a running server. The throw, the ricochets, the fragments, the pierce are
docs/test-diablocraft-7t4gv.8.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_crusader_blessed_shield.py
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
HEADER = "src/classes/crusader/dc_crusader_blessed_shield.h"
SOURCES = [HEADER, "tests/crusader_blessed_shield/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_blessed_shield.cpp"
SKILL = "Blessed Shield"


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
    binary = harness_env.build([MODULE / "tests/crusader_blessed_shield/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("blessed_shield_bounce_yards"), value("Staggering Shield", "proc_chance_pct", "base"),
               value("Staggering Shield", "proc_chance_pct", "reduction")] + runes() + [tune("blessed_shield_pierce_width_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 17, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Combust;", "return Rune::DivineAegis;")),
            ("the ricochet goes to the farthest", (HEADER, "distances[i] < distances[std::size_t(best)]", "distances[i] > distances[std::size_t(best)]")),
            ("the ricochet goes to an enemy already hit", (HEADER, "if (!hit[i] && distances[i] <= radius", "if (distances[i] <= radius")),
            ("the ricochet goes past the radius", (HEADER, "distances[i] <= radius && (best", "(best")),
            ("the stun chance does not fall", (HEADER, "return std::max(0.0, base - reduction * place);", "return base;")),
            ("the stun chance falls below nothing", (HEADER, "return std::max(0.0, base - reduction * place);", "return base - reduction * place;")),
            ("the pierce has no width", (HEADER, "return width > 0 && along >= 0", "return along >= 0")),
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
        self.assertEqual(runes(), ["Staggering Shield", "Combust", "Divine Aegis", "Shattering Throw", "Piercing Shield"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("cost_resource", "damage_pct", "block_chance_share_pct", "target_count")], [20, 430, 250, 3])
        self.assertEqual([value("Staggering Shield", "proc_chance_pct", q) for q in ("base", "reduction")], [25, 5])
        self.assertEqual(value("Staggering Shield", "stun_duration_seconds"), 2)
        self.assertEqual([value("Combust", t) for t in ("proc_chance_pct", "damage_pct", "radius_yards")], [33, 310, 10])
        self.assertEqual([value("Divine Aegis", t) for t in ("armor_pct", "life_regen_pct", "duration_seconds")], [5, 5, 4])
        self.assertEqual((value("Shattering Throw", "spawn_count"), value("Shattering Throw", "damage_pct")), (3, 170))
        self.assertEqual(value("Piercing Shield", "proc_chance_pct"), 50)

    def test_the_tunables(self):
        rows = tunables()
        for name, number, source in (("blessed_shield_bounce_yards", "20", "SF_13"), ("blessed_shield_range_yards", "70", "SF_0")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""), name)
            self.assertIn(source, rows[name]["notes"])
        # The designer's answers (cards q-1021-15 and -16): the line is 3 yards wide and the knock 3 yards; no placeholder mark is left.
        for name, card in (("blessed_shield_pierce_width_yards", "q-1021-15"), ("blessed_shield_knockaside_yards", "q-1021-16")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), ("", "3"), name)
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)
            self.assertIn(card, rows[name]["notes"], name)

    def test_piercing_shield_pierces_a_lane_3_yards_wide_and_knocks_back_3_yards(self):
        self.assertEqual((tune("blessed_shield_pierce_width_yards"), tune("blessed_shield_knockaside_yards")), (3, 3))
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('Abilities::Knockback(player, enemy, Tune("blessed_shield_knockaside_yards"));', text)
        self.assertIn('width = Tune("blessed_shield_pierce_width_yards")', text)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("blessed_shield_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "block_chance_share_pct", "target_count", "stun_duration_seconds", "proc_chance_pct",
                                  "radius_yards", "armor_pct", "life_regen_pct", "duration_seconds", "spawn_count"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "damage_pct", ""), ("", "block_chance_share_pct", ""), ("", "target_count", ""),
                                       ("Staggering Shield", "proc_chance_pct", "base"), ("Staggering Shield", "proc_chance_pct", "reduction"),
                                       ("Staggering Shield", "stun_duration_seconds", ""), ("Combust", "proc_chance_pct", ""),
                                       ("Combust", "damage_pct", ""), ("Combust", "radius_yards", ""), ("Divine Aegis", "armor_pct", ""),
                                       ("Divine Aegis", "life_regen_pct", ""), ("Divine Aegis", "duration_seconds", ""),
                                       ("Shattering Throw", "spawn_count", ""), ("Shattering Throw", "damage_pct", ""),
                                       ("Piercing Shield", "proc_chance_pct", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertEqual(mapped[(rune, token, qualifier)]["origin"], "own")

    def test_the_hit_is_the_skills_for_every_rune_and_the_share_is_its_too(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('return Numbers::Get(BaseId(Skill), "damage_pct");', text)
        self.assertIn('std::make_pair(Numbers::Num(base, "damage_pct"), Numbers::Num(base, "block_chance_share_pct"))', text)
        share = (MODULE / "src/classes/crusader/dc_crusader_block_share.cpp").read_text(encoding="utf-8")
        self.assertIn("BlessedShield::Main(spellId)", share)


if __name__ == "__main__":
    unittest.main()
