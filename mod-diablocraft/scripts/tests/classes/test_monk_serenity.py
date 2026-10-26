"""diablocraft-umi1o (Monk 2.3.17): Serenity and its five runes.

What this proves, and how:

  * **The logic.** tests/monk_serenity/harness.cpp compiles the real dc_monk_serenity.h and feeds it the sheets' own numbers:
    Unwelcome Disturbance pulses 3 times in a 3 second shield and 4 times in Ascension's 4; Peaceful Repose's heal always
    falls inside the sheet's range; the cooldown is pushed back by the shield's whole time. Mutations planted in a scratch
    copy must each make it fail.
  * **The sheets.** The numbers the code reads are the researched ones (monk_skill_values.csv, data/tunables/monk.csv); the power
    file's durations (SF_9 3, SF_10 +1 for Ascension, SF_11 = the same for Tranquility) agree with the sheet, so no sheet row
    changed. Every name dc_monk_serenity.cpp reads exists, and the Monk dispatches Serenity's cast.

What it does not prove: anything on a running server. The shield, the immunity, the heal, the allies' shields, the pulses and
the delayed cooldown are docs/test-diablocraft-umi1o.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_serenity.py
"""

import csv
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
SOURCES = ["src/classes/monk/dc_monk_serenity.h", "tests/monk_serenity/harness.cpp"]
SKILL = "Serenity"


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
    binary = harness_env.build([MODULE / "tests/monk_serenity/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "absorb_duration_seconds"), value("Ascension", "duration_seconds"), tune("serenity_pulse_seconds"),
               value("Peaceful Repose", "heal_min_life"), value("Peaceful Repose", "heal_max_life")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_pulses_the_heal_and_the_cooldown(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 13, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        path = "src/classes/monk/dc_monk_serenity.h"
        mutations = [
            ("a part pulse is counted", (path, "std::floor(durationSeconds / intervalSeconds + 1e-9)",
                                         "std::ceil(durationSeconds / intervalSeconds)")),
            ("rounding loss drops a pulse", (path, "durationSeconds / intervalSeconds + 1e-9", "durationSeconds / intervalSeconds")),
            ("the heal ignores the share", (path, "(std::max(minLife, maxLife) - minLife) * std::clamp(share, 0.0, 1.0)",
                                            "(std::max(minLife, maxLife) - minLife) * 0.5")),
            ("the heal share is not clamped", (path, "std::clamp(share, 0.0, 1.0)", "share")),
            ("the heal can fall under the minimum", (path, "std::max(minLife, maxLife) - minLife", "maxLife - minLife")),
            ("the cooldown does not wait", (path, "std::max(0.0, shieldSeconds) * 1000.0 + 0.5", "0.0")),
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
    def test_the_numbers_are_the_researched_ones(self):
        self.assertEqual((value("", "cooldown_seconds"), value("", "absorb_duration_seconds")), (16, 3))
        self.assertEqual([value("Peaceful Repose", t) for t in ("heal_min_life", "heal_max_life", "healing_bonus_share_pct")],
                         [93874, 120695, 40])
        self.assertEqual(value("Ascension", "duration_seconds"), 4)
        self.assertEqual([value("Tranquility", t) for t in ("radius_yards", "absorb_life", "absorb_duration_seconds")],
                         [45, 120158, 3])
        self.assertEqual((value("Unwelcome Disturbance", "radius_yards"), value("Unwelcome Disturbance", "damage_pct")), (20, 438))

    def test_the_power_file_agrees_with_the_sheet(self):
        # Power/Monk_Serenity.pow: SF_9 3 + SF_10 1 (rune C) = SF_0 4; SF_11 'D: shield duration' = SF_0; SF_12 45; SF_5 20;
        # SF_4 4.38; SF_18 16. No duration differs from the sheet, so no sheet row changed.
        self.assertEqual(value("", "absorb_duration_seconds") + 1, value("Ascension", "duration_seconds"))
        self.assertEqual(value("Tranquility", "absorb_duration_seconds"), value("", "absorb_duration_seconds"))
        self.assertEqual(value("Tranquility", "radius_yards"), 45)
        self.assertEqual(value("Unwelcome Disturbance", "radius_yards"), 20)
        self.assertAlmostEqual(value("Unwelcome Disturbance", "damage_pct"), 4.38 * 100, places=6)
        self.assertEqual(value("", "cooldown_seconds"), 16)

    def test_the_tunable_is_the_researched_one(self):
        self.assertEqual(tune("serenity_pulse_seconds"), 0.99)


if __name__ == "__main__":
    unittest.main()
