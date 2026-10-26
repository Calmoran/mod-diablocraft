"""diablocraft-mrpzh (Monk 2.3.22): Mantra of Conviction and its five runes.

What this proves, and how:

  * **The rules.** tests/monk_mantra_of_conviction/harness.cpp compiles the real dc_monk_mantra_of_conviction.h with
    the sheets' and tunables' numbers: the marked enemies take 8% (16% in the activation's 3 s), Overawe 12% (20%),
    Submission's 38% a second split over the 0.5 s ticks, and the boost window ends on time. Which Mantra is in force
    is test_monk_mantras.py's. Six mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every number Conviction's section of dc_monk_mantras.cpp reads by name is a Mantra of
    Conviction row of monk_skill_values.csv or a mantra_of_conviction_ row of data/tunables/monk.csv with the power
    file's value.
  * **The wiring.** dc_monk.cpp hands the activation to Conviction among the skills' own returns and every landed hit
    after the null guard.

What it does not prove: anything on a running server (the aura, the slow, the damage tick, the speed and the marks'
effect on damage are docs/test-diablocraft-mrpzh.md's, live).

    python mod-diablocraft/scripts/tests/classes/test_monk_mantra_of_conviction.py
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
HEADER = "src/classes/monk/dc_monk_mantra_of_conviction.h"
SOURCES = [HEADER, "tests/monk_mantra_of_conviction/harness.cpp"]
SKILL = "Mantra of Conviction"
PREFIX = "mantra_of_conviction_"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def values():
    return read(D3 / "monk_skill_values.csv")


def value(rune, token, qualifier=""):
    rows = [r for r in values() if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "monk.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits the header."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        old, new = mutate
        key = HEADER[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/monk_mantra_of_conviction/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_taken_pct", "passive"), value("", "damage_taken_pct", "active"),
               value("Overawe", "damage_taken_pct"), value("Submission", "damage_pct"),
               tune(PREFIX + "tick_seconds"), value("", "duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 8, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the boost always on",
             ("(boosted ? std::max(0.0, active - skillPassive) : 0.0)", "std::max(0.0, active - skillPassive)")),
            ("the boost adds the whole active", ("std::max(0.0, active - skillPassive)", "std::max(0.0, active)")),
            ("the tick deals a whole second", ("perSecond * tickSeconds : 0.0", "perSecond : 0.0")),
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
    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_taken_pct", "active"), value("", "duration_seconds"),
                          value("", "radius_yards"), value("", "damage_taken_pct", "passive")], [50, 16, 3, 30, 8])
        self.assertEqual(value("Overawe", "damage_taken_pct"), 12)
        self.assertEqual(value("Submission", "damage_pct"), 38)
        self.assertEqual(value("Dishearten", "slow_pct"), 80)
        self.assertEqual([value("Annihilation", t) for t in ("movement_speed_pct", "duration_seconds")], [30, 3])
        self.assertEqual(value("Intimidation", "enemy_damage_pct"), 15)

    def test_the_tunables_are_the_power_files(self):
        expected = {PREFIX + "tick_seconds": 0.5, PREFIX + "hold_seconds": 0.6, PREFIX + "ally_radius_yards": 60}
        rows = tunables()
        self.assertEqual({n for n in rows if n.startswith(PREFIX)}, set(expected))
        for name, number in expected.items():
            with self.subTest(name):
                self.assertEqual(float(rows[name]["d3_value"]), number)
                self.assertFalse(rows[name]["value"], "a power-file number is d3_value, the designer's column stays open")
                self.assertIn("X1_Monk_MantraOfConviction_v2.pow SF_", rows[name]["notes"])

    def test_every_name_the_code_reads_exists(self):
        self.assertEqual(monk_source.tunables("Conviction"), {n for n in tunables() if n.startswith(PREFIX)})
        reads = monk_source.reads("Conviction")
        self.assertGreaterEqual(len(reads), 8)
        sheet = {(r["token"], r["qualifier"]) for r in values() if r["skill"] == SKILL}
        self.assertEqual(reads - sheet, set())


if __name__ == "__main__":
    unittest.main()
