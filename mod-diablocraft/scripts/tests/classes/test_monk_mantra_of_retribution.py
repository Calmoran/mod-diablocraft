"""diablocraft-2rjqh (Monk 2.3.20): Mantra of Retribution and its five runes.

What this proves, and how:

  * **The rules that need no core type.** tests/monk_mantra_of_retribution/harness.cpp compiles the real
    dc_monk_mantra_of_retribution.h with the sheets' numbers: a reflected hit is the passive's 101% (Retaliation's own 202%),
    the activation adds what its 202% adds over the passive for its 3 seconds (202% and Retaliation's 303%), a chance procs
    under the roll and a blank chance never. That one Mantra is in force at a time is test_monk_mantras.py's. Ten mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every number Retribution's section of dc_monk_mantras.cpp reads by name is a row of
    monk_skill_values.csv for the skill or its rune, or a tunable of data/tunables/monk.csv with the power file's value
    (Collateral Damage's 8 yard blast, the aura's 1 second look); Against All Odds' chance is a blank tunable (the designer's).
  * **The wiring.** dc_monk.cpp hands the Mantra's spell ids to its own file in Cast and the hit taken in Taken; dc_combat.cpp
    calls Monk::Taken beside Passives::Taken at the three places a player's damage taken is set (not the periodic one).

What it does not prove: anything on a running server. The reflect, the stun, the Spirit, the blast and the attack speed need a
Monk in a group and are docs/test-diablocraft-2rjqh.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_mantra_of_retribution.py
"""

import csv
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import monk_source

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
SOURCES = ["src/classes/monk/dc_monk_mantra_of_retribution.h", "tests/monk_mantra_of_retribution/harness.cpp"]
HEADER = "src/classes/monk/dc_monk_mantra_of_retribution.h"
SKILL = "Mantra of Retribution"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "monk_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "monk.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/monk_mantra_of_retribution/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_pct", "passive"), value("", "damage_pct", "active"),
               value("Retaliation", "damage_pct"), value("", "duration_seconds"),
               value("Indignation", "proc_chance_pct"), value("Collateral Damage", "proc_chance_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 13, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the boost adds nothing", (HEADER, "(boosted && boost > 0 ? boost : 0.0)", "0.0")),
            ("the boost is always on", (HEADER, "(boosted && boost > 0 ? boost : 0.0)", "boost")),
            ("the chance itself procs", (HEADER, "rollPct < chancePct", "rollPct <= chancePct")),
            ("a blank chance procs", (HEADER, "chancePct > 0 && rollPct < chancePct", "rollPct <= chancePct || chancePct <= 0")),
            ("a hit may be negative", (HEADER, "return std::max(0.0, passive +", "return (passive +")),
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
    def test_the_numbers_the_code_reads_are_the_sheets(self):
        self.assertEqual((value("", "damage_pct", "passive"), value("", "damage_pct", "active")), (101, 202))
        self.assertEqual((value("", "duration_seconds"), value("", "radius_yards"), value("", "cost_resource")), (3, 60, 50))
        self.assertEqual(value("Retaliation", "damage_pct"), 202)
        self.assertEqual(value("Transgression", "attack_speed_pct"), 10)
        self.assertEqual((value("Indignation", "proc_chance_pct"), value("Indignation", "stun_duration_seconds")), (20, 3))
        self.assertEqual(value("Against All Odds", "gain_resource"), 3)
        self.assertEqual((value("Collateral Damage", "proc_chance_pct"), value("Collateral Damage", "damage_pct")), (75, 101))

    def test_the_records_and_their_elements(self):
        runes = {r["rune_name"]: r for r in read(D3 / "monk_runes.csv") if r["skill_name"] == SKILL}
        self.assertEqual(set(runes), {"Retaliation", "Transgression", "Indignation", "Against All Odds", "Collateral Damage"})
        self.assertEqual({n: r["element"] for n, r in runes.items()},
                         {"Retaliation": "Fire", "Transgression": "Holy", "Indignation": "Holy",
                          "Against All Odds": "Holy", "Collateral Damage": "Holy"})
        skill = next(r for r in read(D3 / "monk_skills.csv") if r["skill_name"] == SKILL)
        self.assertEqual((skill["element"], skill["resource_cost"]), ("Holy", "50"))
        row = next(r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual((row["target_type"], float(row["radius_yards"])), ("self_allies", 60))

    def test_the_tunables_are_the_power_files_or_alexs(self):
        self.assertEqual(tune("mantra_of_retribution_buff_tick_seconds"), 1)
        self.assertEqual(tune("mantra_of_retribution_detonation_radius_yards"), 8)
        chance = tunables()["mantra_of_retribution_spirit_chance_pct"]
        # no sheet or power file gives it: the designer's card q-1014-11, final (bead fwrjm)
        self.assertEqual((chance["d3_value"], chance["value"]), ("", "25"))
        self.assertIn("q-1014-11", chance["notes"])

    def test_every_name_the_code_reads_exists(self):
        read_tunables = monk_source.tunables("Retribution")
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("mantra_of_retribution_")})
        tokens = {token for token, _ in monk_source.reads("Retribution")}
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "proc_chance_pct", "stun_duration_seconds", "gain_resource", "radius_yards",
                                  "duration_seconds", "attack_speed_pct"})


if __name__ == "__main__":
    unittest.main()
