"""diablocraft-wv17q (Monk 2.3.21): Mantra of Healing and its five runes.

What this proves, and how:

  * **The rules that need no core type.** tests/monk_mantra_of_healing/harness.cpp compiles the real
    dc_monk_mantra_of_healing.h with the sheets' numbers: the heal of a pulse is the sheet's number plus a share of the
    Monk's Life per Second over the pulse's seconds, a hit heals its number plus a share of Life per Hit, the absorb is
    raised by the share of the globe bonus (none: 0), Time of Need applies strictly below its threshold, Circular
    Breathing pays its Spirit by the pulse, a holder out of range is the one that left. Which Mantra is in force
    is test_monk_mantras.py's. Eight mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every number Healing's section of dc_monk_mantras.cpp reads by name is a row of
    monk_skill_values.csv for that rune (or the skill, which a rune inherits): 62064 absorbed for 3 seconds, 10728 Life a
    second over 60 yards (Sustenance 21457), 3576 a hit (Boon of Inspiration), +20% Life (Heavenly Body), 3 Spirit a second
    (Circular Breathing), 30% less damage below 50% Life (Time of Need). The pulse is the power file's 1 second.
  * **The wiring.** dc_monk.cpp hands the skill's spell ids to its own file in Cast, starts the pulse on any cast and
    asks it in Landed.

What it does not prove: anything on a running server. The pulse, the absorb and the stats need the Monk's records (3mk78)
and are docs/test-diablocraft-wv17q.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_mantra_of_healing.py
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
SOURCES = ["src/classes/monk/dc_monk_mantra_of_healing.h", "tests/monk_mantra_of_healing/harness.cpp"]
HEADER = "src/classes/monk/dc_monk_mantra_of_healing.h"
SKILL = "Mantra of Healing"


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
    binary = harness_env.build([MODULE / "tests/monk_mantra_of_healing/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "heal_per_second_life"), value("Sustenance", "heal_per_second_life"),
               value("", "life_per_second_share_pct"), value("Boon of Inspiration", "heal_per_hit_life"),
               value("Boon of Inspiration", "life_per_hit_share_pct"), value("", "absorb_life"),
               value("", "healing_bonus_share_pct"), value("Time of Need", "life_threshold_pct"),
               value("Circular Breathing", "regen_per_second_resource")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 21, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the share of Life per Second is lost", (HEADER, "std::max(lifePerSecond, 0.0) * std::max(sharePct, 0.0) / 100.0",
                                                       "0.0")),
            ("the pulse ignores its seconds", (HEADER, "/ 100.0) *\n               pulseSeconds;", "/ 100.0);")),
            ("the globe bonus is not a share", (HEADER, "std::max(sharePct, 0.0) / 100.0 * std::max(globeBonusPct, 0.0) / 100.0",
                                                 "std::max(sharePct, 0.0) / 100.0")),
            ("Time of Need applies at the threshold", (HEADER, "return lifePct < thresholdPct;", "return lifePct <= thresholdPct;")),
            ("Spirit is paid a whole second at a time", (HEADER, "perSecond * pulseSeconds : 0.0", "perSecond : 0.0")),
            ("a holder that stayed has left", (HEADER, "if (!now.count(guid))", "if (now.count(guid))")),
            ("the hit's share is lost", (HEADER, "std::max(lifePerHit, 0.0) * std::max(sharePct, 0.0) / 100.0;\n    }\n\n    // \"absorbs",
                                         "0.0;\n    }\n\n    // \"absorbs")),
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
        self.assertEqual((value("", "absorb_life"), value("", "absorb_duration_seconds"), value("", "healing_bonus_share_pct")),
                         (62064, 3, 15))
        self.assertEqual((value("", "heal_per_second_life"), value("", "life_per_second_share_pct"), value("", "radius_yards")),
                         (10728, 7, 60))
        self.assertEqual(value("", "cost_resource"), 50)
        self.assertEqual((value("Sustenance", "heal_per_second_life"), value("Sustenance", "life_per_second_share_pct")), (21457, 7))
        self.assertEqual((value("Boon of Inspiration", "heal_per_hit_life"), value("Boon of Inspiration", "life_per_hit_share_pct")),
                         (3576, 20))
        self.assertEqual(value("Heavenly Body", "max_life_pct"), 20)
        self.assertEqual(value("Circular Breathing", "regen_per_second_resource"), 3)
        self.assertEqual((value("Time of Need", "damage_reduction_pct"), value("Time of Need", "life_threshold_pct")), (30, 50))
        row = next(r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual((row["target_type"], float(row["radius_yards"])), ("self_allies", 60))

    def test_the_pulse_is_the_power_files(self):
        row = tunables()["mantra_healing_pulse_seconds"]
        self.assertEqual(float(row["d3_value"]), 1)
        self.assertIn("SF_18", row["notes"])

    def test_every_name_the_code_reads_exists(self):
        read_tunables = monk_source.tunables("Healing")
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith("mantra_healing_")})
        tokens = {token for token, _ in monk_source.reads("Healing")}
        sheet_tokens = {r["token"] for r in read(D3 / "monk_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"absorb_life", "healing_bonus_share_pct", "absorb_duration_seconds", "heal_per_second_life",
                                  "life_per_second_share_pct", "heal_per_hit_life", "life_per_hit_share_pct", "max_life_pct",
                                  "life_threshold_pct", "damage_reduction_pct", "regen_per_second_resource", "radius_yards"})


if __name__ == "__main__":
    unittest.main()
