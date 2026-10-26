"""Demon Hunter Elemental Arrow and its five runes (src/classes/demon_hunter/dc_demon_hunter_elemental_arrow.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_elemental_arrow/harness.cpp compiles the real
    dc_demon_hunter_elemental_arrow.h, the DoT rules and the clock with the sheets' own rune names and numbers: each rune name is its
    rune; a slow projectile covers its speed a second and stops at the end of its path; Ball Lightning's two shocks make the rune's
    damage; Nether Tentacles' heal is its share of the maximum Life for each enemy; the ticks of Immolation Arrow's ground make its
    total; a tentacle held through its path ticks at its cadence. Eight mutations planted in a scratch copy must each make it fail.
  * **The records.** The migration combat_0101 gives Frost Arrow, Ball Lightning, Immolation Arrow and Nether Tentacles the aim at one
    enemy (the rune texts name one), where the base skill and Lightning Bolts keep the line through every enemy.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Elemental
    Arrow; every tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_ElementalArrow.pow (skipped where the game archives are not on this machine). The speed of the slow projectiles is the
    file's 0.4 yards a frame at 60 frames a second (AGENTS.md 'Numbers'); the length of their path is a marked placeholder.
  * **The wiring.** The dispatch answers the seams; the cone's and the ground's own strikes start nothing; Ball Lightning and Nether
    Tentacles hit nothing at the cast and fly until the end of their path; the stun is on a critical hit only.

What it does not prove: anything on a running server. The arrow, the cone, the ball, the tentacle and the burning ground are
docs/test-diablocraft-vawmy.15.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_elemental_arrow.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_elemental_arrow.h"
DOT = "src/classes/demon_hunter/dc_demon_hunter_dot.h"
CLOCK = "src/classes/demon_hunter/dc_demon_hunter_clock.h"
SOURCES = [HEADER, DOT, CLOCK, "tests/demon_hunter_elemental_arrow/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_elemental_arrow.cpp"
SKILL = "Elemental Arrow"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0101_demon_hunter_elemental_arrow_runes_aim_at_one_enemy.sql"
RUNES = ["Frost Arrow", "Ball Lightning", "Immolation Arrow", "Nether Tentacles", "Lightning Bolts"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_elemental_arrow/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("Nether Tentacles", "heal_pct"), value("Immolation Arrow", "damage_pct", "ground"),
                         value("Immolation Arrow", "dot_duration_seconds"), tune("elemental_arrow_immolation_tick_seconds"),
                         tune("elemental_arrow_slow_projectile_yards_per_second"), tune("elemental_arrow_travel_yards"),
                         tune("elemental_arrow_tentacle_tick_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 14, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Ball Lightning")\n            return Rune::BallLightning;',
                                        'if (name == "Ball Lightning")\n            return Rune::FrostArrow;')),
            ("a projectile flies a second as a millisecond", (HEADER, "yardsPerSecond * elapsedMs / 1000.0", "yardsPerSecond * elapsedMs")),
            ("a projectile never stops", (HEADER, "return std::min(travel, yardsPerSecond * elapsedMs / 1000.0);",
                                          "return yardsPerSecond * elapsedMs / 1000.0;")),
            ("a projectile arrives early", (HEADER, "return flown >= travel;", "return flown >= travel - 5;")),
            ("a shock is the whole damage", (HEADER, "return shocks ? damagePct / shocks : 0.0;", "return shocks ? damagePct : 0.0;")),
            ("the heal ignores the enemies", (HEADER, "maxLife * healPct / 100.0 * hits", "maxLife * healPct / 100.0")),
            ("the heal is a share of a hundred times", (HEADER, "maxLife * healPct / 100.0 * hits", "maxLife * healPct * hits")),
            ("a tick of the ground is the whole total", (HEADER, "return Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds));",
                                                         "return totalPct;")),
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


class Records(unittest.TestCase):
    def test_four_runes_aim_at_one_enemy_and_the_others_keep_the_line(self):
        migration = MIGRATION.read_text(encoding="utf-8")
        ids = {r[1]: int(r[0]) for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
               if r and r[0].isdigit() and r[4] in ("active", "rune")}
        kinds = {int(m.group(1)): m.group(2) for m in re.finditer(r"INSERT INTO dc_spell_targeting VALUES \((\d+),'(\w+)'", migration)}
        for name in ("Frost Arrow", "Ball Lightning", "Immolation Arrow", "Nether Tentacles"):
            self.assertEqual(kinds[ids[f"{SKILL} - {name}"]], "single_enemy", name)
        for name in (SKILL, f"{SKILL} - Lightning Bolts"):
            self.assertEqual(kinds[ids[name]], "line_pierce", name)


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), RUNES)

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct")], [10, 300])
        self.assertEqual([value("Frost Arrow", "damage_pct"), value("Frost Arrow", "max_count"), value("Frost Arrow", "chill_pct"),
                          value("Frost Arrow", "chill_duration_seconds")], [330, 10, 60, 1])
        self.assertEqual([value("Ball Lightning", "damage_pct"), value("Nether Tentacles", "damage_pct"),
                          value("Lightning Bolts", "damage_pct")], [300, 300, 300])
        self.assertEqual([value("Immolation Arrow", "damage_pct", "hit"), value("Immolation Arrow", "damage_pct", "ground"),
                          value("Immolation Arrow", "dot_duration_seconds"), value("Immolation Arrow", "radius_yards")], [300, 315, 2, 10])
        self.assertEqual([value("Nether Tentacles", "heal_pct"), value("Lightning Bolts", "stun_duration_seconds")], [0.4, 1])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("elemental_arrow_cone_radius_yards", "35", "SF_13"), ("elemental_arrow_cone_degrees", "120", "SF_14"),
                                 ("elemental_arrow_cone_delay_seconds", "0.17", "SF_16"), ("elemental_arrow_ball_seek_yards", "15", "SF_22"),
                                 ("elemental_arrow_ball_tick_seconds", "0.7", "SF_21"),
                                 ("elemental_arrow_ball_shock_delay_seconds", "0.1", "SF_24"),
                                 ("elemental_arrow_tentacle_tick_seconds", "0.35", "SF_30"),
                                 ("elemental_arrow_tentacle_radius_yards", "6", "SF_31"),
                                 ("elemental_arrow_immolation_tick_seconds", "0.5", "SF_2")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_ElementalArrow.pow", rows[name]["notes"])
        speed = rows["elemental_arrow_slow_projectile_yards_per_second"]
        self.assertEqual((speed["d3_value"], speed["value"]), ("24", ""))
        self.assertIn("AGENTS.md 'Numbers'", speed["notes"])
        travel = rows["elemental_arrow_travel_yards"]
        self.assertEqual(travel["d3_value"], "")
        self.assertIn("placeholder", travel["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'"(elemental_arrow_[a-z_]+)"', text)),
                         {name for name in tunables() if name.startswith("elemental_arrow_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"], r["qualifier"] if "qualifier" in r else ""): r
                  for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token in (("Frost Arrow", "damage_pct"), ("Ball Lightning", "damage_pct"), ("Nether Tentacles", "damage_pct"),
                            ("Nether Tentacles", "heal_pct"), ("Lightning Bolts", "stun_duration_seconds"),
                            ("Frost Arrow", "chill_pct"), ("Frost Arrow", "max_count"), ("Immolation Arrow", "dot_duration_seconds")):
            self.assertEqual(mapped[(rune, token, "")]["origin"], "own", (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_ElementalArrow.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(0) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(11) * 100, value("Frost Arrow", "damage_pct"))
        self.assertAlmostEqual(number(15), value("Frost Arrow", "max_count"))
        self.assertAlmostEqual(number(18) * 100, value("Frost Arrow", "chill_pct"))
        self.assertAlmostEqual(number(19), value("Frost Arrow", "chill_duration_seconds"))
        self.assertAlmostEqual(number(4) * 100, value("Immolation Arrow", "damage_pct", "hit"))
        self.assertAlmostEqual(number(5) * 100, value("Immolation Arrow", "damage_pct", "ground"))
        self.assertAlmostEqual(number(6), value("Immolation Arrow", "dot_duration_seconds"))
        self.assertAlmostEqual(number(7), value("Immolation Arrow", "radius_yards"))
        self.assertAlmostEqual(number(32) * 100, value("Nether Tentacles", "damage_pct"))
        self.assertAlmostEqual(number(33) * 100, value("Nether Tentacles", "heal_pct"))
        self.assertAlmostEqual(number(38), value("Lightning Bolts", "stun_duration_seconds"))
        self.assertAlmostEqual(number(2), tune("elemental_arrow_immolation_tick_seconds"))
        self.assertAlmostEqual(number(13), tune("elemental_arrow_cone_radius_yards"))
        self.assertAlmostEqual(number(14), tune("elemental_arrow_cone_degrees"))
        self.assertAlmostEqual(number(16), tune("elemental_arrow_cone_delay_seconds"))
        self.assertAlmostEqual(number(21), tune("elemental_arrow_ball_tick_seconds"))
        self.assertAlmostEqual(number(22), tune("elemental_arrow_ball_seek_yards"))
        self.assertAlmostEqual(number(24), tune("elemental_arrow_ball_shock_delay_seconds"))
        self.assertAlmostEqual(number(30), tune("elemental_arrow_tentacle_tick_seconds"))
        self.assertAlmostEqual(number(31), tune("elemental_arrow_tentacle_radius_yards"))
        # The two shocks of a tick together are the sheet's 300%: SF_26 is half of SF_0.
        self.assertAlmostEqual(number(0) * 0.5 * 2 * 100, value("Ball Lightning", "damage_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto arrow = ElementalArrow::BasePct(spellId)) return arrow;"), 1)
        self.assertLess(self.dispatch.index("Chakram::BasePct(spellId)"), self.dispatch.index("ElementalArrow::BasePct(spellId)"))
        for call in ("ElementalArrow::Landed(player, target, spellId, critical);", "ElementalArrow::Cast(player, spellId, targets);",
                     "ElementalArrow::RegisterScripts();"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_projectiles_hit_nothing_at_the_cast_and_immolation_states_its_hit(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Landed(")]
        self.assertIn("if (rune == Rune::BallLightning || rune == Rune::NetherTentacles) return 0.0;", base)
        self.assertIn('return Numbers::Get(spellId, "damage_pct", "hit");', base)
        self.assertIn("return std::nullopt;", base)

    def test_the_cones_and_the_grounds_strikes_start_nothing(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Cast(")]
        self.assertIn("if (splitting || burning || !player || !target) return;", landed)
        self.assertIn("Scope scope(splitting);", self.code)
        self.assertIn("Scope scope(burning);", self.code)

    def test_the_stun_is_on_a_critical_hit_and_stretched_by_the_items(self):
        landed = self.code[self.code.index("case Rune::LightningBolts:"):self.code.index("default:")]
        self.assertIn("if (critical)", landed)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', landed)

    def test_the_ball_shocks_twice_and_the_tentacle_heals_for_the_enemies_it_struck(self):
        self.assertIn("constexpr unsigned ShocksPerTick = 2;", self.code)
        self.assertIn('ShockPct(Numbers::Num(spellId, "damage_pct"), ShocksPerTick)', self.code)
        self.assertIn('TentacleHeal(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), hits)', self.code)
        self.assertIn("if (Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, \"damage_pct\"))) ++hits;", self.code)

    def test_a_flight_ends_with_its_path_and_the_state_ends_with_its_owner(self):
        self.assertIn("over = Arrived(flown, travel);", self.code)
        self.assertIn("if (!player->IsAlive()) { Stop(player); return; }", self.code)
        self.assertIn("OnPlayerMapChanged", self.code)
        self.assertIn("OnPlayerLogout", self.code)


if __name__ == "__main__":
    unittest.main()
