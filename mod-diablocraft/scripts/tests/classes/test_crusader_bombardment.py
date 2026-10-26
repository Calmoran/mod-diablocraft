"""Bombardment and its five runes (src/classes/crusader/dc_crusader_bombardment.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_bombardment/harness.cpp compiles the real
    dc_crusader_bombardment.h with the sheets' own rune names and numbers: each rune name is its rune; the spheres share the
    skill's 2850% and the big ball deals its own 3320% in its own 18 yards; the next sphere waits the least with what
    Barrels of Spikes and Mine Field add and a part of the extra; a barrel adds the share of Thorns; Annihilate alone adds
    the critical chance; a roll picks a place inside the enemies; a mine lies between the nearest and the farthest and goes
    off on an enemy within its radius. Eighteen mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_bombardment.cpp reads by name is a row of
    crusader_skill_values.csv for Bombardment, the generated value map says whose record holds it, and the numbers are the
    researched ones: a 60 second cooldown, 5 spheres, 2850% in 12 yards, Barrels of Spikes 200% of Thorns, Annihilate 100%
    critical chance, Mine Field 2 mines at 160% in 10 yards, Impactful Bombardment 3320% in 18 yards. Every tunable it reads
    is a row of data/tunables/crusader.csv with the power file's number (Power/X1_Crusader_Bombardment.pow) as its D3 value,
    the mines' look the standing default of 0.25 seconds (card q-1021-32).
  * **The cast deals no hit of its own.** BasePct answers 0 for the skill and every rune.

What it does not prove: anything on a running server, how the client draws the spheres, or that the sheet's "enemies around
you" is the enemies near the aimed point (the power file's search radius is not tied to either by any source).

    python mod-diablocraft/scripts/tests/classes/test_crusader_bombardment.py
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
HEADER = "src/classes/crusader/dc_crusader_bombardment.h"
SOURCES = [HEADER, "tests/crusader_bombardment/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_bombardment.cpp"
SKILL = "Bombardment"
POW = "Power/X1_Crusader_Bombardment.pow"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "crusader_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "crusader_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/crusader.csv") if r["name"].startswith("bombardment_")}


def d3(name):
    return float(tunables()[name]["d3_value"])


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/crusader_bombardment/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [int(value("", "spawn_count")), value("", "damage_pct"), value("", "radius_yards"),
               value("Impactful Bombardment", "damage_pct"), value("Impactful Bombardment", "radius_yards"),
               d3("bombardment_spawn_wait_seconds"), d3("bombardment_barrels_wait_added_seconds"),
               d3("bombardment_mine_field_wait_added_seconds"), d3("bombardment_spawn_wait_extra_seconds"),
               value("Barrels of Spikes", "thorns_share_pct"), value("Annihilate", "crit_chance_pct"),
               d3("bombardment_mine_min_yards"), d3("bombardment_mine_max_yards"),
               value("Mine Field", "radius_yards")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Targeted;", "return Rune::MineField;")),
            ("the big ball is five", (HEADER, "rune == Rune::ImpactfulBombardment ? 1u : skillCount", "skillCount")),
            ("the spheres each deal the total", (HEADER, "total / impacts : 0.0", "total : 0.0")),
            ("the big ball deals the skill's total", (HEADER, "rune == Rune::ImpactfulBombardment ? runeTotalPct : skillTotalPct", "skillTotalPct")),
            ("no impacts still deals", (HEADER, "return impacts && total > 0 ?", "return total > 0 ?")),
            ("every rune strikes the big area", (HEADER, "rune == Rune::ImpactfulBombardment ? runeRadius : skillRadius", "runeRadius")),
            ("Barrels of Spikes adds nothing to the wait", (HEADER, "(rune == Rune::BarrelsOfSpikes ? barrelsAdded : 0.0)", "0.0")),
            ("Mine Field adds the wrong one", (HEADER, "(rune == Rune::MineField ? minesAdded : 0.0)", "(rune == Rune::MineField ? barrelsAdded : 0.0)")),
            ("the roll is ignored", (HEADER, "std::max(0.0, extra) * std::clamp(roll, 0.0, 1.0)", "std::max(0.0, extra)")),
            ("the roll can run past the extra", (HEADER, "std::max(0.0, extra) * std::clamp(roll, 0.0, 1.0)", "std::max(0.0, extra) * roll")),
            ("every rune's barrels bite", (HEADER, "rune == Rune::BarrelsOfSpikes && thorns > 0", "thorns > 0")),
            ("the barrel adds the whole Thorns", (HEADER, "thorns * sharePct / 100.0 : 0.0", "thorns : 0.0")),
            ("every rune crits", (HEADER, "rune == Rune::Annihilate && pct > 0", "pct > 0")),
            ("the pick can run past the end", (HEADER, "std::min(count - 1, static_cast<std::size_t>(std::max(0.0, roll) * count))", "static_cast<std::size_t>(std::max(0.0, roll) * count)")),
            ("nobody is picked from nobody", (HEADER, "if (!count)\n            return std::nullopt;", "if (!count)\n            return 0;")),
            ("a mine lies at the nearest", (HEADER, "nearest + std::max(0.0, farthest - nearest) * std::clamp(roll, 0.0, 1.0)", "nearest")),
            ("a mine goes off at a distance", (HEADER, "nearestEnemy <= radius;", "nearestEnemy <= radius + 5;")),
            ("a mine with no radius goes off", (HEADER, "return radius > 0 && nearestEnemy <= radius", "return nearestEnemy <= radius")),
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
    def test_the_five_runes(self):
        self.assertEqual(runes(), ["Barrels of Spikes", "Annihilate", "Mine Field", "Impactful Bombardment", "Targeted"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "spawn_count"), value("", "damage_pct"),
                          value("", "radius_yards")], [60, 5, 2850, 12])
        self.assertEqual(value("Barrels of Spikes", "thorns_share_pct"), 200)
        self.assertEqual(value("Annihilate", "crit_chance_pct"), 100)
        self.assertEqual((value("Mine Field", "spawn_count"), value("Mine Field", "damage_pct"),
                          value("Mine Field", "radius_yards")), (2, 160, 10))
        self.assertEqual((value("Impactful Bombardment", "damage_pct"), value("Impactful Bombardment", "radius_yards")),
                         (3320, 18))

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"spawn_count", "damage_pct", "radius_yards", "thorns_share_pct", "crit_chance_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "spawn_count"), ("", "damage_pct"), ("Barrels of Spikes", "thorns_share_pct"),
                            ("Annihilate", "crit_chance_pct"), ("Mine Field", "spawn_count"), ("Mine Field", "damage_pct"),
                            ("Mine Field", "radius_yards"), ("Impactful Bombardment", "damage_pct"),
                            ("Impactful Bombardment", "radius_yards")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "bombardment_search_radius_yards": "35",           # SF_13
        "bombardment_first_delay_seconds": "0.35",         # SF_4
        "bombardment_impact_delay_seconds": "0.55",        # SF_14
        "bombardment_spawn_wait_seconds": "0.55",          # SF_7
        "bombardment_spawn_wait_extra_seconds": "1.5",     # SF_39
        "bombardment_barrels_wait_added_seconds": "0.1",   # SF_18
        "bombardment_mine_field_wait_added_seconds": "0.5",  # SF_30
        "bombardment_mine_seconds": "5",                   # SF_24
        "bombardment_mine_min_yards": "5",                 # SF_29
        "bombardment_mine_max_yards": "30",                # SF_28
    }

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        self.assertEqual(set(rows), set(self.NUMBERS) | {"bombardment_mine_check_seconds"})
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertIn(POW, rows[name]["notes"])
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
        check = rows["bombardment_mine_check_seconds"]
        self.assertEqual((check["d3_value"], check["value"]), ("", "0.25"))
        self.assertNotIn("PLACEHOLDER", check["notes"])
        self.assertIn("q-1021-32", check["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(tunables()))


if __name__ == "__main__":
    unittest.main()
