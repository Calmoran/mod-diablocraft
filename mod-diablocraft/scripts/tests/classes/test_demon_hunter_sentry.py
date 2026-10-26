"""Demon Hunter Sentry and its five runes (src/classes/demon_hunter/dc_demon_hunter_sentry.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_sentry/harness.cpp compiles the real dc_demon_hunter_sentry.h with the
    sheets' own rune names and numbers: each rune name is its rune; the fire rate is the attack speed; a rocket's pause and flight;
    the chain's pulses together make the sheet's damage; a link's reach; the turret shoots the nearest enemy; the shield is held
    past the next pulse. Mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The skill is the engine's self-summon (a `self_summon` row of skill_targeting.csv) that hits
    nothing, so the one new migration is the tunables'.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Sentry (or the
    rune that states it); every tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_Sentry.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams; the cast spends a charge of the sheet's count and recharge and lays the turret as
    a periodic device of the shared ground-device piece; each rune's pulse is a device beside it.

What it does not prove: anything on a running server. The turret, the shots and the runes are docs/test-diablocraft-vawmy.26.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_sentry.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_sentry.h"
SOURCES = [HEADER, "tests/demon_hunter_sentry/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_sentry.cpp"
SKILL = "Sentry"
RUNES = ["Chain of Torment", "Impaling Bolt", "Spitfire Turret", "Polar Station", "Guardian Turret"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_sentry/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("sentry_rocket_rate_factor"), tune("sentry_rocket_warmup_seconds"), tune("sentry_rocket_seconds_per_yard"),
                         value("Chain of Torment", "damage_pct"), tune("sentry_chain_pulse_seconds"), tune("sentry_chain_touch_yards"),
                         tune("sentry_chain_max_yards"), tune("sentry_aura_pulse_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 25, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Impaling Bolt")\n            return Rune::ImpalingBolt;',
                                        'if (name == "Impaling Bolt")\n            return Rune::ChainOfTorment;')),
            ("every shot keeps the rune's element", (HEADER, "return rune != Rune::SpitfireTurret;", "return true;")),
            ("the fire rate is the attack speed squared", (HEADER, "1000.0 / attacksPerSecond", "1000.0 / (attacksPerSecond * attacksPerSecond)")),
            ("a turret without speed still shoots", (HEADER, "return attacksPerSecond > 0 ? std::uint32_t(1000.0 / attacksPerSecond + 0.5) : 0u;",
                                                      "return std::uint32_t(1000.0 / (attacksPerSecond > 0 ? attacksPerSecond : 1.0) + 0.5);")),
            ("a rocket ignores the speed", (HEADER, "rateFactor / attacksPerSecond * 1000.0", "rateFactor * 1000.0")),
            ("a rocket lands at once", (HEADER, "(warmupSeconds + perYardSeconds * std::max(0.0, yards))", "0.0")),
            ("a rocket's flight is its warmup alone", (HEADER, "warmupSeconds + perYardSeconds * std::max(0.0, yards)", "warmupSeconds")),
            ("a pulse is the whole second", (HEADER, "return perSecondPct * intervalSeconds;", "return perSecondPct;")),
            ("a link runs on before its start", (HEADER, "along = std::clamp(along, 0.0, 1.0);", "along = std::min(along, 1.0);")),
            ("a link runs on past its end", (HEADER, "along = std::clamp(along, 0.0, 1.0);", "along = std::max(along, 0.0);")),
            ("a link of no length divides by nothing", (HEADER, "length2 > 0 ? ((px - ax) * dx + (py - ay) * dy) / length2 : 0.0",
                                                         "((px - ax) * dx + (py - ay) * dy) / length2")),
            ("a link holds for ever", (HEADER, "return length <= maxYards;", "return true;")),
            ("a link holds one yard short", (HEADER, "return length <= maxYards;", "return length < maxYards;")),
            ("the chain touches everything", (HEADER, "return distanceToLink <= touchYards;", "return true;")),
            ("the turret shoots the farthest", (HEADER, "distances[i] < distances[best]", "distances[i] > distances[best]")),
            ("the shield lapses between pulses", (HEADER, "return 2.0 * pulseSeconds;", "return pulseSeconds;")),
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

    def test_the_record_is_the_engines_self_summon(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["radius_yards"]), ("self_summon", "60"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct"), value("", "duration_seconds"), value("", "max_count"),
                          value("", "charge_recharge_seconds"), value("", "charge_count")], [20, 280, 30, 2, 8, 2])
        self.assertEqual(value("Chain of Torment", "damage_pct"), 300)
        self.assertEqual(value("Spitfire Turret", "damage_pct"), 120)
        self.assertEqual([value("Polar Station", "radius_yards"), value("Polar Station", "slow_pct")], [16, 60])
        self.assertEqual(value("Guardian Turret", "damage_reduction_pct"), 25)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("sentry_attack_radius_yards", "60", "SF_3"), ("sentry_chain_pulse_seconds", "0.5", "SF_15"),
                                 ("sentry_chain_touch_yards", "3", "SF_4"), ("sentry_chain_max_yards", "45", "SF_5"),
                                 ("sentry_aura_pulse_seconds", "0.5", "SF_8"), ("sentry_shield_radius_yards", "16", "SF_9"),
                                 ("sentry_shot_chill_pct", "60", "SF_26"), ("sentry_chill_seconds", "1", "SF_29"),
                                 ("sentry_rocket_rate_factor", "0.9", "SF_12"), ("sentry_rocket_warmup_seconds", "0.4", "SF_13"),
                                 ("sentry_rocket_seconds_per_yard", "0.01", "SF_14")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Sentry.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_the_turret_display_is_alexs_pick(self):
        row = tunables()["sentry_turret_display_id"]
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("", "19218", "count"))
        self.assertIn("Gnomish Flame Turret", row["notes"])
        self.assertIn("q-1021-106", row["notes"])

    def test_the_pierce_width_is_alexs_standing_default(self):
        row = tunables()["sentry_pierce_width_yards"]
        self.assertEqual((row["d3_value"], row["value"]), ("", "3"))
        self.assertIn("standing default", row["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("sentry_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_pct", "own"), ("Impaling Bolt", "duration_seconds", "inherited"),
                                    ("Chain of Torment", "damage_pct", "own"), ("Spitfire Turret", "damage_pct", "own"),
                                    ("Polar Station", "slow_pct", "own"), ("Polar Station", "radius_yards", "own"),
                                    ("Guardian Turret", "damage_reduction_pct", "own"), ("Guardian Turret", "charge_count", "inherited")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Sentry.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(3), tune("sentry_attack_radius_yards"))
        self.assertAlmostEqual(number(17), value("", "duration_seconds"))
        self.assertAlmostEqual(number(22), value("", "max_count"))
        self.assertAlmostEqual(number(23), value("", "charge_recharge_seconds"))
        self.assertAlmostEqual(number(6) * 100, value("Chain of Torment", "damage_pct"))
        self.assertAlmostEqual(number(15), tune("sentry_chain_pulse_seconds"))
        self.assertAlmostEqual(number(4), tune("sentry_chain_touch_yards"))
        self.assertAlmostEqual(number(5), tune("sentry_chain_max_yards"))
        self.assertAlmostEqual(number(8), tune("sentry_aura_pulse_seconds"))
        self.assertAlmostEqual(number(9), tune("sentry_shield_radius_yards"))
        self.assertAlmostEqual(number(9), value("Polar Station", "radius_yards"))
        self.assertAlmostEqual(number(11) * 100, value("Polar Station", "slow_pct"))
        self.assertAlmostEqual(number(26) * 100, tune("sentry_shot_chill_pct"))
        self.assertAlmostEqual(number(29), tune("sentry_chill_seconds"))
        self.assertAlmostEqual(float(str(sf[10]).split("?")[1].split(":")[0]) * 100, value("Guardian Turret", "damage_reduction_pct"))
        self.assertAlmostEqual(float(str(sf[12]).split("/")[0]), tune("sentry_rocket_rate_factor"))
        self.assertEqual(str(sf[12]).split("/")[1].strip(), "Attacks_Per_Second_Total")
        self.assertEqual(str(sf[1]).strip(), "Attacks_Per_Second_Total")
        self.assertAlmostEqual(number(13), tune("sentry_rocket_warmup_seconds"))
        self.assertAlmostEqual(number(14), tune("sentry_rocket_seconds_per_yard"))
        self.assertAlmostEqual(number(19) * 100, value("Spitfire Turret", "damage_pct"))
        self.assertAlmostEqual(number(2) * 100, value("", "damage_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("return turret;"), 1)
        self.assertLess(self.dispatch.index("Sentry::BasePct(spellId)"), self.dispatch.index("Caltrops::BasePct(spellId)"))
        self.assertEqual(self.dispatch.count("Sentry::Cast(player, spellId);"), 1)

    def test_the_turret_hits_nothing_when_it_is_set_down(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_the_cast_spends_a_charge_of_the_sheets_count_and_recharge(self):
        spend = self.code[self.code.index("void SpendCharge("):self.code.index("void Shoot(")]
        self.assertIn('Passive::MostStanding(player, "sentry", unsigned(Numbers::Num(spellId, "charge_count")))', spend)
        self.assertIn('Numbers::Num(spellId, "charge_recharge_seconds")', spend)
        self.assertIn("ReducedCooldownMilliseconds(", spend)
        self.assertIn(".Spend(Now(), cap, period)", spend)
        self.assertIn("SendSkillCooldown(player, spellId, std::uint32_t(wait));", spend)
        cast = self.code[self.code.index("void Cast("):]
        self.assertLess(cast.index("SpendCharge(player, spellId);"), cast.index("Lay(player, spellId);"))

    def test_the_turret_is_a_periodic_device_of_the_shared_piece(self):
        lay = self.code[self.code.index("void Lay("):self.code.index("bool Is(")]
        self.assertIn("turret.spec.mode = GroundDevice::Mode::Periodic;", lay)
        self.assertIn('turret.spec.radiusYards = Tune("sentry_attack_radius_yards");', lay)
        self.assertIn('turret.spec.lifetimeMs = Numbers::Num(base, "duration_seconds") * Passive::DurationFactor(player, "Sentry") * 1000.0;', lay)
        self.assertIn("turret.spec.intervalMs = ShotMs(attacks);", lay)
        self.assertIn('turret.spec.most = std::size_t(Passive::MostStanding(player, "sentry", unsigned(Numbers::Num(base, "max_count"))));', lay)
        self.assertIn("double const attacks = Combat::AttacksPerSecond(player, spellId);", lay)
        self.assertIn("GroundDevice::Place(player, turret, at);", lay)
        self.assertIn("Position const at = player->GetPosition();", lay)

    def test_custom_engineering_asks_for_the_turrets_time_cap_and_charges(self):
        # The sheet side: the passive's numbers are above what the skill states, so asking the seams changes the result.
        passive = {(r["token"], r["qualifier"]): float(r["value"]) for r in read(D3 / "demon_hunter_passive_values.csv")
                   if r["skill"] == "Custom Engineering"}
        self.assertGreater(passive[("max_count", "sentry")], value("", "max_count"))
        self.assertGreater(passive[("max_count", "sentry")], value("", "charge_count"))
        self.assertEqual(value("", "duration_seconds") * (1 + passive[("duration_bonus_pct", "")] / 100), 60)
        # The code side: the turret's life, its cap and the stored charges all go through the passive's seams.
        self.assertIn('#include "dc_demon_hunter_passives.h"', CODE.read_text(encoding="utf-8"))
        spend = self.code[self.code.index("void SpendCharge("):self.code.index("void Shoot(")]
        self.assertIn("unsigned const cap = Passive::MostStanding(", spend)
        lay = self.code[self.code.index("void Lay("):self.code.index("bool Is(")]
        self.assertEqual(lay.count("Passive::DurationFactor(player, \"Sentry\")"), 1)
        self.assertEqual(lay.count("Passive::MostStanding(player, \"sentry\""), 1)
        # The rune's pulse is a copy of the turret, so it lives as long and counts as many.
        self.assertLess(lay.index("turret.spec.most ="), lay.index("GroundDevice::Setup pulse = turret;"))
        self.assertLess(lay.index("turret.spec.lifetimeMs ="), lay.index("GroundDevice::Setup pulse = turret;"))

    def test_the_turret_shoots_the_nearest_enemy_for_the_skills_damage(self):
        shoot = self.code[self.code.index("void Shoot("):self.code.index("void Chain(")]
        self.assertIn("Nearest(distances)", shoot)
        self.assertIn('Numbers::Num(base, "damage_pct")', shoot)
        self.assertIn("ShotTakesRuneElement(rune) ? spellId : base", shoot)
        self.assertIn("Combat::Strike(owner, target, striker, pct);", shoot)

    def test_the_runes_part(self):
        shoot = self.code[self.code.index("void Shoot("):self.code.index("void Chain(")]
        self.assertIn("if (rune == Rune::ImpalingBolt)", shoot)
        self.assertIn('Tune("sentry_pierce_width_yards")', shoot)
        self.assertIn("OnLine(", shoot)
        self.assertIn('Slow(owner, target, Tune("sentry_shot_chill_pct"), Tune("sentry_chill_seconds"));', shoot)
        chain = self.code[self.code.index("void Chain("):self.code.index("void Rocket(")]
        self.assertIn('PulsePct(Numbers::Num(spellId, "damage_pct"), Tune("sentry_chain_pulse_seconds"))', chain)
        self.assertIn("GroundDevice::Places(owner, BaseId(Skill))", chain)
        self.assertIn("{{owner->GetPosition(), place}}", chain)
        self.assertIn("if (!Linked(from.GetExactDist2d(&to), reach)) continue;", chain)
        self.assertIn("Touches(DistanceToSegment(", chain)
        rocket = self.code[self.code.index("void Rocket("):self.code.index("void Chill(")]
        self.assertIn("urand(0, uint32(enemies.size() - 1))", rocket)
        self.assertIn("RocketDelayMs(", rocket)
        self.assertIn('Combat::Strike(owner, enemy, spellId, Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(owner));', rocket)
        chill = self.code[self.code.index("void Chill("):self.code.index("void Shield(")]
        self.assertIn('Slow(owner, enemy, Numbers::Num(spellId, "slow_pct"), Tune("sentry_chill_seconds"));', chill)
        shield = self.code[self.code.index("void Shield("):self.code.index("void Lay(")]
        self.assertIn("owner->GetGroup()", shield)
        self.assertIn('Tune("sentry_shield_radius_yards")', shield)
        self.assertIn("ShieldHoldSeconds(Tune(\"sentry_aura_pulse_seconds\"))", shield)
        self.assertIn('Stat::SpecificReduction, Bucket::Flat, Numbers::Num(spellId, "damage_reduction_pct"), 1, hold', shield)

    def test_the_turret_wears_the_display_and_its_pulse_does_not(self):
        lay = self.code[self.code.index("void Lay("):self.code.index("bool Is(")]
        self.assertIn('turret.display = std::uint32_t(Tune("sentry_turret_display_id"));', lay)
        self.assertIn("pulse.display = 0;", lay)
        self.assertLess(lay.index("turret.display ="), lay.index("GroundDevice::Place(player, turret, at);"))
        self.assertLess(lay.index("GroundDevice::Setup pulse = turret;"), lay.index("pulse.display = 0;"))

    def test_each_rune_with_a_pulse_lays_one_beside_the_turret(self):
        lay = self.code[self.code.index("void Lay("):self.code.index("bool Is(")]
        self.assertIn("pulse.kind = PulseKind();", lay)
        for rune in ("ChainOfTorment", "SpitfireTurret", "PolarStation", "GuardianTurret"):
            self.assertIn(f"case Rune::{rune}:", lay)
        self.assertIn("default: return;", lay)
        self.assertIn("pulse.spec.radiusYards = Numbers::Num(spellId, \"radius_yards\");", lay)
        self.assertIn("pulse.spec.intervalMs = RocketMs(Tune(\"sentry_rocket_rate_factor\"), attacks);", lay)
        self.assertLess(lay.index("GroundDevice::Place(player, turret, at);"), lay.index("GroundDevice::Place(player, pulse, at);"))


if __name__ == "__main__":
    unittest.main()
