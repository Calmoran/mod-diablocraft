"""Demon Hunter Grenade and its five runes (src/classes/demon_hunter/dc_demon_hunter_grenade.h and .cpp, with the stun and slow in
dc_demon_hunter_effects.cpp and the ticks' rules in dc_demon_hunter_dot.h).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_grenade/harness.cpp compiles the real dc_demon_hunter_grenade.h with
    the sheets' own rune names and numbers: each rune name is its rune; Grenade Cache's three grenades are one at the point aimed at
    and one on each side 15 degrees off the line (an even count has none on it, one grenade or none no fan); Cluster Grenades'
    200% is shared by its three pulses, the first at once and each after it a gap later. Six mutations planted in a scratch copy
    (two runes share a name, the fan leaves the middle grenade doubled, is lopsided, or ignores the spread, the pulses deal
    the whole total each or come all at once) must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of demon_hunter_skill_values.csv for
    Grenade (or the rune that states it), the generated value map says whose record holds it, and the numbers are the researched
    ones: 160% in the 6 yard radius, 4 Hatred (7 for Tinkerer), Cold Grenade's 120% over 3 seconds, Cluster Grenades' 200% over 9
    yards, Grenade Cache's 3 grenades of 160%, Stun Grenade's 20% for 1.5 seconds. Every tunable it reads is a row of
    data/tunables/demonhunter.csv, and the sheet's and the tunables' numbers equal the decoded Power/DemonHunter_Grenades.pow
    (skipped where the game archives are not on this machine).
  * **The wiring.** The class's dispatch hands the skill its three seams after the others' (the new Ground seam is called from the
    engine after the hits), the engine's hit at the point aimed at is the skill's for every rune but Cluster Grenades (its first
    pulse), the first pulse reaches only the ring beyond the engine's radius, the cloud ticks as periodic strikes and chills,
    and the stun is rolled for each enemy hit and stretched by the stun duration items.

What it does not prove: anything on a running server. The throw, the pulses, the cloud, the fan and the stun are
docs/test-diablocraft-vawmy.10.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_grenade.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_grenade.h"
SOURCES = ["src/combat/dc_damage_buckets.h", HEADER, "tests/demon_hunter_grenade/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_grenade.cpp"
SKILL = "Grenade"


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_grenade/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("Grenade Cache", "projectile_count"), tune("grenade_cache_spread_degrees"),
                         tune("grenade_cluster_pulses"), tune("grenade_cluster_pulse_seconds"), value("Cluster Grenades", "damage_pct"),
                         tune("grenade_min_throw_yards"), tune("grenade_cluster_min_throw_yards"),
                         tune("grenade_edge_damage_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 21, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::GrenadeCache;", "return Rune::Tinkerer;")),
            ("the middle grenade is doubled", (HEADER, "if (place != 0.0)", "if (true)")),
            ("the fan is lopsided", (HEADER, "double(count - 1) / 2.0", "double(count - 1) / 3.0")),
            ("the fan ignores the spread", (HEADER, "offsets.push_back(place * spreadDegrees);", "offsets.push_back(place);")),
            ("each pulse deals the whole total", (HEADER, "return pulses ? totalPct / pulses : totalPct;", "return totalPct;")),
            ("the pulses come all at once", (HEADER, "return gapSeconds * index;", "return 0.0;")),
            ("a grenade aimed near is not moved", (HEADER, "return aimedYards < minimum ? minimum : aimedYards;", "return aimedYards;")),
            ("every grenade is thrown the minimum", (HEADER, "return aimedYards < minimum ? minimum : aimedYards;", "return minimum;")),
            ("the minimum is a yard short", (HEADER, "return aimedYards < minimum ? minimum : aimedYards;", "return aimedYards < minimum ? minimum - 1 : aimedYards;")),
            ("the edge keeps all of it", (HEADER, "return 100.0 - (100.0 - edgePct) * share;", "return 100.0;")),
            ("the middle loses damage", (HEADER, "return 100.0 - (100.0 - edgePct) * share;", "return 100.0 - (100.0 - edgePct) * (0.1 + 0.9 * share);")),
            ("the falloff is not a straight line", (HEADER, "return 100.0 - (100.0 - edgePct) * share;", "return 100.0 - (100.0 - edgePct) * share * share;")),
            ("the damage keeps falling past the edge", (HEADER, "double const share = distance >= radius ? 1.0 : distance / radius;", "double const share = distance / radius;")),
            ("the edge keeps nothing", (HEADER, "return 100.0 - (100.0 - edgePct) * share;", "return 100.0 - 100.0 * share;")),
            ("a blast with no radius divides by it", (HEADER, "if (radius <= 0 || distance <= 0)\n            return 100.0;", "if (distance <= 0)\n            return 100.0;")),
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
        self.assertEqual(runes(), ["Cold Grenade", "Cluster Grenades", "Grenade Cache", "Tinkerer", "Stun Grenade"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "generated_resource"), value("", "damage_pct")], [4, 160])
        self.assertEqual([value("Cold Grenade", "damage_pct", q) for q in ("explosion", "cloud")], [160, 120])
        self.assertEqual(value("Cold Grenade", "dot_duration_seconds"), 3)
        self.assertEqual([value("Cluster Grenades", t) for t in ("damage_pct", "radius_yards")], [200, 9])
        self.assertEqual([value("Grenade Cache", t) for t in ("projectile_count", "damage_pct")], [3, 160])
        self.assertEqual(value("Tinkerer", "generated_resource"), 7)
        self.assertEqual([value("Stun Grenade", t) for t in ("proc_chance_pct", "stun_duration_seconds")], [20, 1.5])

    def test_the_tunables_are_the_power_files_and_nobody_has_set_them(self):
        rows = tunables()
        for name, number, source in (("grenade_cluster_pulses", "3", "SF_28"), ("grenade_cluster_pulse_seconds", "0.6", "SF_12"),
                                     ("grenade_cloud_tick_seconds", "0.5", "SF_27"), ("grenade_cloud_radius_yards", "6", "SF_5"),
                                     ("grenade_cloud_chill_pct", "60", "SF_34"), ("grenade_cache_spread_degrees", "15", "SF_11"),
                                     ("grenade_min_throw_yards", "6", "SF_1"), ("grenade_cluster_min_throw_yards", "8", "SF_1")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Grenades.pow", rows[name]["notes"])
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)

    def test_the_edge_damage_is_the_power_files_and_the_line_is_alexs(self):
        row = tunables()["grenade_edge_damage_pct"]
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("40", "", "percent"))
        self.assertIn("SF_3", row["notes"])
        self.assertIn("Power/DemonHunter_Grenades.pow", row["notes"])
        self.assertIn("q-1021-69", row["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("grenade_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "radius_yards", "dot_duration_seconds", "projectile_count", "proc_chance_pct",
                                  "stun_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "damage_pct", ""), ("Cold Grenade", "damage_pct", "cloud"),
                                       ("Cold Grenade", "dot_duration_seconds", ""), ("Cluster Grenades", "damage_pct", ""),
                                       ("Cluster Grenades", "radius_yards", ""), ("Grenade Cache", "projectile_count", ""),
                                       ("Grenade Cache", "damage_pct", ""), ("Stun Grenade", "proc_chance_pct", ""),
                                       ("Stun Grenade", "stun_duration_seconds", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertEqual(mapped[(rune, token, qualifier)]["origin"], "own")

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Grenades.pow"))["sf"]

        def number(n):
            return float(sf[n])

        def rune_part(n):
            return float(sf[n].split("?")[1].split(":")[0])

        self.assertAlmostEqual(number(3) * 100, tune("grenade_edge_damage_pct"))

        self.assertAlmostEqual(number(13) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(13) * 100, value("Cold Grenade", "damage_pct", "explosion"))
        self.assertAlmostEqual(number(26) * number(7) * 100, value("Cold Grenade", "damage_pct", "cloud"))
        self.assertAlmostEqual(number(7), value("Cold Grenade", "dot_duration_seconds"))
        # The total is the base times Cluster Grenades' 1.25, shared by the first pulse and the extra ones.
        pulses = rune_part(28) + 1
        self.assertAlmostEqual(number(13) * float(sf[15].split("?")[1].split(":")[0]) * 100, value("Cluster Grenades", "damage_pct"))
        self.assertAlmostEqual(pulses, tune("grenade_cluster_pulses"))
        self.assertAlmostEqual(6 + rune_part(18), value("Cluster Grenades", "radius_yards"))
        self.assertAlmostEqual(1 + rune_part(8), value("Grenade Cache", "projectile_count"))
        self.assertAlmostEqual(number(19), value("", "generated_resource"))
        self.assertAlmostEqual(number(19) + rune_part(24), value("Tinkerer", "generated_resource"))
        self.assertAlmostEqual(rune_part(9) * 100, value("Stun Grenade", "proc_chance_pct"))
        self.assertAlmostEqual(number(10), value("Stun Grenade", "stun_duration_seconds"))
        for n, name in ((12, "grenade_cluster_pulse_seconds"), (27, "grenade_cloud_tick_seconds"), (5, "grenade_cloud_radius_yards")):
            self.assertAlmostEqual(number(n), tune(name), msg=name)
        # SF_11 is "Rune_B ? 25 : 15": the fan of Grenade Cache is the 15 of every rune but Cluster Grenades.
        self.assertAlmostEqual(float(sf[11].split(":")[1]), tune("grenade_cache_spread_degrees"))
        # SF_1 is "Rune_B ? 8 : 6": the plain skill's 6, Cluster Grenades' 8.
        self.assertAlmostEqual(float(sf[1].split(":")[1]), tune("grenade_min_throw_yards"))
        self.assertAlmostEqual(rune_part(1), tune("grenade_cluster_min_throw_yards"))
        self.assertAlmostEqual(number(34) * 100, tune("grenade_cloud_chill_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        engine = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat/dc_combat_internal.h",
                                                                 *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.engine = re.sub(r"\s+", " ", engine)

    def test_the_dispatch_hands_the_skill_its_seams_after_the_others(self):
        self.assertEqual(self.dispatch.count("if (auto nade = Grenade::BasePct(spellId)) return nade;"), 1)
        self.assertLess(self.dispatch.index("EvasiveFire::BasePct(spellId)"), self.dispatch.index("Grenade::BasePct(spellId)"))
        self.assertEqual(self.dispatch.count("Grenade::Landed(player, target, spellId);"), 1)
        self.assertEqual(self.dispatch.count("Grenade::Ground(player, spellId, center);"), 1)
        self.assertEqual(self.dispatch.count("Grenade::Aim(player, spellId, center);"), 1)

    def test_the_engine_calls_the_ground_seam_after_the_hits_and_the_other_classes(self):
        call = "DemonHunter::Ground(player, shell.spellId, center);"
        self.assertEqual(self.engine.count(call), 1)
        self.assertLess(self.engine.index("Necromancer::Ground(player, shell.spellId, center);"), self.engine.index(call))
        self.assertLess(self.engine.index("ResolveHit(player, target, punch.pct ? punched : shell, info)"), self.engine.index(call))

    def test_the_aim_is_moved_out_along_the_line_before_the_cast_resolves(self):
        call = "DemonHunter::Aim(player, shell.spellId, center);"
        self.assertEqual(self.engine.count(call), 1)
        self.assertLess(self.engine.index("center = *GetExplTargetDest();"), self.engine.index(call))
        self.assertLess(self.engine.index(call), self.engine.index("previousSpline = player->movespline->GetId();"))
        aim = self.code[self.code.index("void Aim("):self.code.index("void Ground(")]
        self.assertIn("ThrownYards(aimed,", aim)
        self.assertIn('RuneAt(spellId) == Rune::ClusterGrenades ? Tune("grenade_cluster_min_throw_yards") : Tune("grenade_min_throw_yards")', aim)
        self.assertIn("if (thrown != aimed) {", aim)
        self.assertIn("aimed > 0 ? std::atan2(dy, dx) : player->GetOrientation()", aim)
        self.assertIn("std::cos(angle) * thrown", aim)

    def test_a_blast_hurts_less_toward_its_edge(self):
        self.assertEqual(self.dispatch.count("Grenade::Multipliers(player, target, spellId, out);"), 1)
        engine = self.engine
        call = "DemonHunter::Multipliers(player, target, shell.spellId, hit.factors);"
        self.assertEqual(engine.count(call), 1)
        self.assertLess(engine.index("Necromancer::Multipliers(player, target, shell.spellId, hit.factors);"), engine.index(call))
        multipliers = self.code[self.code.index("void Multipliers("):]
        self.assertIn('KeptPct(target->GetExactDist(&blast.center), blast.radius, Tune("grenade_edge_damage_pct"))', multipliers)
        self.assertIn('AddFactor(out, "Grenade falloff", kept - 100.0);', multipliers)
        self.assertIn("if (!player || !target || !Is(spellId)) return;", multipliers)
        self.assertIn("Blast blast = current; if (!blast.on) {", multipliers)

    def test_the_blast_is_known_to_the_engines_hit_and_to_the_explosions_strikes_and_not_to_the_cloud(self):
        aim = self.code[self.code.index("void Aim("):self.code.index("void Ground(")]
        self.assertIn("blasts[player->GetGUID().GetRawValue()] = Blast{center, BlastRadius(spellId), true};", aim)
        ground = self.code[self.code.index("void Ground("):self.code.index("void Multipliers(")]
        self.assertIn("blasts.erase(player->GetGUID().GetRawValue());", ground)
        self.assertLess(ground.index("blasts.erase("), ground.index("switch (RuneAt(spellId))"))
        self.assertIn("Scope scope(center, radius);", self.code)
        self.assertIn("Scope scope(landing, Combat::TargetRadius(spellId));", self.code)
        cloud = self.code[self.code.index("void Cloud("):self.code.index("void Fan(")]
        self.assertNotIn("Scope", cloud)
        radius = self.code[self.code.index("double BlastRadius("):self.code.index("struct Scope")]
        self.assertIn('RuneAt(spellId) == Rune::ClusterGrenades ? Numbers::Num(spellId, "radius_yards") : Combat::TargetRadius(spellId)', radius)

    def test_the_engines_hit_is_the_skills_except_cluster_grenades_first_pulse(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Landed(")]
        self.assertIn("if (RuneAt(spellId) == Rune::ClusterGrenades) return PulsePct(Numbers::Num(spellId, \"damage_pct\"), Pulses());", base)
        self.assertIn('return Numbers::Get(BaseId(Skill), "damage_pct");', base)

    def test_the_first_pulse_reaches_only_the_ring_beyond_the_engines_radius(self):
        cluster = self.code[self.code.index("void Cluster("):self.code.index("void Cloud(")]
        self.assertIn("Combat::TargetRadius(spellId)", cluster)
        self.assertIn("if (enemy->GetExactDist(center) > inner)", cluster)
        self.assertIn("for (unsigned pulse = 1; pulse < Pulses(); ++pulse)", cluster)
        self.assertIn("PulseAfter(pulse, gap)", cluster)

    def test_the_cloud_ticks_as_periodic_strikes_and_chills_what_it_hurts(self):
        cloud = self.code[self.code.index("void Cloud("):self.code.index("void Fan(")]
        self.assertIn("Combat::Strike(player, enemy, spellId, pct, true);", cloud)
        self.assertIn('Slow(player, enemy, Tune("grenade_cloud_chill_pct"), tick * 2);', cloud)
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn('Dot::TickPct(Numbers::Num(spellId, "damage_pct", "cloud"), ticks)', ground)
        self.assertIn("Dot::Ticks(seconds, tick)", ground)

    def test_the_fan_lands_the_same_distance_off_the_line_and_explodes_like_the_first(self):
        fan = self.code[self.code.index("void Fan("):self.code.index("} // namespace\n") if "} // namespace\n" in self.code else None]
        self.assertIn("FanOffsets(std::size_t(Numbers::Num(spellId, \"projectile_count\")), Tune(\"grenade_cache_spread_degrees\"))", fan)
        self.assertIn("std::cos(angle) * yards", fan)
        self.assertIn("Combat::Enemies(player, spellId, landing, Combat::TargetRadius(spellId))", fan)

    def test_the_stun_is_rolled_for_each_enemy_hit_and_stretched(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Ground(")]
        self.assertIn("RuneAt(spellId) == Rune::StunGrenade", landed)
        self.assertIn('roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct")))', landed)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', landed)


if __name__ == "__main__":
    unittest.main()
