"""Blessed Hammer and its five runes (src/classes/crusader/dc_crusader_blessed_hammer.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_blessed_hammer/harness.cpp compiles the real
    dc_crusader_blessed_hammer.h with the sheets' own rune names and numbers and the designer's and the power file's tunables: each rune
    name is its rune; only Limitless reaches further (the 15 yards and 20 more) and lasts longer; the hammer's path is a spiral
    from the Crusader out to the reach evenly over its 3 seconds, turning 1.5 loops; it touches an enemy within its hit radius
    and hits it once as it reaches it; Thunderstruck's arc catches the enemies near the segment from the Crusader to the hammer;
    the hammer takes a look every tenth of a second over its life; a fire pool may be laid while fewer than 4 burn and fires every
    one of its ticks, the last included. Ten mutations planted in a scratch copy (two runes share a name, every rune reaches
    further or lasts longer, the spiral does not grow, does not turn, an enemy is hit at every look and not as it is reached,
    the arc is measured to the line and not the segment, the pools have no cap, the last tick of a pool is dropped, the ticks
    round up) must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_blessed_hammer.cpp reads by name is a row of
    crusader_skill_values.csv for Blessed Hammer (or the rune that states it), the generated value map says whose record holds
    it, and the numbers are the researched ones: 320% weapon damage for 10 Wrath, Burning Wrath 25% for 330% a second, Thunderstruck
    60%, Limitless 640% and 20 yards more, Brute Force 35% to explode for 460% within 6 yards and stun 1 second. Every tunable
    it reads is a row of data/tunables/crusader.csv: the designer's answers (the hammer lasts 3 seconds, spirals out to 15 yards in 1.5
    loops, Brute Force slows 60% for 2 seconds, the hammer hits within 5 yards), the power file's numbers.
  * **What the hit is.** The engine's own hit of the cast is none (the hammer hits where it spirals), and the hammer's hit is the
    base record's 320% for every rune but Limitless's 640%.
  * **The pool's schedule.** No clock test may stop a pool before its last tick (a test of the clock against the pool's end dropped
    the last of its two ticks).

What it does not prove: anything on a running server. The spiral, the hits, the pools, the arcs, the orbit and the explosion are
docs/test-diablocraft-7t4gv.7.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_crusader_blessed_hammer.py
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
HEADER = "src/classes/crusader/dc_crusader_blessed_hammer.h"
SOURCES = [HEADER, "tests/crusader_blessed_hammer/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_blessed_hammer.cpp"
SKILL = "Blessed Hammer"


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
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "crusader.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


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
    binary = harness_env.build([MODULE / "tests/crusader_blessed_hammer/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("blessed_hammer_reach_yards"), value("Limitless", "radius_yards"), tune("blessed_hammer_pools_at_once"),
               tune("blessed_hammer_pool_seconds"), tune("blessed_hammer_pool_tick_seconds"), tune("blessed_hammer_seconds"),
               tune("blessed_hammer_loops"), tune("blessed_hammer_step_seconds"),
               tune("blessed_hammer_limitless_life_factor")] + runes() + [tune("blessed_hammer_hit_radius_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 30, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::Dominion;", "return Rune::BruteForce;")),
            ("every rune reaches further", (HEADER, "return rune == Rune::Limitless ? base + increase : base;", "return base + increase;")),
            ("every rune lasts longer", (HEADER, "return rune == Rune::Limitless ? base * factor : base;", "return base * factor;")),
            ("the spiral does not grow", (HEADER, "distance = reach * share;", "distance = reach;")),
            ("the spiral does not turn", (HEADER, "double const angle = heading + 2 * 3.14159265358979323846 * loops * share,", "double const angle = heading,")),
            ("an enemy is hit at every look", (HEADER, "return touchingNow && !touchedBefore;", "return touchingNow;")),
            ("the arc is measured to the line", (HEADER, "std::clamp(((px - ax) * dx + (py - ay) * dy) / length, 0.0, 1.0)", "((px - ax) * dx + (py - ay) * dy) / length")),
            ("the pools have no cap", (HEADER, "return burning < most;", "return true;")),
            ("the last tick of a pool is dropped", (HEADER, "return left > 0;\n    }\n\n    inline unsigned PoolLeftAfter", "return left > 1;\n    }\n\n    inline unsigned PoolLeftAfter")),
            ("the ticks round up", (HEADER, "static_cast<unsigned>(seconds / tickSeconds + 1e-9)", "static_cast<unsigned>(std::ceil(seconds / tickSeconds))")),
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
        self.assertEqual(runes(), ["Burning Wrath", "Thunderstruck", "Limitless", "Brute Force", "Dominion"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct")], [10, 320])
        self.assertEqual((value("Burning Wrath", "proc_chance_pct"), value("Burning Wrath", "damage_pct")), (25, 330))
        self.assertEqual(value("Thunderstruck", "damage_pct"), 60)
        self.assertEqual((value("Limitless", "damage_pct"), value("Limitless", "radius_yards")), (640, 20))
        self.assertEqual([value("Brute Force", t) for t in ("proc_chance_pct", "damage_pct", "radius_yards", "stun_duration_seconds")],
                         [35, 460, 6, 1])

    def test_the_tunables(self):
        rows = tunables()
        for name, number, source in (("blessed_hammer_pool_radius_yards", "8", "SF_7"), ("blessed_hammer_pool_seconds", "2", "SF_13"),
                                     ("blessed_hammer_pools_at_once", "4", "SF_14"), ("blessed_hammer_step_seconds", "0.1", "SF_16"),
                                     ("blessed_hammer_arc_chance_pct", "30", "SF_33"), ("blessed_hammer_limitless_life_factor", "1.5", "SF_38")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""), name)
            self.assertIn(source, rows[name]["notes"])
        self.assertEqual((rows["blessed_hammer_pool_tick_seconds"]["d3_value"], rows["blessed_hammer_pool_tick_seconds"]["value"]), ("1", ""))
        # The designer's answers: his column is filled, no mark of a placeholder is left on these rows.
        for name, number, card in (("blessed_hammer_seconds", "3", "q-1021-10"), ("blessed_hammer_reach_yards", "15", "q-1021-10"),
                                   ("blessed_hammer_loops", "1.5", "q-1021-10"), ("blessed_hammer_slow_pct", "60", "q-1021-11"),
                                   ("blessed_hammer_slow_seconds", "2", "q-1021-11")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), ("", number), name)
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)
            self.assertIn(card, rows[name]["notes"], name)
        # The hammer's size (card q-1021-13): 5 yards, in the designer's column, no placeholder mark.
        size = rows["blessed_hammer_hit_radius_yards"]
        self.assertEqual((size["d3_value"], size["value"]), ("", "5"))
        self.assertNotIn("PLACEHOLDER", size["notes"])
        self.assertIn("q-1021-13", size["notes"])

    def test_the_hammer_hits_within_5_yards(self):
        self.assertEqual(tune("blessed_hammer_hit_radius_yards"), 5)
        code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('hammer->hitRadius = Tune("blessed_hammer_hit_radius_yards");', code)
        self.assertIn("if (hammer->hitRadius <= 0 || !hammer->steps) return;", code)

    def test_the_hammer_lasts_three_seconds_spirals_out_to_15_yards_in_1_5_loops_and_brute_force_slows_60_for_2(self):
        self.assertEqual((tune("blessed_hammer_seconds"), tune("blessed_hammer_reach_yards"), tune("blessed_hammer_loops")), (3, 15, 1.5))
        self.assertEqual((tune("blessed_hammer_slow_pct"), tune("blessed_hammer_slow_seconds")), (60, 2))
        code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('Slow(player, enemy, Tune("blessed_hammer_slow_pct"), Tune("blessed_hammer_slow_seconds"));', code)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("blessed_hammer_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\(\w+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "proc_chance_pct", "radius_yards", "stun_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_pct"), ("Burning Wrath", "proc_chance_pct"), ("Burning Wrath", "damage_pct"),
                            ("Thunderstruck", "damage_pct"), ("Limitless", "damage_pct"), ("Limitless", "radius_yards"),
                            ("Brute Force", "proc_chance_pct"), ("Brute Force", "damage_pct"), ("Brute Force", "radius_yards"),
                            ("Brute Force", "stun_duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token, "")]["origin"], "own")

    def test_the_engines_hit_is_none_and_the_hammers_is_the_skills_except_limitless(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn("std::optional<double> BasePct(std::uint32_t spellId) { if (!Is(spellId)) return std::nullopt; return 0.0; }", text)
        self.assertIn('hammer->pct = hammer->rune == Rune::Limitless ? Numbers::Num(spellId, "damage_pct") : Numbers::Num(BaseId(Skill), "damage_pct");',
                      text)

    def test_no_clock_stops_a_pool_before_its_last_tick(self):
        def guard(text):
            tick = text[text.index("void PoolTick("):text.index("void LayPool(")]
            first = tick[:tick.index("return;")]
            assert "until" not in first and "Now()" not in first, "a clock test stops the pool"
            assert "PoolFires(left)" in first
            assert "unsigned left, std::uint32_t intervalMs" in tick
        text = CODE.read_text(encoding="utf-8")
        guard(text)
        broken = text.replace("!PoolFires(left))", "!PoolFires(left) || Now() >= 0)", 1)
        self.assertNotEqual(broken, text)
        with self.assertRaises(AssertionError):
            guard(broken)
        self.assertIn("PoolLeftAfter(left)", text)


if __name__ == "__main__":
    unittest.main()
