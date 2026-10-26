"""Akarat's Champion and its five runes (src/classes/crusader/dc_crusader_akarats_champion.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_akarats_champion/harness.cpp compiles the real
    dc_crusader_akarats_champion.h with the sheets' own rune names and numbers: each rune name is its rune; the
    transformation is on until its time is over and the bonus is the sheet's only while it is; the Wrath is paid for each
    whole second; Fire Starter burns the same enemy again only after the gap; Rally cuts by the sheet's seconds and never
    more than is left; Prophet saves the first fatal blow and nothing else. Fourteen mutations planted in a scratch copy
    must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_akarats_champion.cpp reads by name is a row of
    crusader_skill_values.csv for Akarat's Champion, the generated value map says whose record holds it, and the numbers
    are the researched ones: a 90 second cooldown, 35% damage and 5 Wrath a second for 20 seconds, Fire Starter 460% over 3
    seconds, Embodiment of Power 10 Wrath a second, Rally 12 seconds, Prophet 150% Armor, Hasteful 15% attack speed. Every
    tunable it reads is a row of data/tunables/crusader.csv: the burn's gap with the power file's number
    (Power/X1_Crusader_AkaratsChampion.pow) as its D3 value, the burn's tick the closed card's 0.5 seconds (six ticks).
  * **The cast deals no damage of its own.** BasePct answers 0 for the skill and every rune.

What it does not prove: anything on a running server, or how the client draws the transformation.

    python mod-diablocraft/scripts/tests/classes/test_crusader_akarats_champion.py
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
HEADER = "src/classes/crusader/dc_crusader_akarats_champion.h"
SOURCES = [HEADER, "src/combat/dc_damage_buckets.h", "tests/crusader_akarats_champion/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_akarats_champion.cpp"
SKILL = "Akarat's Champion"
POW = "Power/X1_Crusader_AkaratsChampion.pow"


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
    return {r["name"]: r for r in read(MODULE / "data/tunables/crusader.csv") if r["name"].startswith("akarats_champion_")}


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
    binary = harness_env.build([MODULE / "tests/crusader_akarats_champion/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_bonus_pct"), value("", "duration_seconds"),
               float(tunables()["akarats_champion_fire_starter_icd_factor"]["d3_value"]),
               value("Rally", "cooldown_reduction_seconds")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 18, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Hasteful;", "return Rune::Prophet;")),
            ("the form never ends", (HEADER, "return until > now;", "return true;")),
            ("the form ends a moment early", (HEADER, "return until > now;", "return until > now + 1;")),
            ("the bonus is always on", (HEADER, "return active && bonusPct > 0 ? bonusPct : 0.0;", "return bonusPct > 0 ? bonusPct : 0.0;")),
            ("a part second is paid", (HEADER, "static_cast<unsigned>(std::floor(durationSeconds + 1e-9))", "static_cast<unsigned>(std::ceil(durationSeconds))")),
            ("the gap ignores the speed", (HEADER, "factor / attacksPerSecond * 1000.0", "factor * 1000.0")),
            ("the first burn waits", (HEADER, "return !burnedBefore || now >= last + gapMs;", "return burnedBefore && now >= last + gapMs;")),
            ("the same enemy burns at once", (HEADER, "now >= last + gapMs", "now >= last")),
            ("Rally cuts more than is left", (HEADER, "std::min(remainingMs, static_cast<std::uint32_t>(std::llround(seconds * 1000.0)))", "static_cast<std::uint32_t>(std::llround(seconds * 1000.0))")),
            ("Rally cuts nothing", (HEADER, "return seconds > 0 ? std::min", "return seconds > 1e9 ? std::min")),
            ("a blow that leaves Life is fatal", (HEADER, "damage >= health;", "damage + 1 >= health;")),
            ("Prophet saves again", (HEADER, "rune == Rune::Prophet && !alreadySaved &&", "rune == Rune::Prophet &&")),
            ("every rune saves", (HEADER, "rune == Rune::Prophet && !alreadySaved", "!alreadySaved")),
            ("a dead player is saved", (HEADER, "&& health > 0 && damage >= health", "&& damage >= health")),
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
        self.assertEqual(runes(), ["Fire Starter", "Embodiment of Power", "Rally", "Prophet", "Hasteful"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "damage_bonus_pct"),
                          value("", "regen_per_second_resource"), value("", "duration_seconds")], [90, 35, 5, 20])
        self.assertEqual((value("Fire Starter", "damage_pct"), value("Fire Starter", "dot_duration_seconds")), (460, 3))
        self.assertEqual(value("Embodiment of Power", "regen_per_second_resource"), 10)
        self.assertEqual(value("Rally", "cooldown_reduction_seconds"), 12)
        self.assertEqual(value("Prophet", "armor_pct"), 150)
        self.assertEqual(value("Hasteful", "attack_speed_pct"), 15)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"duration_seconds", "regen_per_second_resource", "armor_pct", "attack_speed_pct",
                                  "cooldown_reduction_seconds", "damage_pct", "dot_duration_seconds", "damage_bonus_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_bonus_pct"), ("", "regen_per_second_resource"), ("", "duration_seconds"),
                            ("Fire Starter", "damage_pct"), ("Fire Starter", "dot_duration_seconds"),
                            ("Embodiment of Power", "regen_per_second_resource"), ("Rally", "cooldown_reduction_seconds"),
                            ("Prophet", "armor_pct"), ("Hasteful", "attack_speed_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    def test_the_gap_is_the_power_files_and_the_tick_is_the_closed_cards(self):
        rows = tunables()
        self.assertEqual(set(rows), {"akarats_champion_fire_starter_icd_factor", "akarats_champion_fire_starter_tick_seconds"})
        gap = rows["akarats_champion_fire_starter_icd_factor"]
        self.assertEqual((gap["d3_value"], gap["value"]), ("0.9", ""))
        self.assertIn(POW, gap["notes"])
        self.assertNotIn("PLACEHOLDER", gap["notes"])
        tick = rows["akarats_champion_fire_starter_tick_seconds"]
        self.assertEqual((tick["d3_value"], tick["value"]), ("", "0.5"))
        self.assertNotIn("PLACEHOLDER", tick["notes"])
        self.assertIn("q-1021-29", tick["notes"])

    def test_the_burn_is_six_ticks_of_a_sixth_of_the_sheets_total(self):
        seconds, total = value("Fire Starter", "dot_duration_seconds"), value("Fire Starter", "damage_pct")
        tick = float(tunables()["akarats_champion_fire_starter_tick_seconds"]["value"])
        ticks = int(seconds / tick + 1e-9)
        self.assertEqual(ticks, 6)
        self.assertAlmostEqual(total / ticks, 460 / 6)

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(tunables()))


if __name__ == "__main__":
    unittest.main()
