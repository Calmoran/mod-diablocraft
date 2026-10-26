"""diablocraft-56z6v (Monk 2.3.11): Cyclone Strike and its five runes.

What this proves, and how:

  * **The logic.** tests/monk_cyclone_strike/harness.cpp compiles the real dc_monk_cyclone_strike.h and feeds it the sheets' own
    numbers: the pull takes the nearest 16 enemies, nearest first; each lands 1 to 9 yards from the Monk on the line it came
    along, inside the blast's 10 yards; Implosion's 34 yard pull is wider than the skill's 24; the blast's edge. Mutations
    planted in a scratch copy must each make it fail.
  * **The sheets.** The numbers the code reads are the researched ones (monk_skill_values.csv, data/tunables/monk.csv; the power
    file's 2.61, 1.7395 and 4.54 agree with 261 and 454), every name dc_monk_cyclone_strike.cpp reads exists, and the cast path
    calls Monk::Aim before Monk::Begin.

What it does not prove: anything on a running server. The pull, the blast, the freeze and the heal are
docs/test-diablocraft-56z6v.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_cyclone_strike.py
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
SOURCES = ["src/classes/monk/dc_monk_cyclone_strike.h", "tests/monk_cyclone_strike/harness.cpp"]
SKILL = "Cyclone Strike"


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
    binary = harness_env.build([MODULE / "tests/monk_cyclone_strike/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "target_count"), value("", "radius_yards"), value("Implosion", "radius_yards"),
               tune("cyclone_strike_pull_land_min_yards"), tune("cyclone_strike_pull_land_spread_yards"),
               tune("cyclone_strike_blast_radius_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_pull_the_landing_and_the_blast(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 18, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        path = "src/classes/monk/dc_monk_cyclone_strike.h"
        mutations = [
            ("the pull takes the farthest", (path, "return distances[a] < distances[b];", "return distances[a] > distances[b];")),
            ("the pull has no cap", (path, "std::min<std::size_t>(order.size(), count)", "order.size()")),
            ("a tie is not kept in order", (path, "std::stable_sort", "std::sort")),
            ("the landing share is not clamped", (path, "std::clamp(share, 0.0, 1.0)", "share")),
            ("the landing ignores the minimum", (path, "return minYards + spreadYards", "return spreadYards")),
            ("the landing is on the wrong line", (path, "monk.x + dx / length * yards", "monk.x + dy / length * yards")),
            ("the landing is not a distance", (path, "monk.y + dy / length * yards", "monk.y + dy / length")),
            ("the blast has no edge", (path, "std::hypot(at.x - monk.x, at.y - monk.y) <= radiusYards", "true")),
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
        self.assertEqual([value("", t) for t in ("cost_resource", "target_count", "radius_yards", "damage_pct")], [50, 16, 24, 261])
        self.assertEqual(value("Sunburst", "damage_pct"), 454)
        self.assertEqual(value("Implosion", "radius_yards"), 34)
        self.assertEqual([value("Soothing Breeze", t) for t in ("radius_yards", "heal_life", "healing_bonus_share_pct")],
                         [24, 31036, 17])
        self.assertEqual(value("Eye of the Storm", "cost_resource"), 26)
        self.assertEqual(value("Wall of Wind", "freeze_duration_seconds"), 1.5)

    def test_the_power_file_agrees_with_the_sheet(self):
        # Power/Monk_CycloneStrike.pow: SF_4 2.61 x SF_15 1.7394636 = 4.54; SF_9 24 + SF_16 10 = 34; SF_5 16; SF_28 1.5;
        # SF_22 50 - SF_25 24 = 26; SF_21 0.17. No duration differs from the sheet, so no sheet row changed.
        self.assertEqual(value("", "damage_pct"), 2.61 * 100)
        self.assertAlmostEqual(2.61 * 1.739463601532567 * 100, value("Sunburst", "damage_pct"), delta=0.5)
        self.assertEqual(value("", "radius_yards") + 10, value("Implosion", "radius_yards"))
        self.assertEqual(value("", "cost_resource") - 24, value("Eye of the Storm", "cost_resource"))
        self.assertEqual(value("Soothing Breeze", "healing_bonus_share_pct"), 0.17 * 100)

    def test_the_tunables_are_the_researched_ones(self):
        self.assertEqual([tune(n) for n in ("cyclone_strike_pull_land_min_yards", "cyclone_strike_pull_land_spread_yards",
                                             "cyclone_strike_blast_radius_yards")], [1, 8, 10])


if __name__ == "__main__":
    unittest.main()
