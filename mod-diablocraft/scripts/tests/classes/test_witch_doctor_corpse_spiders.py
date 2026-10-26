"""Witch Doctor Corpse Spiders and its five runes (src/classes/witch_doctor/dc_witch_doctor_corpse_spiders.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_corpse_spiders/harness.cpp compiles the real dc_witch_doctor_corpse_spiders.h and
    the shared damage-over-time arithmetic with the sheets' own rune names and numbers: each rune name is its rune; the bites together
    deal the sheet's total; every bite falls evenly inside a spider's life; the queen's pulses make her total, the first an interval
    after the jar and the last at her end; Medusa Spiders' chance edge to edge; the pick of an enemy. Eight mutations planted in a scratch
    copy must each make it fail.
  * **The record needs no change.** The cast is the engine's ground throw (a `ground_area` row of skill_targeting.csv); it is free, the jar's
    own hit is the file's impact scalar, each rune's school is the record's.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Corpse Spiders (or the rune
    that states it); every tunable is a row of data/tunables/witchdoctor.csv, one marked a placeholder; the numbers equal the decoded
    Power/Witchdoctor_CorpseSpider.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Ground`); the engine calls `Ground`; the spiders' bites and the queen's pulses
    are scheduled on the player's own queue; a later queen takes the place of an earlier.

What it does not prove: anything on a running server. The jar, the spiders, the queen, the Mana and the slow are
docs/test-diablocraft-vxrcu.9.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_corpse_spiders.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_corpse_spiders.h"
PICK = "src/classes/witch_doctor/dc_witch_doctor_pick.h"
PERIODIC = "src/combat/dc_periodic_strike.h"
SOURCES = [HEADER, PICK, PERIODIC, "tests/witch_doctor_corpse_spiders/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_corpse_spiders.cpp"
SKILL = "Corpse Spiders"
RUNES = ["Blazing Spiders", "Spider Queen", "Leaping Spiders", "Widowmakers", "Medusa Spiders"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_corpse_spiders/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "damage_pct"), value("", "spawn_count"), tune("corpse_spiders_hits_per_spider"), tune("corpse_spiders_lifetime_seconds"),
                         value("Spider Queen", "damage_pct"), value("Spider Queen", "dot_duration_seconds"), tune("corpse_spiders_queen_pulse_seconds"),
                         value("Medusa Spiders", "proc_chance_pct")]
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
            ("two runes share a name", (HEADER, 'if (name == "Spider Queen")\n            return Rune::SpiderQueen;',
                                        'if (name == "Spider Queen")\n            return Rune::BlazingSpiders;')),
            ("a bite is a spider's whole share", (HEADER, "totalPct / (double(spiders) * double(bites))", "totalPct / double(spiders)")),
            ("a bite is the whole total", (HEADER, "totalPct / (double(spiders) * double(bites))", "totalPct")),
            ("the bites fall at the end of the life", (HEADER, "double(bites + 1) +", "double(bites) +")),
            ("the first pulse is at the jar", (HEADER, "* 1000.0 * (index + 1) + 0.5", "* 1000.0 * index + 0.5")),
            ("a roll at the chance slows", (HEADER, "return roll < chancePct;", "return roll <= chancePct;")),
            ("every roll picks the first enemy", (PICK, "std::min(count - 1, std::size_t(std::max(0.0, roll) * double(count)))", "0")),
            ("a pulse is the queen's whole total", (PERIODIC, "return ticks ? totalPct / ticks : 0.0;", "return totalPct;")),
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

    def test_the_record_is_the_engines_ground_throw(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual(rows[SKILL]["target_type"], "ground_area")
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "spawn_count"), value("", "damage_pct")], [4, 576])
        self.assertEqual(value("Blazing Spiders", "gain_resource"), 3)
        self.assertEqual([value("Spider Queen", "damage_pct"), value("Spider Queen", "dot_duration_seconds")], [2625, 15])
        self.assertEqual([value("Leaping Spiders", "radius_yards"), value("Leaping Spiders", "damage_pct")], [25, 645])
        self.assertEqual(value("Widowmakers", "damage_pct"), 700)
        self.assertEqual([value("Medusa Spiders", "proc_chance_pct"), value("Medusa Spiders", "slow_pct")], [100, 60])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("corpse_spiders_impact_pct", "1", "SF_1"), ("corpse_spiders_lifetime_seconds", "4", "SF_3"),
                                 ("corpse_spiders_hits_per_spider", "3", "SF_24"), ("corpse_spiders_slow_seconds", "1.5", "SF_5"),
                                 ("corpse_spiders_queen_area_yards", "10", "SF_13"), ("corpse_spiders_queen_pulse_seconds", "0.25", "SF_19")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/Witchdoctor_CorpseSpider.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_the_spiders_reach_is_alexs_answer(self):
        row = tunables()["corpse_spiders_reach_yards"]
        # The designer's column: the power file holds no search radius, and card q-1021-102 answered 10 yards.
        self.assertEqual((row["d3_value"], row["value"]), ("", "10"))
        self.assertIn("q-1021-102", row["notes"])
        self.assertNotIn("placeholder", row["notes"].lower())

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("corpse_spiders_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "spawn_count", "own"), ("", "damage_pct", "own"), ("Blazing Spiders", "spawn_count", "inherited"),
                                    ("Blazing Spiders", "damage_pct", "inherited"), ("Spider Queen", "damage_pct", "own"),
                                    ("Spider Queen", "dot_duration_seconds", "own"), ("Leaping Spiders", "radius_yards", "own"),
                                    ("Leaping Spiders", "damage_pct", "own"), ("Widowmakers", "damage_pct", "own"),
                                    ("Medusa Spiders", "proc_chance_pct", "own"), ("Medusa Spiders", "slow_pct", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_CorpseSpider.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(0), value("", "spawn_count"))
        self.assertAlmostEqual((number(9) + number(18) / 2) * number(0) * number(24) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(14) * number(10) * 100, value("Spider Queen", "damage_pct"))
        self.assertAlmostEqual(number(10), value("Spider Queen", "dot_duration_seconds"))
        self.assertAlmostEqual(number(21), value("Leaping Spiders", "radius_yards"))
        self.assertAlmostEqual(float(str(sf[22]).split("?")[1].split(":")[0]), 1.12)
        self.assertAlmostEqual(number(11) * 100, value("Medusa Spiders", "proc_chance_pct"))
        self.assertAlmostEqual(number(4) * 100, value("Medusa Spiders", "slow_pct"))
        self.assertAlmostEqual(number(1) * 100, tune("corpse_spiders_impact_pct"))
        self.assertAlmostEqual(number(3), tune("corpse_spiders_lifetime_seconds"))
        self.assertAlmostEqual(number(24), tune("corpse_spiders_hits_per_spider"))
        self.assertAlmostEqual(number(5), tune("corpse_spiders_slow_seconds"))
        self.assertAlmostEqual(number(13), tune("corpse_spiders_queen_area_yards"))
        self.assertAlmostEqual(number(19), tune("corpse_spiders_queen_pulse_seconds"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))
        self.resolve = (MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")

    def test_the_dispatch_answers_the_seams_and_the_engine_calls_ground(self):
        self.assertEqual(self.dispatch.count("if (auto jar = CorpseSpiders::BasePct(spellId)) return jar;"), 1)
        self.assertEqual(self.dispatch.count("CorpseSpiders::Ground(player, spellId, center);"), 1)
        self.assertEqual(self.resolve.count("WitchDoctor::Ground(player, shell.spellId, center);"), 1)
        self.assertLess(self.resolve.index("DemonHunter::Ground(player, shell.spellId, center);"), self.resolve.index("WitchDoctor::Ground(player, shell.spellId, center);"))

    def test_the_jars_hit_is_the_impact_scalar(self):
        self.assertIn('Is(spellId) ? std::optional<double>(Tune("corpse_spiders_impact_pct")) : std::nullopt', self.code)

    def test_the_spiders_bite_inside_their_life_at_random_enemies_near_the_jar(self):
        swarm = self.code[self.code.index("void Swarm("):self.code.index("void Queen(")]
        self.assertIn('unsigned(Numbers::Num(spellId, "spawn_count")), bites = unsigned(Tune("corpse_spiders_hits_per_spider"))', swarm)
        self.assertIn('BiteShare(Numbers::Num(spellId, "damage_pct"), spiders, bites)', swarm)
        self.assertIn('RuneAt(spellId) == Rune::LeapingSpiders ? Numbers::Num(spellId, "radius_yards") : Tune("corpse_spiders_reach_yards")', swarm)
        self.assertIn('BiteMs(bite, bites, Tune("corpse_spiders_lifetime_seconds"))', swarm)
        bite = self.code[self.code.index("void Bite("):self.code.index("void Swarm(")]
        self.assertIn("enemies[PickAt(frand(0.0f, 1.0f), enemies.size())]", bite)
        self.assertIn('Slows(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct"))', bite)
        self.assertIn('Slow(player, target, Numbers::Num(spellId, "slow_pct"), Tune("corpse_spiders_slow_seconds"));', bite)
        self.assertIn("Combat::Connected(player, spellId, 1);", bite)

    def test_the_queen_pulses_and_a_later_queen_takes_her_place(self):
        queen = self.code[self.code.index("void Queen("):self.code.index("} // namespace")]
        self.assertIn("queens[player->GetGUID().GetRawValue()] = stamp;", queen)
        self.assertIn("found->second != stamp", queen)
        self.assertIn('PeriodicStrike::Ticks(Numbers::Num(spellId, "dot_duration_seconds"), Tune("corpse_spiders_queen_pulse_seconds"))', queen)
        self.assertIn('PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), pulses)', queen)
        self.assertIn('Tune("corpse_spiders_queen_area_yards")', queen)
        self.assertIn("Combat::Strike(player, enemy, spellId, pct, true);", queen)


if __name__ == "__main__":
    unittest.main()
