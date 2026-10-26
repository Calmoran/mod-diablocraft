"""diablocraft-im88g (Monk 2.3.04): Way of the Hundred Fists and its five runes.

What this proves, and how:

  * **The logic.** tests/monk_hundred_fists/harness.cpp compiles the real dc_monk_hundred_fists.h (with dc_monk_fists.h's
    Combo) and feeds it the sheets' own numbers: the stages count 1, 2, 3 and start again; only stage 2 is a series, 7
    punches and 10 with Hands of Lightning; the series' punches add up to the sheet's 190% and 423%; stage 3's circle
    sits 5 yards in front of the Monk with a radius of 10; Fists of Fury's stacks add, run out one by one, stop at the cap
    and replace the oldest. Mutations planted in a scratch copy must each make it fail.
  * **The sheets.** The numbers the code reads are the researched ones (monk_skill_values.csv, data/tunables/monk.csv),
    each tunable has a note naming its source.

What it does not prove: anything on a running server. The punches, the cone, the area, the damage over time, the buffs
and the wave are docs/test-diablocraft-im88g.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_hundred_fists.py
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
SOURCES = ["src/classes/monk/dc_monk_fists.h", "src/classes/monk/dc_monk_hundred_fists.h",
           "tests/monk_hundred_fists/harness.cpp"]
SKILL = "Way of the Hundred Fists"


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
    binary = harness_env.build([MODULE / "tests/monk_hundred_fists/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("fists_combo_window_frames"), tune("fists_combo_frames_per_second"),
               value("", "damage_pct"), value("Hands of Lightning", "damage_pct"),
               value("Hands of Lightning", "hit_count", "from"), value("Hands of Lightning", "hit_count", "to"),
               tune("hundred_fists_stage3_radius_yards"), tune("hundred_fists_stage3_offset_yards"),
               value("Fists of Fury", "damage_pct"), value("Fists of Fury", "dot_duration_seconds"),
               tune("hundred_fists_fury_max_stacks"), tune("hundred_fists_fury_tick_seconds"),
               value("Blazing Fists", "max_stacks_count"), value("Blazing Fists", "duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_stages_the_series_and_the_stacks(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 25, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        path = "src/classes/monk/dc_monk_hundred_fists.h"
        mutations = [
            ("stage 2 is not a series", (path, "if (stage != 2)\n            return 1;", "")),
            ("Hands of Lightning keeps the base hits", (path, "handsOfLightning ? upgradedHits : baseHits", "baseHits")),
            ("the series' punches are not divided", (path, "return stage == 2 && hits ? totalPct / hits : totalPct;",
                                                    "return totalPct;")),
            ("the area is centred on the Monk", (path, "monk.x + std::cos(facing) * offsetYards",
                                                 "monk.x")),
            ("the stacks have no cap", (path, "if (ends.size() >= cap)", "if (false)")),
            ("the cap drops the newest, not the oldest", (path, "ends.erase(ends.begin());\n            ends.push_back(now + durationMs);",
                                                          "return;\n            ends.push_back(now + durationMs);")),
            ("a stack pays its whole total in the first tick", (path, "double(to - from) / double(durationMs)", "1.0")),
            ("a late tick pays past the stack's end", (path, "std::min(end, now)", "now")),
            ("the wave has no length", (path, "along >= 0 && along <= lengthYards &&", "along >= 0 &&")),
            ("the wave has no width", (path, "std::fabs(across) <= widthYards / 2", "true")),
            ("Blazing Fists has no cap", (path, "std::min(stacks + 1, std::max(1u, cap))", "stacks + 1")),
            ("Blazing Fists does not renew its time", (path, "until = now + durationMs;\n            return stacks;",
                                                      "if (stacks == 1)\n                until = now + durationMs;\n            return stacks;")),
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
        self.assertEqual((value("", "damage_pct"), value("", "generated_resource")), (190, 12))
        self.assertEqual((value("Hands of Lightning", "hit_count", "from"), value("Hands of Lightning", "hit_count", "to"),
                          value("Hands of Lightning", "damage_pct")), (7, 10, 423))
        self.assertEqual((value("Fists of Fury", "damage_pct"), value("Fists of Fury", "dot_duration_seconds")), (60, 3))
        self.assertEqual([value("Blazing Fists", t) for t in ("attack_speed_pct", "duration_seconds", "max_stacks_count")],
                         [5, 5, 3])
        self.assertEqual((value("Assimilation", "damage_bonus_pct"), value("Assimilation", "duration_seconds")), (5, 5))
        self.assertEqual(value("Windforce Flurry", "damage_pct"), 500)

    def test_the_power_file_agrees_with_the_split(self):
        # Power/Monk_WayOfTheHundredFists.pow: SF_1 0.27142857 x SF_27 7 hits = 1.9; SF_12 (SF_1 x SF_21 1.5590909) x 10 = 4.23.
        self.assertAlmostEqual(0.27142857142857142857 * 7 * 100, value("", "damage_pct"), places=6)
        self.assertAlmostEqual(0.27142857142857142857 * 1.559090909090909 * 10 * 100, value("Hands of Lightning", "damage_pct"),
                               delta=0.5)

    def test_the_tunables_are_the_researched_ones(self):
        self.assertEqual(tune("hundred_fists_stage3_radius_yards"), 10)
        self.assertEqual(tune("hundred_fists_stage3_offset_yards"), 5)
        self.assertEqual(tune("hundred_fists_fury_max_stacks"), 15)
        self.assertEqual(tune("hundred_fists_fury_tick_seconds"), 0.5)


if __name__ == "__main__":
    unittest.main()
