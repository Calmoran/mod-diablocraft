"""Heaven's Fury and its five runes (src/classes/crusader/dc_crusader_heavens_fury.h and .cpp, dc_crusader_hold.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_heavens_fury/harness.cpp compiles the real
    dc_crusader_heavens_fury.h with the sheets' own rune names and numbers: each rune name is its rune; the skill, Blessed
    Ground and Thou Shalt Not Pass keep the skill's ray and the other three put their own in its place; a total is paid in
    ticks that add up to it; Split Fury's ring is the area less a beam and the beams are a third of the circle apart; the
    beam of Fires of Heaven is a strip out from the Crusader. Fourteen mutations planted in a scratch copy must each make it
    fail.
  * **The code reads what the sheets state.** Every token dc_crusader_heavens_fury.cpp reads by name is a row of
    crusader_skill_values.csv for Heaven's Fury, the generated value map says whose record holds it, and the numbers are the
    researched ones: a 20 second cooldown and 1710% over 6 seconds, Ascendancy 12 yards and 2766%, Blessed Ground 1550% over
    5 seconds, Split Fury 3 beams at 1980%, Thou Shalt Not Pass 6 seconds, Fires of Heaven 960% for 40 Wrath. Every tunable
    it reads is a row of data/tunables/crusader.csv with the power file's number (Power/X1_Crusader_HeavensFury3.pow) as its
    D3 value, the tick a reading, the barrier's look the standing default of 0.25 seconds (card q-1021-30).
  * **The records.** Fires of Heaven's generated record has no cooldown and costs 40 Wrath; the others have the 20 seconds.
  * **The cast deals no hit of its own.** BasePct answers 0 for the skill and every rune.

What it does not prove: anything on a running server, how the client draws the ray, or that the ray stands still where D3's
may move (the power file gives it no speed).

    python mod-diablocraft/scripts/tests/classes/test_crusader_heavens_fury.py
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
HEADER = "src/classes/crusader/dc_crusader_heavens_fury.h"
SOURCES = [HEADER, "src/classes/crusader/dc_crusader_dot.h", "tests/crusader_heavens_fury/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_heavens_fury.cpp"
SKILL = "Heaven's Fury"
POW = "Power/X1_Crusader_HeavensFury3.pow"


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
    return {r["name"]: r for r in read(MODULE / "data/tunables/crusader.csv") if r["name"].startswith("heavens_fury_")}


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
    binary = harness_env.build([MODULE / "tests/crusader_heavens_fury/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    rows = tunables()
    numbers = [value("", "damage_pct"), value("", "dot_duration_seconds"), float(rows["heavens_fury_tick_seconds"]["d3_value"]),
               8, float(rows["heavens_fury_split_beam_radius_yards"]["d3_value"]),
               float(rows["heavens_fury_fires_distance_yards"]["d3_value"]),
               float(rows["heavens_fury_fires_radius_yards"]["d3_value"])] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 17, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::FiresOfHeaven;", "return Rune::SplitFury;")),
            ("Ascendancy keeps the skill's ray", (HEADER, "rune == Rune::None || rune == Rune::BlessedGround ||", "rune == Rune::None || rune == Rune::Ascendancy || rune == Rune::BlessedGround ||")),
            ("Blessed Ground loses the ray", (HEADER, "rune == Rune::None || rune == Rune::BlessedGround ||", "rune == Rune::None ||")),
            ("a tick pays the whole total", (HEADER, "Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds))", "Dot::TickPct(totalPct, 1)")),
            ("a negative total pays", (HEADER, "return totalPct > 0 ? Dot::TickPct", "return totalPct != 0 ? Dot::TickPct")),
            ("the ring is the area", (HEADER, "std::max(0.0, areaRadius - beamRadius)", "std::max(0.0, areaRadius)")),
            ("the ring can be negative", (HEADER, "std::max(0.0, areaRadius - beamRadius)", "areaRadius - beamRadius")),
            ("the beams are all at the start", (HEADER, "start + 2.0 * M_PI * index / count", "start")),
            ("the beams are a half circle", (HEADER, "start + 2.0 * M_PI * index / count", "start + M_PI * index / count")),
            ("along and across are swapped", (HEADER, "return dx * std::cos(heading) + dy * std::sin(heading);", "return -dx * std::sin(heading) + dy * std::cos(heading);")),
            ("across turns the wrong way", (HEADER, "return -dx * std::sin(heading) + dy * std::cos(heading);", "return dx * std::sin(heading) + dy * std::cos(heading);")),
            ("the beam reaches behind", (HEADER, "return along >= 0 && along <= distance", "return along <= distance")),
            ("the beam is too long", (HEADER, "along <= distance &&", "along <= distance + 1 &&")),
            ("the strip has no sides", (HEADER, "std::fabs(across) <= radius", "true")),
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
        self.assertEqual(runes(), ["Ascendancy", "Blessed Ground", "Split Fury", "Thou Shalt Not Pass", "Fires of Heaven"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "damage_pct"), value("", "dot_duration_seconds")], [20, 1710, 6])
        self.assertEqual((value("Ascendancy", "radius_yards"), value("Ascendancy", "damage_pct"),
                          value("Ascendancy", "dot_duration_seconds")), (12, 2766, 6))
        self.assertEqual((value("Blessed Ground", "damage_pct"), value("Blessed Ground", "dot_duration_seconds")), (1550, 5))
        self.assertEqual((value("Split Fury", "spawn_count"), value("Split Fury", "damage_pct"),
                          value("Split Fury", "dot_duration_seconds")), (3, 1980, 6))
        self.assertEqual(value("Thou Shalt Not Pass", "duration_seconds"), 6)
        self.assertEqual((value("Fires of Heaven", "damage_pct"), value("Fires of Heaven", "cost_resource")), (960, 40))

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"radius_yards", "damage_pct", "dot_duration_seconds", "spawn_count", "duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_pct"), ("", "dot_duration_seconds"), ("Ascendancy", "radius_yards"),
                            ("Ascendancy", "damage_pct"), ("Ascendancy", "dot_duration_seconds"),
                            ("Blessed Ground", "damage_pct"), ("Blessed Ground", "dot_duration_seconds"),
                            ("Split Fury", "spawn_count"), ("Split Fury", "damage_pct"), ("Split Fury", "dot_duration_seconds"),
                            ("Thou Shalt Not Pass", "duration_seconds"), ("Fires of Heaven", "damage_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "heavens_fury_tick_seconds": "1",                 # a rate a second paid in seconds, a reading
        "heavens_fury_split_beam_radius_yards": "4",      # SF_21
        "heavens_fury_fires_distance_yards": "55",        # SF_14
        "heavens_fury_fires_radius_yards": "3",           # SF_15
    }

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        self.assertEqual(set(rows), set(self.NUMBERS) | {"heavens_fury_barrier_check_seconds"})
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertIn(POW, rows[name]["notes"])
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
        barrier = rows["heavens_fury_barrier_check_seconds"]
        self.assertEqual((barrier["d3_value"], barrier["value"]), ("", "0.25"))
        self.assertNotIn("PLACEHOLDER", barrier["notes"])
        self.assertIn("q-1021-30", barrier["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(tunables()))


class Records(unittest.TestCase):
    def sql(self):
        return (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")

    def record(self, spell_id):
        text = self.sql()
        columns = re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", text, re.S).group(1)
        names = [c.strip("` ") for c in columns.split(",")]
        line = re.search(r"\n\(%d,.*" % spell_id, text).group(0).strip().rstrip(",;")[1:-1]
        values = next(csv.reader([line], quotechar="'"))
        return dict(zip(names, values))

    def ids(self):
        return {r["rune"]: int(r["spell_id"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                if r["skill"] == SKILL and r["token"] == "damage_pct"}

    def test_fires_of_heaven_has_no_cooldown_and_costs_forty_wrath_and_the_others_have_twenty_seconds(self):
        ids = self.ids()
        fires = self.record(ids["Fires of Heaven"])
        self.assertEqual((fires["RecoveryTime"], fires["CategoryRecoveryTime"], fires["ManaCost"]), ("0", "0", "40"))
        for rune in ("", "Ascendancy", "Blessed Ground", "Split Fury", "Thou Shalt Not Pass"):
            with self.subTest(rune):
                other = self.record(ids[rune])
                self.assertEqual((other["RecoveryTime"], other["ManaCost"]), ("20000", "0"))


if __name__ == "__main__":
    unittest.main()
