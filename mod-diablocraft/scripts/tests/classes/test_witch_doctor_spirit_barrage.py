"""Witch Doctor Spirit Barrage and its five runes (src/classes/witch_doctor/dc_witch_doctor_spirit_barrage.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_spirit_barrage/harness.cpp compiles the real
    dc_witch_doctor_spirit_barrage.h with the sheets' own rune names and numbers: each rune name is its rune; the bolts share the
    total and land in order from the delay until a hit, each later gap longer by the file's delta; Phlebotomize's Life is the sheet's
    at level 70 and less below; Well of Souls' spirits fly one every fire rate, never more than the sheet's; Manitou's bolts make its
    damage; no more barrages than the file's most; the spirits seek the enemies other than the aimed one. Mutations planted in a
    scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Spirit Barrage
    (or the rune that states it) the engine can read; every tunable is a row of data/tunables/witchdoctor.csv; the numbers equal the
    decoded Power/Witchdoctor_SpiritBarrage.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams; the cast's own hit is nothing and its Mana is paid bolt by bolt, not by the
    cast; each bolt lands on the enemy aimed at with its rune's part; Phantasm is a periodic device of the shared piece and Manitou
    a chain of bolts that a later Manitou ends.

What it does not prove: anything on a running server. The bolts, the spirits and the spectres are docs/test-diablocraft-vxrcu.24.md's,
live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_spirit_barrage.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_spirit_barrage.h"
SOURCES = [HEADER, "src/combat/dc_healing_table.h", "src/combat/dc_periodic_strike.h", "tests/witch_doctor_spirit_barrage/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_spirit_barrage.cpp"
SKILL = "Spirit Barrage"
POWER = "Power/Witchdoctor_SpiritBarrage.pow"
RUNES = ["Phlebotomize", "Well of Souls", "Phantasm", "The Spirit Is Willing", "Manitou"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_spirit_barrage/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "projectile_count"), value("", "damage_pct"), tune("spirit_barrage_hit_delay_seconds"),
                         tune("spirit_barrage_bolt_gap_seconds"), tune("spirit_barrage_bolt_gap_delta_seconds"),
                         value("Phlebotomize", "heal_per_hit_life"), value("Well of Souls", "projectile_count"),
                         tune("spirit_barrage_well_duration_seconds"), tune("spirit_barrage_well_fire_rate_seconds"),
                         value("Manitou", "damage_pct"), value("Manitou", "dot_duration_seconds"), tune("spirit_barrage_manitou_tick_seconds"),
                         tune("spirit_barrage_max_active")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 24, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Well of Souls")\n            return Rune::WellOfSouls;',
                                        'if (name == "Well of Souls")\n            return Rune::Phantasm;')),
            ("every bolt keeps the rune's element", (HEADER, "return rune != Rune::WellOfSouls;", "return true;")),
            ("a bolt is the whole total", (HEADER, "return count ? totalPct / count : 0.0;", "return totalPct;")),
            ("the first bolt lands at once", (HEADER, "double seconds = hitDelaySeconds;", "double seconds = 0.0;")),
            ("the bolts have no gap", (HEADER, "seconds += gapSeconds + deltaSeconds * bolt;", "seconds += deltaSeconds * bolt;")),
            ("the gap never grows", (HEADER, "seconds += gapSeconds + deltaSeconds * bolt;", "seconds += gapSeconds;")),
            ("the Life ignores the level", (HEADER, "return sheetLife * Healing::At(level) / Healing::At(70);", "return sheetLife;")),
            ("the Life is the table's raw number", (HEADER, "return sheetLife * Healing::At(level) / Healing::At(70);", "return Healing::At(level);")),
            ("the spirits are more than the sheet's", (HEADER, "return std::min(count, unsigned(std::floor(buffSeconds / rateSeconds + 1e-9)) + 1);",
                                                       "return unsigned(std::floor(buffSeconds / rateSeconds + 1e-9)) + 1;")),
            ("no fire rate still flies", (HEADER, "if (rateSeconds <= 0)\n            return 0;", "")),
            ("the spirits fly together", (HEADER, "return std::uint32_t(index * rateSeconds * 1000.0 + 0.5);", "return 0;")),
            ("a spectre bolt is the whole damage", (HEADER, "return PeriodicStrike::TickPct(totalPct, PeriodicStrike::Ticks(seconds, tickSeconds));", "return totalPct;")),
            ("the barrages have no limit", (HEADER, "return most == 0 || inTheAir < most;", "return true;")),
            ("one barrage too many", (HEADER, "return most == 0 || inTheAir < most;", "return most == 0 || inTheAir <= most;")),
            ("a spirit seeks the aimed enemy", (HEADER, "if (i != aimed && distances[i] <= within)", "if (distances[i] <= within)")),
            ("a spirit seeks beyond the radius", (HEADER, "if (i != aimed && distances[i] <= within)", "if (i != aimed)")),
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
        self.assertEqual([value("", "cost_resource"), value("", "projectile_count"), value("", "damage_pct")], [100, 4, 600])
        self.assertEqual(value("Phlebotomize", "heal_per_hit_life"), 6437)
        self.assertEqual([value("Well of Souls", "projectile_count"), value("Well of Souls", "damage_pct")], [3, 65])
        self.assertEqual([value("Phantasm", "damage_pct"), value("Phantasm", "dot_duration_seconds"), value("Phantasm", "radius_yards"),
                          value("Phantasm", "max_count")], [750, 5, 10, 3])
        self.assertEqual(value("The Spirit Is Willing", "gain_resource"), 12)
        self.assertEqual([value("Manitou", "damage_pct"), value("Manitou", "dot_duration_seconds")], [14000, 20])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("spirit_barrage_hit_delay_seconds", "0.6", "SF_2"), ("spirit_barrage_bolt_gap_seconds", "0.1", "SF_15"),
                                 ("spirit_barrage_bolt_gap_delta_seconds", "0.002", "SF_21"), ("spirit_barrage_max_active", "30", "SF_9"),
                                 ("spirit_barrage_well_duration_seconds", "1.5", "SF_6"), ("spirit_barrage_well_fire_rate_seconds", "0.45", "SF_7"),
                                 ("spirit_barrage_well_search_yards", "40", "SF_10"), ("spirit_barrage_phantasm_tick_seconds", "0.5", "SF_16"),
                                 ("spirit_barrage_manitou_tick_seconds", "0.5", "SF_18"), ("spirit_barrage_manitou_search_yards", "30", "SF_19")):
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""))
                self.assertIn(source, rows[name]["notes"])
                self.assertIn(POWER, rows[name]["notes"])
                self.assertNotIn("placeholder", rows[name]["notes"].lower())

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {n for n in tunables() if n.startswith("spirit_barrage_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]) for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for key in (("", "damage_pct"), ("", "projectile_count"), ("Phlebotomize", "heal_per_hit_life"), ("Well of Souls", "projectile_count"),
                    ("Well of Souls", "damage_pct"), ("Phantasm", "damage_pct"), ("Phantasm", "dot_duration_seconds"), ("Phantasm", "radius_yards"),
                    ("Phantasm", "max_count"), ("The Spirit Is Willing", "gain_resource"), ("Manitou", "damage_pct"), ("Manitou", "dot_duration_seconds")):
            self.assertIn(key, mapped, key)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract(POWER))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(24) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(23), value("", "projectile_count"))
        self.assertAlmostEqual(float(str(sf[1]).split("*")[0]) * 536421, value("Phlebotomize", "heal_per_hit_life"), places=0)
        self.assertAlmostEqual(number(8) * 100, value("Well of Souls", "damage_pct"))
        self.assertAlmostEqual(number(14) * number(11) * 100, value("Phantasm", "damage_pct"))
        self.assertAlmostEqual(number(11), value("Phantasm", "dot_duration_seconds"))
        self.assertAlmostEqual(number(13), value("Phantasm", "radius_yards"))
        self.assertAlmostEqual(number(12), value("Phantasm", "max_count"))
        self.assertAlmostEqual(number(5), value("The Spirit Is Willing", "gain_resource"))
        self.assertAlmostEqual(number(17), value("Manitou", "dot_duration_seconds"))
        self.assertAlmostEqual(number(2), tune("spirit_barrage_hit_delay_seconds"))
        self.assertAlmostEqual(number(15), tune("spirit_barrage_bolt_gap_seconds"))
        self.assertAlmostEqual(number(21), tune("spirit_barrage_bolt_gap_delta_seconds"))
        self.assertAlmostEqual(number(9), tune("spirit_barrage_max_active"))
        self.assertAlmostEqual(number(6), tune("spirit_barrage_well_duration_seconds"))
        self.assertAlmostEqual(number(7), tune("spirit_barrage_well_fire_rate_seconds"))
        self.assertAlmostEqual(number(10), tune("spirit_barrage_well_search_yards"))
        self.assertAlmostEqual(number(16), tune("spirit_barrage_phantasm_tick_seconds"))
        self.assertAlmostEqual(number(18), tune("spirit_barrage_manitou_tick_seconds"))
        self.assertAlmostEqual(number(19), tune("spirit_barrage_manitou_search_yards"))
        # The d3planner tooltip's 14000% for Manitou is the sheet's and is built; the file's own scalar (1.5, SF_20) is a different figure.
        self.assertNotAlmostEqual(number(20) * 100 * value("Manitou", "dot_duration_seconds") / tune("spirit_barrage_manitou_tick_seconds"),
                                  value("Manitou", "damage_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto bolts = SpiritBarrage::BasePct(spellId)) return bolts;"), 1)
        self.assertEqual(self.dispatch.count("SpiritBarrage::Cast(player, spellId, targets);"), 1)
        self.assertIn("if (!player || SpiritBarrage::Is(spellId)) return;", self.dispatch)

    def test_the_cast_hits_nothing_and_each_bolt_pays_for_itself(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        land = self.code[self.code.index("void Land("):self.code.index("void Seek(")]
        self.assertIn("Combat::Strike(player, enemy, BoltTakesRuneElement(rune) ? spellId : base, pct)", land)
        self.assertIn('Heal(player, spellId, LevelLife(Numbers::Num(spellId, "heal_per_hit_life"), player->GetLevel()));', land)
        self.assertIn('Gain(player, Classes::ClassIdOf(player), spellId, Numbers::Num(spellId, "gain_resource"), 1);', land)
        self.assertIn("rune == Rune::Phlebotomize", land)
        self.assertIn("rune == Rune::TheSpiritIsWilling", land)

    def test_the_bolts_land_one_after_another_and_are_counted_in_the_air(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('MayBombard(inTheAir[owner], unsigned(Tune("spirit_barrage_max_active")))', cast)
        self.assertIn('BoltPct(Numbers::Num(base, "damage_pct"), count)', cast)
        self.assertIn("BoltLandsMs(bolt, hit, gap, delta)", cast)
        self.assertIn('unsigned(Numbers::Num(base, "projectile_count"))', cast)
        self.assertIn("if (last) {", cast)
        self.assertIn("--inTheAir[owner];", cast)

    def test_a_logout_clears_the_barrages_in_the_air_and_the_spectre(self):
        self.assertIn('PlayerScript("dc_witch_doctor_spirit_barrage", {PLAYERHOOK_ON_LOGOUT})', self.code)
        logout = self.code[self.code.index("void OnPlayerLogout("):self.code.index("} // namespace")]
        self.assertIn("inTheAir.erase(player->GetGUID().GetRawValue());", logout)
        self.assertIn("spectres.erase(player->GetGUID().GetRawValue());", logout)
        self.assertIn("new Logouts();", self.code)
        self.assertEqual(self.dispatch.count("SpiritBarrage::RegisterScripts();"), 1)

    def test_the_runes_part(self):
        seek = self.code[self.code.index("void Seek("):self.code.index("void Summon(")]
        self.assertIn('Tune("spirit_barrage_well_search_yards")', seek)
        self.assertIn("Others(distances,", seek)
        self.assertIn('Combat::Strike(player, near[others[urand(0, uint32(others.size() - 1))]], spellId, Numbers::Num(spellId, "damage_pct"));', seek)
        summon = self.code[self.code.index("void Summon("):self.code.index("void Hover(")]
        self.assertIn("spectre.spec.mode = GroundDevice::Mode::Periodic;", summon)
        self.assertIn('spectre.spec.radiusYards = Numbers::Num(spellId, "radius_yards");', summon)
        self.assertIn('spectre.spec.most = std::size_t(Numbers::Num(spellId, "max_count"));', summon)
        self.assertIn('Tune("spirit_barrage_phantasm_tick_seconds")', summon)
        self.assertIn("PeriodicStrike::TickPct(", summon)
        self.assertIn("GroundDevice::Place(player, spectre, at);", summon)
        hover = self.code[self.code.index("void Hover("):self.code.index("bool Is(")]
        self.assertIn("if (spectres[player->GetGUID().GetRawValue()] != serial) return;", hover)
        self.assertIn('Tune("spirit_barrage_manitou_search_yards")', hover)
        self.assertIn("Hover(player, spellId, serial, left - 1, pct)", hover)
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("case Rune::WellOfSouls:", cast)
        self.assertIn("case Rune::Phantasm: Summon(player, spellId, target->GetPosition());", cast)
        self.assertIn("serial = ++spectres[owner];", cast)


if __name__ == "__main__":
    unittest.main()
