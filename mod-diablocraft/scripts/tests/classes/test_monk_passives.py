"""diablocraft-x7gp9 (Monk 2.4.1: Resolve, Fleet Footed, Exalted Soul, Transcendence, Chant of Resonance, Seize the
Initiative).

What this proves, and how:

  * **The maths.** tests/monk_passives/harness.cpp compiles the real dc_monk_passives.h: Transcendence's meter counts a
    fall of the Spirit pool as Spirit spent and a clamp to a lowered maximum as none, the Spirit a second is paid in whole
    seconds with the rest kept, Seize's threshold is strictly above, the stat rows are reconciled (a first look clears
    every row a save left), and Chant's payback is the share of what was paid. Planted mutations must each fail it.
  * **The data.** Every token the glue reads is a row of its passive in monk_passive_values.csv with the sheet's value;
    the Hellfire Amulet's pool (dc_class_passive, world_0050) holds every Monk passive (all 18, here once for the three files).
  * **The wiring.** dc_monk.cpp calls the passives from Cast and Landed and registers their tick inside its one RegisterScripts;
    dc_combat.cpp registers the Monk's scripts once, beside the Wizard's (nightly's line, not this bead's).

What it does not prove: anything on a running server; the test sheet's checks do.

    python mod-diablocraft/scripts/tests/classes/test_monk_passives.py
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
HEADER = "src/classes/monk/dc_monk_passives.h"
SOURCES = [HEADER, "tests/monk_passives/harness.cpp"]
GLUE = MODULE / "src/classes/monk/dc_monk_passives.cpp"
SIX = ("Resolve", "Fleet Footed", "Exalted Soul", "Transcendence", "Chant of Resonance", "Seize the Initiative")


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
    binary = harness_env.build([MODULE / "tests/monk_passives/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)], capture_output=True, text=True)


def sheet(name):
    with (MODULE / "data" / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class Harness(unittest.TestCase):
    def test_the_meter_the_seconds_the_threshold_the_rows_and_the_payback(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a clamp counts as a spend", (HEADER, "std::min(last, maximum) - current", "last - current")),
            ("a gain counts as a negative spend", (HEADER, "std::max(0.0, std::min(last, maximum) - current)",
                                                   "(std::min(last, maximum) - current)")),
            ("Spirit drops the leftover", (HEADER, "clockMs %= 1000;", "clockMs = 0;")),
            ("the threshold is inclusive", (HEADER, "return lifePct > thresholdPct;", "return lifePct >= thresholdPct;")),
            ("a row no longer wanted stays", (HEADER, "return {wanted & ~applied, applied & ~wanted};",
                                              "return {wanted & ~applied, 0u};")),
            ("the payback is not capped", (HEADER, "std::clamp(reductionPct, 0.0, 100.0)", "reductionPct")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Data(unittest.TestCase):
    def test_every_number_the_glue_reads_is_its_passives_row(self):
        glue = GLUE.read_text(encoding="utf-8")
        values = {(r["skill"], r["token"]): float(r["value"]) for r in sheet("d3/monk_passive_values.csv")}
        expected = {
            ("Resolve", "enemy_damage_pct"): 20, ("Resolve", "duration_seconds"): 4,
            ("Fleet Footed", "movement_speed_pct"): 10,
            ("Exalted Soul", "max_pool_resource"): 50, ("Exalted Soul", "regen_per_second_resource"): 4,
            ("Transcendence", "heal_per_hit_life"): 429,
            ("Chant of Resonance", "cost_reduction_pct"): 50, ("Chant of Resonance", "regen_per_second_resource"): 4,
            ("Seize the Initiative", "life_threshold_pct"): 75, ("Seize the Initiative", "attack_speed_pct"): 30,
            ("Seize the Initiative", "duration_seconds"): 4,
        }
        for (passive, token), value in expected.items():
            with self.subTest(passive=passive, token=token):
                self.assertEqual(values[(passive, token)], value)
                self.assertIn(f'"{token}"', glue)
        for passive in SIX:
            self.assertIn(f'"{passive}"', glue)

    def test_the_hellfire_pool_holds_every_monk_passive(self):
        sql = (MODULE / "data/sql/db-world/updates/world_0050_class_catalogue.sql").read_text(encoding="utf-8")
        pool = sql[sql.index("INSERT INTO `dc_class_passive`"):]
        pool = pool[:pool.index(";")]
        monk = next(r for r in sheet("d3/class_map.csv") if r["d3_class"] == "Monk")["class_id"]
        ids = {r["name"]: r["spell_id"] for r in sheet("generated/spell_shells.csv") if r["kind"] == "passive"}
        passives = sheet("d3/monk_passives.csv")
        self.assertEqual(18, len(passives))
        for passive in passives:
            with self.subTest(passive["passive_name"]):
                self.assertIn(f"({monk}, {ids[passive['passive_name']]}, {passive['unlock_level']})", pool)


if __name__ == "__main__":
    unittest.main()
