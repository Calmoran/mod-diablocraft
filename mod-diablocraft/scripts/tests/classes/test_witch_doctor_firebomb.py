"""Witch Doctor Firebomb and its five runes (src/classes/witch_doctor/dc_witch_doctor_firebomb.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_firebomb/harness.cpp compiles the real dc_witch_doctor_firebomb.h and the shared
    damage-over-time arithmetic with the sheets' own rune names and numbers: each rune name is its rune; the skull bounces to the nearest enemy
    not yet hit within reach; Flash Fire's bounces each take the reduction off the base; the oldest Pyrogeists give way; the spews and the
    pool's ticks make their totals. Ten mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The cast is the engine's single-enemy throw (a `single_enemy` row of skill_targeting.csv, 45 yards): it is
    free, the hit on the enemy aimed at and each rune's school are the record's; the blast round it is built here.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Firebomb (or the rune
    that states it); every tunable is a row of data/tunables/witchdoctor.csv; the numbers equal the decoded Power/Witchdoctor_Firebomb.pow
    (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Cast`); the explosion is the skill's number for every rune; the blast round the
    enemy, Ghost Bomb's larger one, the bounces, the pool, the columns and Flash Fire's chain are scheduled on the player's own queue.

What it does not prove: anything on a running server. The explosion, the bounces, the pool, the columns and the chain are
docs/test-diablocraft-vxrcu.11.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_firebomb.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_firebomb.h"
PERIODIC = "src/combat/dc_periodic_strike.h"
SOURCES = [HEADER, PERIODIC, "tests/witch_doctor_firebomb/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_firebomb.cpp"
SKILL = "Firebomb"
RUNES = ["Ghost Bomb", "Roll the Bones", "Fire Pit", "Pyrogeist", "Flash Fire"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_firebomb/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "damage_pct"), value("Flash Fire", "damage_dealt_reduction_pct"), value("Flash Fire", "target_count"),
                         tune("firebomb_flash_delay_seconds"), value("Pyrogeist", "damage_pct"), value("Pyrogeist", "dot_duration_seconds"),
                         tune("firebomb_pyrogeist_tick_seconds"), value("Pyrogeist", "max_count"), value("Fire Pit", "damage_pct"),
                         value("Fire Pit", "dot_duration_seconds"), tune("firebomb_pit_tick_seconds"), tune("firebomb_bounce_distance_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 15, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Pyrogeist")\n            return Rune::Pyrogeist;',
                                        'if (name == "Pyrogeist")\n            return Rune::FirePit;')),
            ("the farthest enemy is bounced to", (HEADER, "distances[place] < distances[best]", "distances[place] > distances[best]")),
            ("an enemy already hit is bounced to again", (HEADER, "if (!hit[place] && distances[place] <= reach", "if (distances[place] <= reach")),
            ("the reach is not asked", (HEADER, "distances[place] <= reach &&", "true &&")),
            ("a bounce takes no reduction", (HEADER, "1.0 - (reductionPct > 0 ? reductionPct : 0.0) / 100.0 * double(bounce)", "1.0")),
            ("a bounce can heal", (HEADER, "return basePct * (left > 0 ? left : 0.0);", "return basePct * left;")),
            ("one Pyrogeist too many stands", (HEADER, "standing - most + 1", "standing - most")),
            ("the first spew is at the cast", (HEADER, "* 1000.0 * (index + 1) + 0.5);\n    }\n\n    // The production half", "* 1000.0 * index + 0.5);\n    }\n\n    // The production half")),
            ("the bounces land together", (HEADER, "(delaySeconds > 0 ? delaySeconds : 0.0) * 1000.0 * (index + 1) + 0.5", "(delaySeconds > 0 ? delaySeconds : 0.0) * 1000.0 + 0.5")),
            ("a tick is the whole damage", (PERIODIC, "return ticks ? totalPct / ticks : 0.0;", "return totalPct;")),
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

    def test_the_record_is_the_engines_single_enemy_throw(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["range_yards"]), ("single_enemy", "45"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "damage_pct"), value("", "radius_yards")], [155, 8])
        self.assertEqual([value("Ghost Bomb", "damage_pct"), value("Ghost Bomb", "radius_yards")], [30, 28])
        self.assertEqual(value("Roll the Bones", "max_count"), 2)
        self.assertEqual([value("Fire Pit", "damage_pct"), value("Fire Pit", "dot_duration_seconds")], [60, 3])
        self.assertEqual([value("Pyrogeist", n) for n in ("damage_pct", "dot_duration_seconds", "max_count")], [880, 6, 3])
        self.assertEqual([value("Flash Fire", "target_count"), value("Flash Fire", "damage_dealt_reduction_pct")], [6, 15])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("firebomb_bounce_distance_yards", "14", "SF_8"), ("firebomb_flash_radius_yards", "25", "SF_18"),
                                 ("firebomb_flash_delay_seconds", "0.1", "SF_17"), ("firebomb_pyrogeist_tick_seconds", "0.3", "SF_25"),
                                 ("firebomb_pyrogeist_range_yards", "30", "SF_26")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/Witchdoctor_Firebomb.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_the_pools_tick_is_alexs_standing_default(self):
        row = tunables()["firebomb_pit_tick_seconds"]
        self.assertEqual((row["d3_value"], row["value"]), ("", "0.5"))
        self.assertIn("standing default", row["notes"])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("firebomb_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_pct", "own"), ("", "radius_yards", "own"), ("Ghost Bomb", "damage_pct", "own"),
                                    ("Ghost Bomb", "radius_yards", "own"), ("Roll the Bones", "max_count", "own"), ("Fire Pit", "damage_pct", "own"),
                                    ("Fire Pit", "dot_duration_seconds", "own"), ("Pyrogeist", "max_count", "own"),
                                    ("Flash Fire", "target_count", "own"), ("Flash Fire", "damage_dealt_reduction_pct", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_Firebomb.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(19) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(4), value("", "radius_yards"))
        self.assertAlmostEqual(number(21) * 100, value("Ghost Bomb", "damage_pct"))
        self.assertAlmostEqual(number(5), value("Ghost Bomb", "radius_yards"))
        self.assertAlmostEqual(number(7), value("Roll the Bones", "max_count"))
        self.assertAlmostEqual(number(10) * number(12) * 100, value("Fire Pit", "damage_pct"))
        self.assertAlmostEqual(number(12), value("Fire Pit", "dot_duration_seconds"))
        self.assertAlmostEqual(number(13) * (number(14) / number(25)) * 100, value("Pyrogeist", "damage_pct"))
        self.assertAlmostEqual(number(14), value("Pyrogeist", "dot_duration_seconds"))
        self.assertAlmostEqual(number(27), value("Pyrogeist", "max_count"))
        self.assertAlmostEqual(number(15), value("Flash Fire", "target_count"))
        self.assertAlmostEqual(number(16), value("Flash Fire", "damage_dealt_reduction_pct"))
        self.assertAlmostEqual(number(8), tune("firebomb_bounce_distance_yards"))
        self.assertAlmostEqual(number(18), tune("firebomb_flash_radius_yards"))
        self.assertAlmostEqual(number(17), tune("firebomb_flash_delay_seconds"))
        self.assertAlmostEqual(number(25), tune("firebomb_pyrogeist_tick_seconds"))
        self.assertAlmostEqual(number(26), tune("firebomb_pyrogeist_range_yards"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("Firebomb::BasePct(spellId)"), 1)
        self.assertEqual(self.dispatch.count("Firebomb::Cast(player, spellId, targets);"), 1)

    def test_the_explosion_is_the_skills_number_for_every_rune(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn('Is(spellId) ? std::optional<double>(Numbers::Num(BaseId(Skill), "damage_pct")) : std::nullopt', base)

    def test_the_blast_round_the_enemy_and_ghost_bombs_larger_one(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('Blast(player, spellId, where, Numbers::Num(BaseId(Skill), "radius_yards"), pct, aim);', cast)
        self.assertIn('Blast(player, spellId, where, Numbers::Num(spellId, "radius_yards"), Numbers::Num(spellId, "damage_pct"), aim);', cast)
        self.assertIn("if (rune == Rune::FlashFire) {", cast)
        self.assertIn("Chain(player, spellId, aim, pct); return; }", cast)

    def test_the_bounces_the_pool_the_columns_and_the_chain(self):
        bounces = self.code[self.code.index("void Bounces("):self.code.index("void Pool(")]
        self.assertIn('Numbers::Num(spellId, "max_count")', bounces)
        self.assertIn('NextBounce(distances, seen, Tune("firebomb_bounce_distance_yards"))', bounces)
        pool = self.code[self.code.index("void Pool("):self.code.index("void Column(")]
        self.assertIn('PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), ticks)', pool)
        self.assertIn('Tune("firebomb_pit_tick_seconds")', pool)
        column = self.code[self.code.index("void Column("):self.code.index("void Chain(")]
        self.assertIn('Retired(standing.size(), std::size_t(Numbers::Num(spellId, "max_count")))', column)
        self.assertIn('Tune("firebomb_pyrogeist_tick_seconds")', column)
        self.assertIn('Tune("firebomb_pyrogeist_range_yards")', column)
        self.assertIn("std::find(found->second.begin(), found->second.end(), stamp) == found->second.end()", column)
        chain = self.code[self.code.index("void Chain("):self.code.index("} // namespace")]
        self.assertIn('Numbers::Num(spellId, "target_count")', chain)
        self.assertIn('FlashPct(pct, bounce + 1, Numbers::Num(spellId, "damage_dealt_reduction_pct"))', chain)
        self.assertIn('BounceMs(bounce, Tune("firebomb_flash_delay_seconds"))', chain)
        self.assertIn('Tune("firebomb_flash_radius_yards")', chain)


if __name__ == "__main__":
    unittest.main()
