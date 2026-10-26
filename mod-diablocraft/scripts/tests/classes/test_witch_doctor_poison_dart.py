"""Witch Doctor Poison Dart and its five runes (src/classes/witch_doctor/dc_witch_doctor_poison_dart.h and .cpp, and the shared
src/combat/dc_periodic_strike.h).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_poison_dart/harness.cpp compiles the real dc_witch_doctor_poison_dart.h and the
    shared damage-over-time arithmetic with the sheets' own rune names and numbers: each rune name is its rune; the poison's and the
    fire's ticks make their damage; Splinters' darts leave the delay apart; Snake to the Face's chance edge to edge. Five mutations planted in
    a scratch copy must each make it fail.
  * **The record needs no change.** The cast is the engine's single-enemy shot (a `single_enemy` row of skill_targeting.csv); it is free,
    each rune's school and Spined Dart's Mana (the class's Connected seam, built with 2b) are the record's and the sheet's.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Poison Dart (or the rune
    that states it); every tunable is a row of data/tunables/witchdoctor.csv; the numbers equal the decoded
    Power/Witchdoctor_PoisonDart.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Landed`, `Cast`); the engine calls them; the shot's hit is the skill's `hit`
    number; every dart but Splinters' leaves the poison; the runes' parts.

What it does not prove: anything on a running server. The darts, the poison, the fire, the slow and the stun are
docs/test-diablocraft-vxrcu.8.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_poison_dart.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_poison_dart.h"
PERIODIC = "src/combat/dc_periodic_strike.h"
SOURCES = [HEADER, PERIODIC, "tests/witch_doctor_poison_dart/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_poison_dart.cpp"
SKILL = "Poison Dart"
RUNES = ["Flaming Dart", "Splinters", "Numbing Dart", "Spined Dart", "Snake to the Face"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_poison_dart/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "damage_pct", "dot"), value("", "dot_duration_seconds"), value("Flaming Dart", "damage_pct"),
                         value("Flaming Dart", "dot_duration_seconds"), tune("poison_dart_tick_seconds"), value("Splinters", "projectile_count"),
                         tune("poison_dart_shot_delay_seconds"), value("Snake to the Face", "proc_chance_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 10, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Splinters")\n            return Rune::Splinters;',
                                        'if (name == "Splinters")\n            return Rune::FlamingDart;')),
            ("the darts leave together", (HEADER, "* 1000.0 * index + 0.5", "* 1000.0 + 0.5")),
            ("a roll at the chance stuns", (HEADER, "return roll < chancePct;", "return roll <= chancePct;")),
            ("a tick is the whole damage", (PERIODIC, "return ticks ? totalPct / ticks : 0.0;", "return totalPct;")),
            ("a tick is lost", (PERIODIC, "std::floor(seconds / tickSeconds + 1e-9)", "std::floor(seconds / tickSeconds - 0.5)")),
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

    def test_the_record_is_the_engines_single_enemy_shot(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual(rows[SKILL]["target_type"], "single_enemy")
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "damage_pct", "hit"), value("", "damage_pct", "dot"), value("", "dot_duration_seconds")], [185, 40, 2])
        self.assertEqual([value("Flaming Dart", "damage_pct"), value("Flaming Dart", "dot_duration_seconds")], [565, 4])
        self.assertEqual([value("Splinters", "projectile_count"), value("Splinters", "damage_pct")], [3, 110])
        self.assertEqual([value("Numbing Dart", "slow_pct"), value("Numbing Dart", "slow_duration_seconds")], [60, 2])
        self.assertEqual(value("Spined Dart", "gain_resource"), 50)
        self.assertEqual([value("Snake to the Face", "proc_chance_pct"), value("Snake to the Face", "stun_duration_seconds")], [35, 1.5])

    def test_the_shot_delay_is_the_power_files(self):
        row = tunables()["poison_dart_shot_delay_seconds"]
        self.assertEqual((row["d3_value"], row["value"]), ("0.15", ""))
        self.assertIn("SF_17", row["notes"])
        self.assertIn("Power/Witchdoctor_PoisonDart.pow", row["notes"])
        self.assertNotIn("placeholder", row["notes"].lower())

    def test_the_tick_is_alexs_standing_default(self):
        row = tunables()["poison_dart_tick_seconds"]
        self.assertEqual((row["d3_value"], row["value"]), ("", "0.5"))
        self.assertIn("standing default", row["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("poison_dart_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, qualifier, origin in (("", "damage_pct", "hit", "own"), ("", "damage_pct", "dot", "own"), ("", "dot_duration_seconds", "", "own"),
                                               ("Flaming Dart", "damage_pct", "dot", "inherited"), ("Flaming Dart", "damage_pct", "", "own"),
                                               ("Splinters", "damage_pct", "", "own"), ("Splinters", "projectile_count", "", "own"),
                                               ("Numbing Dart", "slow_pct", "", "own"), ("Snake to the Face", "proc_chance_pct", "", "own")):
            self.assertEqual(mapped[(rune, token, qualifier)]["origin"], origin, (rune, token, qualifier))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_PoisonDart.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(14) * 100, value("", "damage_pct", "hit"))
        self.assertAlmostEqual(number(16) * 100, value("", "damage_pct", "dot"))
        self.assertAlmostEqual(number(9), value("", "dot_duration_seconds"))
        self.assertAlmostEqual(number(2) * 100, value("Flaming Dart", "damage_pct"))
        self.assertAlmostEqual(number(3), value("Flaming Dart", "dot_duration_seconds"))
        self.assertAlmostEqual(number(4), value("Splinters", "projectile_count"))
        self.assertAlmostEqual(number(13) * 100, value("Splinters", "damage_pct"))
        self.assertAlmostEqual(number(5) * 100, value("Numbing Dart", "slow_pct"))
        self.assertAlmostEqual(number(6), value("Numbing Dart", "slow_duration_seconds"))
        self.assertAlmostEqual(number(10), value("Spined Dart", "gain_resource"))
        self.assertAlmostEqual(number(11) * 100, value("Snake to the Face", "proc_chance_pct"))
        self.assertAlmostEqual(number(8), value("Snake to the Face", "stun_duration_seconds"))
        self.assertAlmostEqual(number(17), tune("poison_dart_shot_delay_seconds"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))
        self.resolve = (MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")
        self.combat = (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8")

    def test_the_dispatch_answers_the_seams(self):
        for call in ("if (auto dart = PoisonDart::BasePct(spellId)) return dart;", "PoisonDart::Landed(player, target, spellId);", "PoisonDart::Cast(player, spellId, targets);"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_engine_calls_them(self):
        self.assertIn("else if (auto witchDoctor = WitchDoctor::BasePct(ability.id))", self.combat)
        self.assertLess(self.combat.index("DemonHunter::BasePct(ability.id)"), self.combat.index("WitchDoctor::BasePct(ability.id)"))
        self.assertLess(self.combat.index("WitchDoctor::BasePct(ability.id)"), self.combat.index("DamageWaits(ability.id)"))
        self.assertEqual(self.resolve.count("WitchDoctor::Landed(player, target, shell.spellId);"), 1)
        self.assertEqual(self.resolve.count("WitchDoctor::Landed(player, target, spellId);"), 1)
        self.assertEqual(self.resolve.count("WitchDoctor::Cast(player, shell.spellId, targets);"), 1)
        self.assertLess(self.resolve.index("DemonHunter::Cast(player, shell.spellId, targets);"), self.resolve.index("WitchDoctor::Cast(player, shell.spellId, targets);"))

    def test_the_shots_hit_is_the_skills_hit_number_and_splinters_darts_the_runes(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn('RuneAt(spellId) == Rune::Splinters ? Numbers::Num(spellId, "damage_pct") : Numbers::Num(BaseId(Skill), "damage_pct", "hit")', base)

    def test_splinters_other_darts_follow_at_the_shot_delay(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn("RuneAt(spellId) != Rune::Splinters", cast)
        self.assertIn("index = 1", cast)
        self.assertIn('unsigned(Numbers::Num(spellId, "projectile_count"))', cast)
        self.assertIn('DartDelayMs(index, Tune("poison_dart_shot_delay_seconds"))', cast)
        self.assertIn('Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct"));', cast)

    def test_every_dart_but_splinters_leaves_the_poison_and_the_runes_part(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("if (rune == Rune::Splinters) return;", landed)
        self.assertIn('Numbers::Num(spellId, "damage_pct", "dot"), Numbers::Num(BaseId(Skill), "dot_duration_seconds")', landed)
        self.assertIn('Tune("poison_dart_tick_seconds"));', landed)
        self.assertIn('Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "dot_duration_seconds"), Tune("poison_dart_tick_seconds"), 1);', landed)
        self.assertIn('Slow(player, target, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "slow_duration_seconds"));', landed)
        self.assertIn('Stuns(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct"))', landed)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', landed)


if __name__ == "__main__":
    unittest.main()
