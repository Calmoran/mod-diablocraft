"""Demon Hunter Caltrops and its five runes (src/classes/demon_hunter/dc_demon_hunter_caltrops.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_caltrops/harness.cpp compiles the real dc_demon_hunter_caltrops.h, the
    DoT rules and the clock with the sheets' own rune names and numbers: each rune name is its rune; no more than Max Traps stand
    however many are laid; the ticks of a sprung trap make Jagged Spikes' damage; a trap waits out its limit; held for its seconds in
    server updates that are no divisor of the tick it ticks at its cadence. Seven mutations planted in a scratch copy must each make it
    fail.
  * **The record needs no change.** The skill is a ground-aimed spell (a `ground_area` row of skill_targeting.csv, radius 12) that
    the engine already casts at a point, so the one new migration is the tunables'.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Caltrops (or the
    rune that states it); every tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_Caltrops.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams; the trap hits nothing when it is laid; it springs when an enemy stands in its area,
    slows every tick, and ends with its seconds; Torturous Ground roots on springing; the owner's death, the map and the logout end
    every trap.

What it does not prove: anything on a running server. The laying, the springing, the slow and the runes are
docs/test-diablocraft-vawmy.18.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_caltrops.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/demon_hunter/dc_demon_hunter_caltrops.h"
DOT = "src/classes/demon_hunter/dc_demon_hunter_dot.h"
CLOCK = "src/classes/demon_hunter/dc_demon_hunter_clock.h"
SOURCES = [HEADER, DOT, CLOCK, "tests/demon_hunter_caltrops/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_caltrops.cpp"
SKILL = "Caltrops"
RUNES = ["Jagged Spikes", "Hooked Spines", "Torturous Ground", "Carved Stakes", "Bait the Trap"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "demon_hunter_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "demon_hunter_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "demonhunter.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_caltrops/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("caltrops_max_traps"), value("Jagged Spikes", "damage_pct"), value("Jagged Spikes", "dot_duration_seconds"),
                         tune("caltrops_tick_seconds"), tune("caltrops_activation_wait_seconds"), value("", "duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 13, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Hooked Spines")\n            return Rune::HookedSpines;',
                                        'if (name == "Hooked Spines")\n            return Rune::JaggedSpikes;')),
            ("the oldest never gives way", (HEADER, "return most > 0 && placed >= most ? placed - most + 1 : 0;", "return 0;")),
            ("one too many stand", (HEADER, "placed - most + 1", "placed - most")),
            ("a tick is the whole damage", (HEADER, "return Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds));", "return totalPct;")),
            ("a trap waits for ever", (HEADER, "return limitMs > 0 && waitedMs >= limitMs;", "return false;")),
            ("a trap goes at once", (HEADER, "return limitMs > 0 && waitedMs >= limitMs;", "return true;")),
            ("the clock loses its rest", (CLOCK, "clock -= interval;", "clock = 0;")),
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
        self.assertEqual(runes(), RUNES)

    def test_the_record_is_the_engines_ground_cast(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["radius_yards"]), ("ground_area", "12"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "radius_yards"), value("", "slow_pct"), value("", "duration_seconds")],
                         [6, 12, 60, 6])
        self.assertEqual([value("Jagged Spikes", "damage_pct"), value("Jagged Spikes", "dot_duration_seconds")], [270, 6])
        self.assertEqual(value("Hooked Spines", "slow_pct"), 80)
        self.assertEqual(value("Torturous Ground", "immobilize_duration_seconds"), 2)
        self.assertEqual(value("Carved Stakes", "cost_resource"), 3)
        self.assertEqual(value("Bait the Trap", "crit_chance_pct"), 10)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("caltrops_tick_seconds", "0.25", "SF_1"), ("caltrops_slow_seconds", "0.5", "SF_4"),
                                 ("caltrops_activation_wait_seconds", "30", "SF_9"), ("caltrops_max_traps", "5", "SF_10")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Caltrops.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_the_bait_linger_is_a_marked_placeholder_and_the_check_is_the_ticks(self):
        row = tunables()["caltrops_bait_linger_seconds"]
        self.assertEqual((row["d3_value"], row["value"]), ("", "0.5"))
        self.assertIn("placeholder", row["notes"].lower())
        self.assertIn("0.25", row["notes"])
        self.assertEqual(tune("caltrops_tick_seconds"), 0.25)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("caltrops_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "radius_yards", "own"), ("Jagged Spikes", "radius_yards", "inherited"), ("Hooked Spines", "slow_pct", "own"),
                                    ("Torturous Ground", "slow_pct", "inherited"), ("Jagged Spikes", "damage_pct", "own"),
                                    ("Torturous Ground", "immobilize_duration_seconds", "own"), ("Bait the Trap", "crit_chance_pct", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Caltrops.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(0), value("", "radius_yards"))
        self.assertAlmostEqual(number(6) * 100, value("", "slow_pct"))
        self.assertAlmostEqual((number(6) + 0.20) * 100, value("Hooked Spines", "slow_pct"))
        self.assertAlmostEqual(number(13), value("", "duration_seconds"))
        self.assertAlmostEqual(number(8), value("", "cost_resource"))
        self.assertAlmostEqual(number(8) - 3, value("Carved Stakes", "cost_resource"))
        self.assertAlmostEqual(number(20) * value("Jagged Spikes", "dot_duration_seconds") * 100, value("Jagged Spikes", "damage_pct"))
        self.assertAlmostEqual(number(24), value("Torturous Ground", "immobilize_duration_seconds"))
        self.assertAlmostEqual(float(sf[28].split("?")[1].split(":")[0]) * 100, value("Bait the Trap", "crit_chance_pct"))
        self.assertAlmostEqual(number(1), tune("caltrops_tick_seconds"))
        self.assertAlmostEqual(number(4), tune("caltrops_slow_seconds"))
        self.assertAlmostEqual(number(9), tune("caltrops_activation_wait_seconds"))
        self.assertAlmostEqual(number(10), tune("caltrops_max_traps"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("return Caltrops::BasePct(spellId);"), 1)
        self.assertLess(self.dispatch.index("ElementalArrow::BasePct(spellId)"), self.dispatch.index("Caltrops::BasePct(spellId)"))
        for call in ("Caltrops::Ground(player, spellId, center);", "Caltrops::RegisterScripts();"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_trap_hits_nothing_when_it_is_laid(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_the_trap_springs_on_an_enemy_in_its_area_and_slows_every_tick(self):
        update = self.code[self.code.index("void OnPlayerUpdate("):self.code.index("void OnPlayerLogout(")]
        self.assertIn("if (!trap.sprung) {", update)
        self.assertIn("if (Approached(player, trap)) Spring(player, trap);", update)
        self.assertIn('WaitedOut(trap.waited, Tune("caltrops_activation_wait_seconds") * 1000.0)', update)
        self.assertIn('Due(trap.clock, diff, Tune("caltrops_tick_seconds") * 1000.0)', update)
        self.assertIn("if (trap.left <= 0) continue;", update)
        tick = self.code[self.code.index("void Tick("):self.code.index("bool Approached(")]
        self.assertIn('Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), Tune("caltrops_slow_seconds"));', tick)

    def test_the_runes_part(self):
        spring = self.code[self.code.index("void Spring("):self.code.index("void Tick(")]
        self.assertIn("RuneAt(trap.spellId) == Rune::TorturousGround", spring)
        self.assertIn('Root(player, enemy, Numbers::Num(trap.spellId, "immobilize_duration_seconds"));', spring)
        tick = self.code[self.code.index("void Tick("):self.code.index("bool Approached(")]
        self.assertIn("if (rune == Rune::JaggedSpikes)", tick)
        self.assertIn('Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "dot_duration_seconds")', tick)
        self.assertIn("true);", tick)
        self.assertIn('Numbers::Num(spellId, "crit_chance_pct")', tick)
        self.assertIn("Stat::CritChance, Bucket::Flat", tick)
        self.assertIn('if (ticks && rune == Rune::BaitTheTrap && player->GetExactDist(&trap.center) <= radius)', tick)
        self.assertIn('Tune("caltrops_bait_linger_seconds")', tick)
        self.assertNotIn("1000", tick)

    def test_the_traps_end_with_their_owner_and_the_oldest_give_way(self):
        self.assertIn("if (!player->IsAlive()) { Stop(player); return; }", self.code)
        self.assertIn("OnPlayerMapChanged", self.code)
        self.assertIn("OnPlayerLogout", self.code)
        self.assertIn('Overflow(laid.size(), std::size_t(Tune("caltrops_max_traps")))', self.code)


if __name__ == "__main__":
    unittest.main()
