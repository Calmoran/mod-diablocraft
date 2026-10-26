"""Witch Doctor Locust Swarm and its five runes (src/classes/witch_doctor/dc_witch_doctor_locust_swarm.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_locust_swarm/harness.cpp compiles the real dc_witch_doctor_locust_swarm.h and
    the shared arithmetic with the sheets' own rune names and numbers: each rune name is its rune; the swarm's ticks make the 1040% and
    the last falls when the 8 seconds end; only Searing Locusts has a total of its own (1480%); a jump waits the least plus up to the delta;
    Pestilence jumps to two under its chance and every other swarm to one; Diseased Swarm leaves a cloud for an enemy found dead with
    swarm left and no other rune does; the cloud's pulses make the 750% in 3 seconds. Ten mutations planted in a scratch copy (two runes
    share a name, every rune has the larger total, a jump never waits, every rune jumps twice, a swarm ending leaves a cloud, the cloud's
    pulses are lost, the jump goes to the farthest enemy, the swarm never ends, a tick returns the whole second, the first pulse falls
    at once) must each make it fail.
  * **The record needs no change.** The cast is the engine's single-enemy cast (a `single_enemy` row of skill_targeting.csv, an
    `instant_dot`); the Mana cost and each rune's school are the record's.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of witch_doctor_skill_values.csv for Locust Swarm
    (or the rune that states it): 300 Mana, 1040% over 8 seconds, Searing Locusts' 1480%, Pestilence's 100% chance, Cloud of Insects' 25%,
    Devouring Swarm's 25 Mana a second, Diseased Swarm's 750% over 3 seconds; every tunable is a row of data/tunables/witchdoctor.csv, and
    the numbers equal the decoded Power/Witchdoctor_Locust_Swarm.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the damage and cast seams; the swarm ticks and jumps on the player's own queue; a dead host with
    swarm left leaves the cloud for Diseased Swarm; Cloud of Insects weakens the swarmed through the shared enemy effects; Devouring Swarm
    pays Mana only for the first enemy.

What it does not prove: anything on a running server. The swarm, its jumps, the weakness, the Mana and the cloud are
docs/test-diablocraft-vxrcu.15.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_locust_swarm.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_locust_swarm.h"
CLOCK = "src/classes/witch_doctor/dc_witch_doctor_clock.h"
PICK = "src/classes/witch_doctor/dc_witch_doctor_pick.h"
PERIODIC = "src/combat/dc_periodic_strike.h"
SOURCES = [HEADER, CLOCK, PICK, PERIODIC, "tests/witch_doctor_locust_swarm/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_locust_swarm.cpp"
SKILL = "Locust Swarm"
RUNES = ["Searing Locusts", "Pestilence", "Cloud of Insects", "Devouring Swarm", "Diseased Swarm"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "witch_doctor_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "witch_doctor_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "witchdoctor.csv")}


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_locust_swarm/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "damage_pct"), value("", "dot_duration_seconds"), value("Searing Locusts", "damage_pct"),
                         tune("locust_swarm_tick_seconds"), tune("locust_swarm_jump_min_seconds"), tune("locust_swarm_jump_delta_seconds"),
                         value("Pestilence", "proc_chance_pct"), value("Diseased Swarm", "damage_pct"),
                         value("Diseased Swarm", "dot_duration_seconds"), tune("locust_swarm_cloud_tick_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 18, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Pestilence")\n            return Rune::Pestilence;',
                                        'if (name == "Pestilence")\n            return Rune::SearingLocusts;')),
            ("every rune has the larger total", (HEADER, "return rune == Rune::SearingLocusts ? runePct : skillPct;", "return runePct;")),
            ("a jump never waits", (HEADER, "return std::max(0.0, minSeconds) + std::max(0.0, deltaSeconds) * std::clamp(roll, 0.0, 1.0);", "return 0.0;")),
            ("every rune jumps twice", (HEADER, "return rune == Rune::Pestilence && roll < chancePct ? 2u : 1u;", "return roll < chancePct ? 2u : 1u;")),
            ("a swarm that ended leaves a cloud", (HEADER, "return rune == Rune::DiseasedSwarm && dead && leftSeconds > 0;", "return rune == Rune::DiseasedSwarm && dead;")),
            ("the jump goes to the farthest enemy", (PICK, "std::min_element(distances.begin(), distances.end())", "std::max_element(distances.begin(), distances.end())")),
            ("the swarm never ends", (CLOCK, "return std::max(0.0, leftSeconds - std::max(0.0, tickSeconds));", "return leftSeconds;")),
            ("a tick returns the whole second", (CLOCK, "return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;",
                                                 "return perSecond > 0 && tickSeconds > 0 ? perSecond : 0.0;")),
            ("the first pulse falls at once", (HEADER, "* 1000.0 * (index + 1) + 0.5", "* 1000.0 * index + 0.5")),
            ("the cloud's pulses are lost", (PERIODIC, "std::floor(seconds / tickSeconds + 1e-9)", "std::floor(seconds / tickSeconds - 0.5)")),
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

    def test_the_record_is_the_engines_single_enemy_cast(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["cast_type"]), ("single_enemy", "instant_dot"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", n) for n in ("cost_resource", "damage_pct", "dot_duration_seconds")], [300, 1040, 8])
        self.assertEqual([value("Searing Locusts", n) for n in ("damage_pct", "dot_duration_seconds")], [1480, 8])
        self.assertEqual(value("Pestilence", "proc_chance_pct"), 100)
        self.assertEqual(value("Cloud of Insects", "enemy_damage_pct"), 25)
        self.assertEqual(value("Devouring Swarm", "regen_per_second_resource"), 25)
        self.assertEqual([value("Diseased Swarm", n) for n in ("damage_pct", "dot_duration_seconds")], [750, 3])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("locust_swarm_jump_radius_yards", "30", "SF_2"), ("locust_swarm_jump_min_seconds", "0.5", "SF_4"),
                                 ("locust_swarm_jump_delta_seconds", "0.5", "SF_3"), ("locust_swarm_cloud_area_yards", "6", "SF_13"),
                                 ("locust_swarm_cloud_tick_seconds", "0.3", "SF_17")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/Witchdoctor_Locust_Swarm.pow", rows[name]["notes"])
        # The designer's standing default (AGENTS.md "Numbers", 2026-10-22), set in his column: a burn or bleed ticks every 0.5 seconds.
        self.assertEqual((rows["locust_swarm_tick_seconds"]["d3_value"], rows["locust_swarm_tick_seconds"]["value"]), ("", "0.5"))
        self.assertIn("standing default", rows["locust_swarm_tick_seconds"]["notes"])
        for name, row in rows.items():
            if name.startswith("locust_swarm_"):
                self.assertNotIn("placeholder", row["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("locust_swarm_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "dot_duration_seconds", "proc_chance_pct", "enemy_damage_pct", "regen_per_second_resource"})
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_pct", "own"), ("", "dot_duration_seconds", "own"), ("Searing Locusts", "damage_pct", "own"),
                                    ("Pestilence", "proc_chance_pct", "own"), ("Cloud of Insects", "enemy_damage_pct", "own"),
                                    ("Devouring Swarm", "regen_per_second_resource", "own"), ("Diseased Swarm", "damage_pct", "own"),
                                    ("Diseased Swarm", "dot_duration_seconds", "own")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token)]["origin"], origin)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_Locust_Swarm.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(9) * number(6) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(6), value("", "dot_duration_seconds"))
        self.assertAlmostEqual((number(9) + 0.55) * number(6) * 100, value("Searing Locusts", "damage_pct"))
        self.assertAlmostEqual(number(16) * 100, value("Pestilence", "proc_chance_pct"))
        self.assertAlmostEqual(number(5) * 100, value("Cloud of Insects", "enemy_damage_pct"))
        self.assertAlmostEqual(number(10), value("Devouring Swarm", "regen_per_second_resource"))
        self.assertAlmostEqual(number(12) * number(11) * 100, value("Diseased Swarm", "damage_pct"))
        self.assertAlmostEqual(number(11), value("Diseased Swarm", "dot_duration_seconds"))
        for name, n in (("locust_swarm_jump_radius_yards", 2), ("locust_swarm_jump_min_seconds", 4), ("locust_swarm_jump_delta_seconds", 3),
                        ("locust_swarm_cloud_area_yards", 13), ("locust_swarm_cloud_tick_seconds", 17)):
            self.assertAlmostEqual(number(n), tune(name), msg=name)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("LocustSwarm::BasePct(spellId)"), 1)
        self.assertEqual(self.dispatch.count("LocustSwarm::Cast(player, spellId, targets);"), 1)

    def test_the_cast_hits_nothing_and_the_swarm_ticks_and_jumps_on_the_players_queue(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        after = self.code[self.code.index("void After("):self.code.index("std::vector<ObjectGuid> Hosts(")]
        self.assertIn("player->m_Events.AddEventAtOffset(", after)
        infect = self.code[self.code.index("void Infect(Player* player, std::uint32_t spellId, Unit* enemy, bool first) {"):self.code.index("} // namespace")]
        self.assertIn("[player, stamp] { Tick(player, stamp); }", infect)
        self.assertIn("[player, stamp] { Jump(player, stamp); }", infect)
        self.assertIn("Infect(player, spellId, targets.front(), true);", self.code)

    def test_the_swarm_strikes_a_share_of_its_runes_total(self):
        tick = self.code[self.code.index("void Tick(Player* player, std::uint64_t stamp) {"):self.code.index("// The swarm settles")]
        self.assertIn('SwarmTotal(rune, Numbers::Num(BaseId(Skill), "damage_pct"), Numbers::Num(spellId, "damage_pct"))', tick)
        self.assertIn("Combat::Strike(player, host, spellId, PeriodicStrike::TickPct(total, ticks), true);", tick)
        self.assertIn('PeriodicStrike::Ticks(Duration(), tick)', tick)

    def test_each_rune_does_its_one_thing(self):
        tick = self.code[self.code.index("void Tick(Player* player, std::uint64_t stamp) {"):self.code.index("// The swarm settles")]
        self.assertIn("if (LeavesCloud(rune, true, swarm.leftSeconds)) Cloud(player, spellId, swarm.lastSeen);", tick)
        self.assertIn("if (rune == Rune::DevouringSwarm && swarm.first)", tick)
        self.assertIn('PerTick(Numbers::Num(spellId, "regen_per_second_resource"), tick)', tick)
        infect = self.code[self.code.index("void Infect(Player* player, std::uint32_t spellId, Unit* enemy, bool first) {"):self.code.index("} // namespace")]
        self.assertIn('EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), swarm.leftSeconds);', infect)
        jump = self.code[self.code.index("void Jump("):self.code.index("void Tick(")]
        self.assertIn('Tune("locust_swarm_jump_radius_yards")', jump)
        self.assertIn('Jumps(RuneAt(swarm.spellId), Numbers::Get(swarm.spellId, "proc_chance_pct").value_or(0.0), frand(0.0f, 100.0f))', jump)
        self.assertIn("Infect(player, swarm.spellId, free[*nearest], false);", jump)
        cloud = self.code[self.code.index("void Cloud("):self.code.index("void Infect(Player* player, std::uint32_t spellId, Unit* enemy, bool first);")]
        self.assertIn('Tune("locust_swarm_cloud_area_yards")', cloud)
        self.assertIn('Tune("locust_swarm_cloud_tick_seconds")', cloud)


if __name__ == "__main__":
    unittest.main()
