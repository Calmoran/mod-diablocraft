"""diablocraft-puvah (Monk 2.3.19): Mantra of Salvation and its five runes.

What this proves, and how:

  * **The logic that needs no core type.** tests/monk_mantra_of_salvation/harness.cpp compiles the real
    dc_monk_mantra_of_salvation.h and feeds it the sheets' numbers: Perseverance's number replaces the passive's, the
    resistance gained is a share of what the holder resists, the active adds to the passive, a pulse's number lapses at the
    end of its hold, Divine Protection opens strictly below its threshold and once per cooldown. Which Mantra is in force
    is test_monk_mantras.py's. Nine mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token Salvation's section of dc_monk_mantras.cpp reads by name is a row of
    monk_skill_values.csv for the skill or the rune that states it, and both tunables it reads are rows of monk.csv. The
    power file (X1_Monk_MantraOfEvasion_v2.pow, D3's name for the skill) agrees with the sheet on every number (SF_0 60,
    SF_2 0.2, SF_3 0.35, SF_4 0.2, SF_5 0.2, SF_6 0.1, SF_7 3, SF_8 90, SF_9 0.8, SF_10 0.25, SF_11 1.2, SF_15 1), so no sheet
    row changes.
  * **The wiring.** dc_monk.cpp hands a Mantra of Salvation cast to Salvation::Cast, every other Monk cast to
    Salvation::Touch, and the hit path's dodge to Salvation::Dodge.

What it does not prove: anything on a running server. The pulse, the resistance and the shield need the Monk's records and
are docs/test-diablocraft-puvah.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_mantra_of_salvation.py
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
SOURCES = ["src/classes/monk/dc_monk_mantra_of_salvation.h", "tests/monk_mantra_of_salvation/harness.cpp"]
SKILL = "Mantra of Salvation"
HEADER = "src/classes/monk/dc_monk_mantra_of_salvation.h"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "monk_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunable(name):
    rows = [r for r in read(MODULE / "data/tunables/monk.csv") if r["name"] == name]
    assert len(rows) == 1, name
    return float(rows[0]["value"] or rows[0]["d3_value"])


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
    binary = harness_env.build([MODULE / "tests/monk_mantra_of_salvation/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "resistance_pct", "passive"), value("Perseverance", "resistance_pct"),
               value("", "resistance_pct", "active"), value("Divine Protection", "life_threshold_pct"),
               value("Divine Protection", "internal_cooldown_seconds"), value("Divine Protection", "duration_seconds"),
               tunable("mantra_salvation_hold_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 21, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        shield = "return lifePct < thresholdPct && now >= readyAt;"
        mutations = [
            ("Perseverance adds to the passive", (HEADER, "return runePct ? *runePct : skillPct;",
                                                  "return runePct ? skillPct + *runePct : skillPct;")),
            ("negative resistance gains", (HEADER, "return baseline > 0 && pct > 0 ? baseline * pct / 100.0 : 0.0;",
                                           "return pct > 0 ? baseline * pct / 100.0 : 0.0;")),
            ("the active is lost", (HEADER, "return std::max(0.0, passivePct) + std::max(0.0, activePct);",
                                    "return std::max(0.0, passivePct);")),
            ("a hold never ends", (HEADER, "return now < until;", "return true;")),
            ("an ended number still reads", (HEADER, "return Live(now, until) ? pct : 0.0;", "return pct;")),
            ("the threshold is inclusive", (HEADER, shield, "return lifePct <= thresholdPct && now >= readyAt;")),
            ("the cooldown is lost", (HEADER, shield, "return lifePct < thresholdPct;")),
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
        self.assertEqual([value("", t) for t in ("cost_resource", "duration_seconds", "radius_yards")], [50, 3, 60])
        self.assertEqual((value("", "resistance_pct", "active"), value("", "resistance_pct", "passive")), (20, 20))
        self.assertEqual(value("Agility", "dodge_pct"), 35)
        self.assertEqual(value("Perseverance", "resistance_pct"), 40)
        self.assertEqual(value("Hard Target", "armor_pct"), 20)
        self.assertEqual(value("Wind through the Reeds", "movement_speed_pct"), 10)
        self.assertEqual([value("Divine Protection", t) for t in ("life_threshold_pct", "damage_reduction_pct",
                                                                 "duration_seconds", "internal_cooldown_seconds")],
                         [25, 80, 3, 90])

    def test_the_power_file_and_the_sheet_agree(self):
        # Power/X1_Monk_MantraOfEvasion_v2.pow (decoded, read-only): SF_0 radius 60, SF_2 resistance total 0.2, SF_3 dodge
        # 0.35, SF_4 resist all 0.2, SF_5 armor 0.20, SF_6 run speed 0.1, SF_7 bubble 3, SF_8 bubble frequency 90, SF_9
        # bubble reduction 0.8, SF_10 bubble life 0.25, SF_11 friendly buff 1.2, SF_13 the start aura 3.0 (+ Chant of
        # Resonance), SF_15 tick rate 1; ResourceCost 50, ProcCoefficient 0, no cooldown.
        self.assertEqual(value("", "radius_yards"), 60)
        self.assertEqual(value("", "resistance_pct", "active") / 100, 0.2)
        self.assertEqual(value("Agility", "dodge_pct") / 100, 0.35)
        self.assertEqual(value("", "resistance_pct", "passive") / 100, 0.2)
        self.assertEqual(value("Hard Target", "armor_pct") / 100, 0.2)
        self.assertEqual(value("Wind through the Reeds", "movement_speed_pct") / 100, 0.1)
        self.assertEqual(value("Divine Protection", "duration_seconds"), 3)
        self.assertEqual(value("Divine Protection", "internal_cooldown_seconds"), 90)
        self.assertEqual(value("Divine Protection", "damage_reduction_pct") / 100, 0.8)
        self.assertEqual(value("Divine Protection", "life_threshold_pct") / 100, 0.25)
        self.assertEqual(value("", "duration_seconds"), 3)
        self.assertEqual(value("", "cost_resource"), 50)
        self.assertEqual(tunable("mantra_salvation_hold_seconds"), 1.2)
        self.assertEqual(tunable("mantra_salvation_pulse_seconds"), 1)

    def test_every_name_the_code_reads_exists(self):
        tokens = {token for token, _ in monk_source.reads("Salvation")}
        sheet = read(D3 / "monk_skill_values.csv")
        sheet_tokens = {r["token"] for r in sheet if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertGreaterEqual(len(tokens), 9)
        tunables = {r["name"] for r in read(MODULE / "data/tunables/monk.csv")}
        self.assertEqual(monk_source.tunables("Salvation") - tunables, set())


if __name__ == "__main__":
    unittest.main()
