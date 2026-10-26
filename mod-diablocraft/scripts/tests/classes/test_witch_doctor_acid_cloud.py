"""Witch Doctor Acid Cloud and its five runes (src/classes/witch_doctor/dc_witch_doctor_acid_cloud.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_acid_cloud/harness.cpp compiles the real dc_witch_doctor_acid_cloud.h
    with the sheets' own rune names and numbers: each rune name is its rune; which part of a rune takes its element; when the impact
    lands; which enemies a burst reaches (the first to the inner radius, Acid Rain's outer ring past it); which enemies stand in Kiss
    of Death's cone (ahead, within its range and half its angle each side, across the half turn too); the pool's ticks make its
    damage. Mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Acid Cloud (or
    the rune that states it) the engine can read, qualified or inherited as the code asks; every tunable is a row of
    data/tunables/witchdoctor.csv; the numbers equal the decoded Power/Witchdoctor_AcidCloud.pow (skipped where the game archives
    are not on this machine).
  * **The wiring.** The dispatch answers the seams, and the engine calls the class's new Ground seam; the cast hits nothing; the
    impact is a burst of the band the rune reaches; the pool is a periodic device of the shared piece; Kiss of Death's cone and cloud
    are its own.

What it does not prove: anything on a running server. The impact, the pools and the runes are docs/test-diablocraft-vxrcu.25.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_acid_cloud.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_acid_cloud.h"
SOURCES = [HEADER, "src/combat/dc_periodic_strike.h", "tests/witch_doctor_acid_cloud/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_acid_cloud.cpp"
SKILL = "Acid Cloud"
POWER = "Power/Witchdoctor_AcidCloud.pow"
RUNES = ["Corpse Bomb", "Acid Rain", "Lob Blob Bomb", "Slow Burn", "Kiss of Death"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_acid_cloud/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("acid_cloud_impact_delay_seconds"), tune("acid_cloud_corpse_delay_seconds"), tune("acid_cloud_barf_delay_seconds"),
                         tune("acid_cloud_impact_radius_yards"), value("Acid Rain", "radius_yards"), tune("acid_cloud_barf_range_yards"),
                         tune("acid_cloud_barf_angle_degrees"), value("", "damage_pct", "dot"), value("", "dot_duration_seconds"),
                         tune("acid_cloud_tick_seconds")]
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
            ("two runes share a name", (HEADER, 'if (name == "Acid Rain")\n            return Rune::AcidRain;',
                                        'if (name == "Acid Rain")\n            return Rune::CorpseBomb;')),
            ("Slow Burn's impact takes the frost", (HEADER, "return rune != Rune::SlowBurn;", "return true;")),
            ("Corpse Bomb's pool takes the fire", (HEADER, "return rune != Rune::CorpseBomb;", "return true;")),
            ("Corpse Bomb explodes at once", (HEADER, "return rune == Rune::CorpseBomb ? corpse :", "return rune == Rune::CorpseBomb ? base :")),
            ("Kiss of Death spits after the base delay", (HEADER, "rune == Rune::KissOfDeath ? barf : base", "base")),
            ("the first burst reaches only the middle", (HEADER, "return distance > inner && distance <= outer;", "return distance > inner && distance < 0.5;")),
            ("the first burst misses the inner edge", (HEADER, "return distance > inner && distance <= outer;", "return distance > inner && distance < outer;")),
            ("the outer ring takes the inner too", (HEADER, "return distance > inner && distance <= outer;", "return distance <= outer;")),
            ("the cone has no range", (HEADER, "if (distance > length)\n            return false;", "")),
            ("the cone is twice as wide", (HEADER, "off <= degrees * Pi / 360.0 + 1e-9", "off <= degrees * Pi / 180.0 + 1e-9")),
            ("the cone is behind", (HEADER, "double off = std::fabs(std::atan2(dy, dx) - heading);", "double off = std::fabs(std::atan2(dy, dx) - heading - Pi);")),
            ("the cone forgets the half turn", (HEADER, "if (off > Pi)\n            off = 2 * Pi - off;", "")),
            ("a tick is the whole damage", (HEADER, "return PeriodicStrike::TickPct(totalPct, PeriodicStrike::Ticks(seconds, tickSeconds));", "return totalPct;")),
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

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct", "initial"), value("", "damage_pct", "dot"),
                          value("", "dot_duration_seconds")], [175, 300, 360, 3])
        self.assertEqual(value("Corpse Bomb", "damage_pct"), 700)
        self.assertEqual(value("Acid Rain", "radius_yards"), 24)
        self.assertEqual([value("Lob Blob Bomb", "damage_pct"), value("Lob Blob Bomb", "dot_duration_seconds")], [600, 5])
        self.assertEqual([value("Slow Burn", "damage_pct"), value("Slow Burn", "dot_duration_seconds")], [720, 6])
        self.assertEqual([value("Kiss of Death", "damage_pct", "initial"), value("Kiss of Death", "damage_pct", "dot"),
                          value("Kiss of Death", "dot_duration_seconds")], [333, 400, 3])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("acid_cloud_impact_delay_seconds", "0.25", "SF_0"), ("acid_cloud_corpse_delay_seconds", "0.5", "SF_14"),
                                 ("acid_cloud_splash_delay_seconds", "0.6", "SF_16"), ("acid_cloud_impact_radius_yards", "12", "SF_35"),
                                 ("acid_cloud_pool_radius_yards", "6", "SF_6"), ("acid_cloud_tick_seconds", "0.333", "SF_19"),
                                 ("acid_cloud_max_pools", "3", "SF_10"), ("acid_cloud_slime_radius_yards", "9", "SF_22"),
                                 ("acid_cloud_max_slimes", "3", "SF_25"), ("acid_cloud_barf_range_yards", "30", "SF_30"),
                                 ("acid_cloud_barf_angle_degrees", "55", "SF_31"), ("acid_cloud_barf_delay_seconds", "0.25", "SF_32")):
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""))
                self.assertIn(source, rows[name]["notes"])
                self.assertIn(POWER, rows[name]["notes"])
                self.assertNotIn("placeholder", rows[name]["notes"].lower())

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'"(acid_cloud_[a-z_]+)"', text)), {n for n in tunables() if n.startswith("acid_cloud_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"], r["qualifier"]): r["origin"] for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for key, origin in ((("", "damage_pct", "initial"), "own"), (("Corpse Bomb", "damage_pct", ""), "own"), (("Corpse Bomb", "damage_pct", "dot"), "inherited"),
                            (("Acid Rain", "radius_yards", ""), "own"), (("Acid Rain", "damage_pct", "initial"), "inherited"),
                            (("Lob Blob Bomb", "damage_pct", ""), "own"), (("Lob Blob Bomb", "dot_duration_seconds", ""), "own"),
                            (("Lob Blob Bomb", "damage_pct", "initial"), "inherited"), (("Slow Burn", "damage_pct", ""), "own"),
                            (("Slow Burn", "dot_duration_seconds", ""), "own"), (("Slow Burn", "damage_pct", "initial"), "inherited"),
                            (("Kiss of Death", "damage_pct", "initial"), "own"), (("Kiss of Death", "damage_pct", "dot"), "own"),
                            (("Kiss of Death", "dot_duration_seconds", ""), "own"), (("", "dot_duration_seconds", ""), "own")):
            self.assertEqual(mapped[key], origin, key)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract(POWER))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        def ruled(n, which=1):
            return float(str(sf[n]).split("?")[1].split(":")[0 if which == 1 else 1].strip(" ()"))

        self.assertAlmostEqual(number(11) * 100, value("", "damage_pct", "initial"))
        self.assertAlmostEqual(number(34) * number(17) * 100, value("", "damage_pct", "dot"))
        self.assertAlmostEqual(number(17), value("", "dot_duration_seconds"))
        self.assertAlmostEqual(number(11) * ruled(13) * 100, value("Corpse Bomb", "damage_pct"), places=0)
        self.assertAlmostEqual(number(35) + ruled(36), value("Acid Rain", "radius_yards"))
        self.assertAlmostEqual(number(34) * number(20) * 100, value("Lob Blob Bomb", "damage_pct"))
        self.assertAlmostEqual(number(20), value("Lob Blob Bomb", "dot_duration_seconds"))
        self.assertAlmostEqual(number(34) * (number(17) + ruled(18)) * 100, value("Slow Burn", "damage_pct"))
        self.assertAlmostEqual(number(17) + ruled(18), value("Slow Burn", "dot_duration_seconds"))
        self.assertAlmostEqual(number(11) * ruled(33) * 100, value("Kiss of Death", "damage_pct", "initial"), places=0)
        self.assertAlmostEqual(number(34) * ruled(33) * number(17) * 100, value("Kiss of Death", "damage_pct", "dot"), places=0)
        for name, n in (("acid_cloud_impact_delay_seconds", 0), ("acid_cloud_corpse_delay_seconds", 14), ("acid_cloud_splash_delay_seconds", 16),
                        ("acid_cloud_impact_radius_yards", 35), ("acid_cloud_pool_radius_yards", 6), ("acid_cloud_tick_seconds", 19),
                        ("acid_cloud_max_pools", 10), ("acid_cloud_slime_radius_yards", 22), ("acid_cloud_max_slimes", 25),
                        ("acid_cloud_barf_range_yards", 30), ("acid_cloud_barf_angle_degrees", 31), ("acid_cloud_barf_delay_seconds", 32)):
            self.assertAlmostEqual(number(n), tune(name), msg=name)
        self.assertEqual(str(sf[7]).strip(), "SF_19")  # the total tick rate is the base one


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))
        self.resolve = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams_and_the_engine_calls_the_ground_seam(self):
        self.assertEqual(self.dispatch.count("if (auto cloud = AcidCloud::BasePct(spellId)) return cloud;"), 1)
        self.assertEqual(self.dispatch.count("AcidCloud::Ground(player, spellId, center);"), 1)
        self.assertIn("void Ground(Player* player, std::uint32_t spellId, Position const& center) {", self.dispatch)
        self.assertEqual(self.resolve.count("WitchDoctor::Ground(player, shell.spellId, center);"), 1)
        self.assertLess(self.resolve.index("DemonHunter::Ground(player, shell.spellId, center);"),
                        self.resolve.index("WitchDoctor::Ground(player, shell.spellId, center);"))

    def test_the_cast_hits_nothing(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_the_impact_is_a_burst_of_the_band_the_rune_reaches(self):
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn('Burst(player, spellId, center, -1.0, inner, pct)', ground)
        self.assertIn('Burst(player, spellId, center, inner, Numbers::Num(spellId, "radius_yards"), pct)', ground)
        self.assertIn('Tune("acid_cloud_splash_delay_seconds")', ground)
        self.assertIn("ImpactDelaySeconds(rune,", ground)
        self.assertIn("Pool(player, spellId, rune, center, delay);", ground)
        self.assertIn("if (rune == Rune::KissOfDeath) { Spit(player, spellId, rune, center); return; }", ground)
        burst = self.code[self.code.index("void Burst("):self.code.index("void Pool(")]
        self.assertIn("InBand(enemy->GetExactDist(&center), inner, outer)", burst)
        self.assertIn("ImpactTakesRuneElement(rune) ? spellId : BaseId(Skill)", burst)
        impact = self.code[self.code.index("double ImpactPct("):self.code.index("double PoolPct(")]
        self.assertIn('rune == Rune::CorpseBomb ? Numbers::Num(spellId, "damage_pct") : Numbers::Num(spellId, "damage_pct", "initial")', impact)

    def test_the_pool_is_a_periodic_device_of_the_shared_piece(self):
        pool = self.code[self.code.index("void Pool("):self.code.index("void CloudTick(")]
        self.assertIn("pool.spec.mode = GroundDevice::Mode::Periodic;", pool)
        self.assertIn("pool.spec.armMs = delaySeconds * 1000.0;", pool)
        self.assertIn("pool.spec.lifetimeMs = (delaySeconds + seconds) * 1000.0;", pool)
        self.assertIn('slime ? "acid_cloud_slime_radius_yards" : "acid_cloud_pool_radius_yards"', pool)
        self.assertIn('slime ? "acid_cloud_max_slimes" : "acid_cloud_max_pools"', pool)
        self.assertIn('TickPct(PoolPct(spellId, rune), seconds, tick)', pool)
        self.assertIn("GroundDevice::Place(player, pool, center);", pool)
        total = self.code[self.code.index("double PoolPct("):self.code.index("std::uint32_t PoolRecord(")]
        self.assertIn('rune == Rune::LobBlobBomb || rune == Rune::SlowBurn ? Numbers::Num(spellId, "damage_pct") : Numbers::Num(spellId, "damage_pct", "dot")', total)

    def test_kiss_of_deaths_cone_and_cloud(self):
        spit = self.code[self.code.index("void Spit("):self.code.index("} // namespace\n") if "} // namespace\n" in self.code else None]
        self.assertIn("from.GetAngle(center.GetPositionX(), center.GetPositionY())", spit)
        self.assertIn("InCone(", spit)
        self.assertIn('Tune("acid_cloud_barf_range_yards")', spit)
        self.assertIn('Tune("acid_cloud_barf_angle_degrees")', spit)
        self.assertIn("CloudTick(player, spellId, from, heading, ticks, each)", spit)
        tick = self.code[self.code.index("void CloudTick("):self.code.index("void Spit(")]
        self.assertIn("if (!left || !player->IsAlive() || !player->IsInWorld()) return;", tick)
        self.assertIn("CloudTick(player, spellId, from, heading, left - 1, pct)", tick)


if __name__ == "__main__":
    unittest.main()
