"""diablocraft-ogwtu (Monk 2.3.06): Tempest Rush and its five runes.

What this proves, and how:

  * **The rules that need no core type.** tests/monk_tempest_rush/harness.cpp compiles the real dc_monk_tempest_rush.h with the
    sheets' numbers: a per-second number spread over ticks adds up to itself (390% a second in 0.2 s ticks is 78% a tick, 30
    Spirit a second is 6 a tick), the press covers the first second and the ticks after it pay, Flurry counts one stack a
    attack period up to its cap, Bluster knocks an enemy back once. Six mutations planted in a scratch copy must each make it
    fail.
  * **The code reads what the sheets state.** Every number dc_monk_tempest_rush.cpp reads by name is a row of
    monk_skill_values.csv for that very rune (or the skill, which a rune inherits) or a tunable of data/tunables/monk.csv with
    the power file's value: 390% a second and 30 Spirit a second (500% and 25 with Northern Breeze), Bluster's 20% for 4
    seconds, Tailwind's 25%, Electric Field's 135% over 20 yards, Flurry's 90% over 15 yards; the radius 7, the tick 0.2 s, the
    knockback 8, Electric Field's 0.25 s tick and Flurry's 100 stacks.
  * **The wiring.** dc_monk.cpp hands Tempest Rush's spell ids to its own file in BasePct, Begin and Cast; dc_combat.cpp asks
    Monk::Toggle in the cast check beside Whirlwind's second-press stop.

What it does not prove: anything on a running server. The channel, the pay, the knockback and the speed need the Monk's records
(3mk78) and are docs/test-diablocraft-ogwtu.md's, live. It is press-to-start, press-again-to-stop until the Combat bead
diablocraft-5s5rl gives the Monk channel records and a hold-to-channel row.

    python mod-diablocraft/scripts/tests/classes/test_monk_tempest_rush.py
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
SOURCES = ["src/classes/monk/dc_monk_tempest_rush.h", "tests/monk_tempest_rush/harness.cpp"]
HEADER = "src/classes/monk/dc_monk_tempest_rush.h"
SKILL = "Tempest Rush"


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
    binary = harness_env.build([MODULE / "tests/monk_tempest_rush/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_pct"), value("", "cost_resource"), tune("tempest_rush_tick_seconds"),
               value("Electric Field", "damage_pct"), tune("tempest_rush_field_tick_seconds"),
               tune("tempest_rush_flurry_max_stacks")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a tick is the whole second", (HEADER, "perSecond * tickSeconds", "perSecond")),
            ("the press covers no second", (HEADER, "return now < until;", "return false;")),
            ("the press covers every second", (HEADER, "return now < until;", "return true;")),
            ("the stacks are not capped", (HEADER, "std::min<double>(cap, std::floor(elapsedSeconds * attacksPerSecond))",
                                           "std::floor(elapsedSeconds * attacksPerSecond)")),
            ("the stacks are rounded up", (HEADER, "std::floor(elapsedSeconds * attacksPerSecond)",
                                           "std::ceil(elapsedSeconds * attacksPerSecond)")),
            ("every sight knocks back", (HEADER, "return guids.insert(guid).second;", "return guids.insert(guid).second || true;")),
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
        self.assertEqual((value("", "damage_pct"), value("", "cost_resource")), (390, 30))
        self.assertEqual((value("Northern Breeze", "damage_pct"), value("Northern Breeze", "cost_resource")), (500, 25))
        self.assertEqual((value("Bluster", "enemy_damage_pct"), value("Bluster", "duration_seconds")), (20, 4))
        self.assertEqual(value("Tailwind", "movement_speed_pct"), 25)
        self.assertEqual((value("Electric Field", "radius_yards"), value("Electric Field", "damage_pct")), (20, 135))
        self.assertEqual((value("Flurry", "radius_yards"), value("Flurry", "damage_pct")), (15, 90))

    def test_the_tunables_are_the_power_files_and_the_targeting_rows(self):
        row = next(r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual(row["target_type"], "self_moving_aoe")
        self.assertEqual(tune("tempest_rush_radius_yards"), float(row["radius_yards"]))
        self.assertEqual(tune("tempest_rush_radius_yards"), 7)
        self.assertEqual(tune("tempest_rush_tick_seconds"), 0.2)
        self.assertEqual(tune("tempest_rush_knockback_yards"), 8)
        self.assertEqual(tune("tempest_rush_field_tick_seconds"), 0.25)
        self.assertEqual(tune("tempest_rush_flurry_max_stacks"), 100)

    def test_every_name_the_code_reads_exists(self):
        text = (MODULE / "src/classes/monk/dc_monk_tempest_rush.cpp").read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("tempest_rush_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own)\((?:spellId|tailwind|rune|SkillId\(\)|IsRune\(spellId, "Northern Breeze"\) \? spellId : SkillId\(\)), "([a-z_]+)"',
                                text))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "cost_resource", "enemy_damage_pct", "duration_seconds", "movement_speed_pct",
                                  "radius_yards"})


if __name__ == "__main__":
    unittest.main()
