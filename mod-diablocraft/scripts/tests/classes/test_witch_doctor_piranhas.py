"""Witch Doctor Piranhas and its five runes (src/classes/witch_doctor/dc_witch_doctor_piranhas.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_piranhas/harness.cpp compiles the real dc_witch_doctor_piranhas.h with
    the sheets' own rune names and numbers: each rune name is its rune; which part takes the rune's element; the pool's ticks make
    its damage (a tornado that stands half as long deals half as much); the pool's reach, Zombie Piranhas' farther; which points the
    wave passes over and when it reaches them; what the tornado sucks in. Mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Piranhas (or
    the rune that states it) the engine can read; every tunable is a row of data/tunables/witchdoctor.csv; the numbers equal the
    decoded Power/Witchdoctor_Piranhas.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams; the cast hits nothing; the pool is a periodic device of the shared piece that
    hurts, amplifies the damage taken and (Frozen Piranhas) chills; the Bogadile bites and stuns by `StunFactor`; the Piranhado pulls
    from a device of its own; Wave of Mutilation strikes each enemy it passes when it reaches them.

What it does not prove: anything on a running server. The pool, the bite, the tornado and the wave are
docs/test-diablocraft-vxrcu.27.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_piranhas.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_piranhas.h"
SOURCES = [HEADER, "tests/witch_doctor_piranhas/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_piranhas.cpp"
SKILL = "Piranhas"
POWER = "Power/Witchdoctor_Piranhas.pow"
RUNES = ["Bogadile", "Zombie Piranhas", "Piranhado", "Wave of Mutilation", "Frozen Piranhas"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_piranhas/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("piranhas_pool_radius_yards"), tune("piranhas_leap_radius_yards"), tune("piranhas_tick_seconds"),
                         value("", "damage_pct"), value("", "dot_duration_seconds"), value("Piranhado", "duration_seconds"),
                         tune("piranhas_wave_offset_yards"), tune("piranhas_wave_length_yards"), tune("piranhas_wave_yards_per_second"),
                         tune("piranhas_wave_distance_yards"), tune("piranhas_wave_width_yards"), tune("piranhas_vacuum_radius_yards")]
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
            ("two runes share a name", (HEADER, 'if (name == "Zombie Piranhas")\n            return Rune::ZombiePiranhas;',
                                        'if (name == "Zombie Piranhas")\n            return Rune::Bogadile;')),
            ("the Bogadile's pool takes the bite's element", (HEADER, "return rune != Rune::Bogadile;", "return true;")),
            ("a tick is the whole damage", (HEADER, "return totalSeconds > 0 ? totalPct / totalSeconds * tickSeconds : 0.0;", "return totalPct;")),
            ("a tick ignores the pool's seconds", (HEADER, "totalPct / totalSeconds * tickSeconds", "totalPct * tickSeconds")),
            ("Zombie Piranhas do not leap", (HEADER, "return rune == Rune::ZombiePiranhas ? leap : pool;", "return pool;")),
            ("every rune leaps", (HEADER, "return rune == Rune::ZombiePiranhas ? leap : pool;", "return leap;")),
            ("the wave covers what is behind", (HEADER, "return ahead >= 0 && ahead <= distance", "return ahead <= distance")),
            ("the wave has no distance", (HEADER, "return ahead >= 0 && ahead <= distance", "return ahead >= 0")),
            ("the wave has no width", (HEADER, "&& std::fabs(across) <= width / 2;", ";")),
            ("the wave is twice as wide", (HEADER, "std::fabs(across) <= width / 2;", "std::fabs(across) <= width;")),
            ("the wave hits everything at once", (HEADER, "yardsPerSecond > 0 && ahead > lead ?", "false ?")),
            ("the wave starts at the Witch Doctor", (HEADER, "double const lead = offset + length;", "double const lead = 0;")),
            ("the wave is as slow as its yards", (HEADER, "(ahead - lead) / yardsPerSecond * 1000.0", "(ahead - lead) * 1000.0")),
            ("the tornado sucks in everything", (HEADER, "return distance <= vacuumRadius;", "return true;")),
            ("the tornado misses its edge", (HEADER, "return distance <= vacuumRadius;", "return distance < vacuumRadius;")),
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
        self.assertEqual([value("", "cost_resource"), value("", "cooldown_seconds"), value("", "damage_pct"), value("", "dot_duration_seconds"),
                          value("", "damage_taken_pct")], [250, 8, 400, 8, 15])
        self.assertEqual(value("Bogadile", "damage_pct"), 1100)
        self.assertEqual([value("Piranhado", "duration_seconds"), value("Piranhado", "cooldown_seconds")], [4, 16])
        self.assertEqual([value("Wave of Mutilation", "damage_pct"), value("Wave of Mutilation", "damage_taken_pct"),
                          value("Wave of Mutilation", "duration_seconds")], [475, 15, 8])
        self.assertEqual([value("Frozen Piranhas", "damage_pct"), value("Frozen Piranhas", "dot_duration_seconds")], [400, 8])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("piranhas_pool_radius_yards", "13", "SF_0"), ("piranhas_tick_seconds", "0.4", "SF_2"),
                                 ("piranhas_debuff_seconds", "1", "SF_5"), ("piranhas_bogadile_delay_seconds", "0.5", "SF_6"),
                                 ("piranhas_bogadile_radius_yards", "4", "SF_7"), ("piranhas_bogadile_stun_seconds", "3", "SF_27"),
                                 ("piranhas_leap_radius_yards", "32", "SF_9"), ("piranhas_vacuum_radius_yards", "16", "SF_12"),
                                 ("piranhas_wave_offset_yards", "2", "SF_15"), ("piranhas_wave_yards_per_second", "30", "SF_16"),
                                 ("piranhas_wave_distance_yards", "50", "SF_17"), ("piranhas_wave_length_yards", "20", "SF_18"),
                                 ("piranhas_wave_width_yards", "36", "SF_19"), ("piranhas_frozen_chill_pct", "100", "SF_28")):
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""))
                self.assertIn(source, rows[name]["notes"])
                self.assertIn(POWER, rows[name]["notes"])
                self.assertNotIn("placeholder", rows[name]["notes"].lower())
        pull = rows["piranhas_pull_pulse_seconds"]
        self.assertEqual((pull["d3_value"], pull["value"]), ("", "1"))
        self.assertIn("placeholder", pull["notes"].lower())

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'"(piranhas_[a-z_]+)"', text)), {n for n in tunables() if n.startswith("piranhas_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([^"]*"([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r["origin"] for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for key, origin in ((("", "damage_pct"), "own"), (("", "dot_duration_seconds"), "own"), (("", "damage_taken_pct"), "own"),
                            (("Bogadile", "damage_pct"), "own"), (("Bogadile", "damage_taken_pct"), "inherited"),
                            (("Piranhado", "duration_seconds"), "own"), (("Piranhado", "damage_pct"), "inherited"),
                            (("Piranhado", "dot_duration_seconds"), "inherited"), (("Wave of Mutilation", "damage_pct"), "own"),
                            (("Wave of Mutilation", "damage_taken_pct"), "own"), (("Wave of Mutilation", "duration_seconds"), "own"),
                            (("Frozen Piranhas", "damage_pct"), "own"), (("Frozen Piranhas", "dot_duration_seconds"), "own"),
                            (("Zombie Piranhas", "damage_taken_pct"), "inherited")):
            self.assertEqual(mapped[key], origin, key)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract(POWER))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(29) * number(25) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(25), value("", "dot_duration_seconds"))
        self.assertAlmostEqual(number(4) * 100, value("", "damage_taken_pct"))
        self.assertAlmostEqual(number(23), value("", "cooldown_seconds"))
        self.assertAlmostEqual(number(8) * 100, value("Bogadile", "damage_pct"))
        self.assertAlmostEqual(number(26), value("Piranhado", "duration_seconds"))
        self.assertAlmostEqual(16.0, value("Piranhado", "cooldown_seconds"))
        self.assertEqual(str(sf[24]).replace(" ", ""), "Rune_C?16:SF_23")
        self.assertAlmostEqual(number(30) * 100, value("Wave of Mutilation", "damage_pct"))
        self.assertAlmostEqual(number(20), value("Wave of Mutilation", "duration_seconds"))
        self.assertAlmostEqual(number(29) * number(25) * 100, value("Frozen Piranhas", "damage_pct"))
        for name, n in (("piranhas_pool_radius_yards", 0), ("piranhas_tick_seconds", 2), ("piranhas_debuff_seconds", 5), ("piranhas_bogadile_delay_seconds", 6),
                        ("piranhas_bogadile_radius_yards", 7), ("piranhas_bogadile_stun_seconds", 27), ("piranhas_leap_radius_yards", 9),
                        ("piranhas_vacuum_radius_yards", 12), ("piranhas_wave_offset_yards", 15), ("piranhas_wave_distance_yards", 17),
                        ("piranhas_wave_length_yards", 18), ("piranhas_wave_width_yards", 19)):
            self.assertAlmostEqual(number(n), tune(name), msg=name)
        self.assertAlmostEqual(number(16) * 60, tune("piranhas_wave_yards_per_second"))
        self.assertAlmostEqual(number(28) * 100, tune("piranhas_frozen_chill_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto pool = Piranhas::BasePct(spellId)) return pool;"), 1)
        self.assertEqual(self.dispatch.count("Piranhas::Ground(player, spellId, center);"), 1)

    def test_the_cast_hits_nothing(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_the_pool_hurts_amplifies_and_chills(self):
        pool = self.code[self.code.index("void Pool("):self.code.index("void Crash(")]
        self.assertIn("pool.spec.mode = GroundDevice::Mode::Periodic;", pool)
        self.assertIn("rune == Rune::Piranhado ? Numbers::Num(spellId, \"duration_seconds\") : Numbers::Num(spellId, \"dot_duration_seconds\")", pool)
        self.assertIn('Numbers::Num(PoolTakesRuneElement(rune) ? spellId : BaseId(Skill), "damage_pct")', pool)
        self.assertIn('PoolReach(rune, Tune("piranhas_pool_radius_yards"), Tune("piranhas_leap_radius_yards"))', pool)
        self.assertIn("Combat::Strike(owner, enemy, striker, pct);", pool)
        self.assertIn('EnemyEffects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_taken_pct"), seconds);', pool)
        self.assertIn('Slow(owner, enemy, Tune("piranhas_frozen_chill_pct"), seconds);', pool)
        self.assertIn("if (rune == Rune::Piranhado) Vacuum(player, spellId, center, life);", pool)
        self.assertIn("if (rune == Rune::Bogadile) Bite(player, spellId, center);", pool)

    def test_the_bite_the_tornado_and_the_wave(self):
        bite = self.code[self.code.index("void Bite("):self.code.index("void Vacuum(")]
        self.assertIn('Combat::Enemies(player, spellId, center, Tune("piranhas_bogadile_radius_yards"))', bite)
        self.assertIn('Numbers::Num(spellId, "damage_pct")', bite)
        self.assertIn('Stun(player, enemy, Tune("piranhas_bogadile_stun_seconds") * ItemPowers::StunFactor(player));', bite)
        vacuum = self.code[self.code.index("void Vacuum("):self.code.index("void Pool(")]
        self.assertIn('pull.spec.intervalMs = Tune("piranhas_pull_pulse_seconds") * 1000.0;', vacuum)
        self.assertIn('pull.spec.radiusYards = Tune("piranhas_vacuum_radius_yards");', vacuum)
        self.assertIn("Abilities::Pull(enemy, center);", vacuum)
        crash = self.code[self.code.index("void Crash("):self.code.index("} // namespace\n") if "} // namespace\n" in self.code else None]
        self.assertIn("WaveCovers(ahead, Across(dx, dy, heading), distance, width)", crash)
        self.assertIn('WaveReachesMs(ahead, Tune("piranhas_wave_offset_yards"), Tune("piranhas_wave_length_yards"), Tune("piranhas_wave_yards_per_second"))', crash)
        self.assertIn('EnemyEffects::Taken(hit, spellId, Numbers::Num(spellId, "damage_taken_pct"), Numbers::Num(spellId, "duration_seconds"));', crash)
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn("if (rune == Rune::WaveOfMutilation) Crash(player, spellId, center); else Pool(player, spellId, rune, center);", ground)


if __name__ == "__main__":
    unittest.main()
