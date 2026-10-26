"""diablocraft-dkf8w (Monk 2.3.07): Wave of Light and its five runes.

What this proves, and how:

  * **The logic.** tests/monk_wave_of_light/harness.cpp compiles the real dc_monk_wave_of_light.h and feeds it the sheets' own
    numbers: Pillar of the Ancients' 785% over 3 seconds is 6 ticks of an equal share; the bell and the pillar stand `offset`
    yards ahead along the direction of the aimed point (not at the cursor); the circle's edge; Shattering Light's line has a
    start, an end, a width and a direction. Mutations planted in a scratch copy must each make it fail.
  * **The sheets.** The numbers the code reads are the researched ones (monk_skill_values.csv, data/tunables/monk.csv), every
    name dc_monk_wave_of_light.cpp reads exists, the two rows the designer sets are blank, and the cast path calls Monk::Ground
    after Monk::Cast.

What it does not prove: anything on a running server. The bell, the pillar's ticks, the stun and the line are
docs/test-diablocraft-dkf8w.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_wave_of_light.py
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
SOURCES = ["src/classes/monk/dc_monk_wave_of_light.h", "tests/monk_wave_of_light/harness.cpp"]
SKILL = "Wave of Light"


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
    binary = harness_env.build([MODULE / "tests/monk_wave_of_light/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Pillar of the Ancients", "damage_pct", "dot"), value("Pillar of the Ancients", "dot_duration_seconds"),
               tune("wave_of_light_pillar_tick_seconds"), tune("wave_of_light_bell_offset_yards"),
               tune("wave_of_light_pillar_radius_yards"), tune("wave_of_light_line_start_yards"),
               tune("wave_of_light_line_end_yards"), value("", "damage_pct"), value("Empowered Wave", "damage_pct"),
               tune("wave_of_light_bell_ticks")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_ticks_the_point_ahead_and_the_line(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 26, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        path = "src/classes/monk/dc_monk_wave_of_light.h"
        mutations = [
            ("the ticks are not rounded down", (path, "std::floor(durationSeconds / tickSeconds + 1e-9)",
                                                "std::ceil(durationSeconds / tickSeconds + 0.5)")),
            ("a tick pays the whole total", (path, "return ticks ? totalPct / ticks : 0.0;", "return totalPct;")),
            ("the bell ticks are not spaced by the tick count", (path, "1000.0 / attacksPerSecond / ticks", "1000.0 / attacksPerSecond")),
            ("the bell ticks are not rounded", (path, "1000.0 / attacksPerSecond / ticks + 0.5", "1000.0 / attacksPerSecond / ticks")),
            ("the bell falls at the cursor", (path, "monk.x + std::cos(heading) * yards", "monk.x + yards * 3")),
            ("the heading ignores the facing fallback", (path, "std::hypot(dx, dy) < 1e-6 ? facing : std::atan2(dy, dx)",
                                                         "std::atan2(dy, dx)")),
            ("the circle has no edge", (path, "std::hypot(at.x - centre.x, at.y - centre.y) <= radiusYards", "true")),
            ("the line has no start", (path, "along >= startYards &&", "")),
            ("the line has no end", (path, "along <= endYards &&", "")),
            ("the line has no width", (path, "std::fabs(across) <= widthYards / 2", "true")),
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
        self.assertEqual((value("", "cost_resource"), value("", "damage_pct")), (75, 835))
        self.assertEqual(value("Wall of Light", "stun_duration_seconds"), 1)
        self.assertEqual(value("Explosive Light", "damage_pct"), 830)
        self.assertEqual((value("Pillar of the Ancients", "damage_pct", "hit"), value("Pillar of the Ancients", "damage_pct", "dot"),
                          value("Pillar of the Ancients", "dot_duration_seconds")), (635, 785, 3))
        self.assertEqual(value("Empowered Wave", "damage_pct"), 1045)
        self.assertEqual(value("Shattering Light", "damage_pct"), 820)

    def test_the_power_file_agrees_with_the_sheet(self):
        # Power/Monk_WaveOfLight.pow: SF_29 8.35 x SF_34 1.2514970 = 10.45; SF_17 6.35; SF_31 7.85; SF_3 8.2; SF_23 8.3.
        self.assertAlmostEqual(8.35 * 1.2514970059880239520958083832335 * 100, value("Empowered Wave", "damage_pct"), delta=0.5)
        self.assertEqual(value("", "damage_pct"), 8.35 * 100)
        self.assertAlmostEqual(value("Pillar of the Ancients", "damage_pct", "hit"), 6.35 * 100, places=6)
        self.assertAlmostEqual(value("Pillar of the Ancients", "damage_pct", "dot"), 7.85 * 100, places=6)
        self.assertAlmostEqual(value("Shattering Light", "damage_pct"), 8.2 * 100, places=6)
        self.assertAlmostEqual(value("Explosive Light", "damage_pct"), 8.3 * 100, places=6)
        # the sheet's durations agree with SF_32 (stun 1) and SF_27 (pillar 3): no change to any sheet row
        self.assertEqual((value("Wall of Light", "stun_duration_seconds"), value("Pillar of the Ancients", "dot_duration_seconds")), (1, 3))

    def test_the_tunables_are_the_researched_ones(self):
        self.assertEqual([tune(n) for n in ("wave_of_light_bell_offset_yards", "wave_of_light_pillar_offset_yards",
                                             "wave_of_light_pillar_radius_yards", "wave_of_light_pillar_tick_seconds",
                                             "wave_of_light_line_start_yards", "wave_of_light_line_end_yards")],
                         [10, 10, 15, 0.5, 1, 50])
        self.assertEqual(tune("wave_of_light_bell_ticks"), 3)
        # The designer's values (bead 760kv, cards q-1014-01..04): the bell strikes within 10 yards, Shattering Light's line is 5 wide
        for name, alex in (("wave_of_light_bell_radius_yards", "10"), ("wave_of_light_line_width_yards", "5")):
            row = tunables()[name]
            self.assertEqual((row["d3_value"], row["value"]), ("", alex), name)
            self.assertIn("diablocraft-760kv", row["notes"], name)


if __name__ == "__main__":
    unittest.main()
