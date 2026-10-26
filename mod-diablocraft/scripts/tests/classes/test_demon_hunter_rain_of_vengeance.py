"""Demon Hunter Rain of Vengeance and its five runes (src/classes/demon_hunter/dc_demon_hunter_rain_of_vengeance.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_rain_of_vengeance/harness.cpp compiles the real
    dc_demon_hunter_rain_of_vengeance.h, the DoT rules and the shared pick with the sheets' own rune names and numbers: each rune name is
    its rune; how many ticks, storms and grenades fit and the shares make each rune's total; when each lands after the delay; a random
    place inside the area, evenly; Stampede's beasts along the line and the wave reaching them in turn. Ten mutations planted in a scratch
    copy must each make it fail.
  * **The record needs no change.** The cast is the engine's ground cast (a `ground_area` row of skill_targeting.csv, radius 30) that hits
    nothing of its own; its 30 second cooldown is the record's.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Rain of Vengeance (or the
    rune that states it); every tunable is a row of data/tunables/demonhunter.csv, two of them marked placeholders; the numbers equal the
    decoded Power/DemonHunter_RainOfVengeance.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Ground`); the cast hits nothing; every strike is a damage-over-time strike;
    each rune's work is scheduled on the player's own queue after the delay; Flying Strike's strikes freeze with the stun power and
    Stampede's knock back.

What it does not prove: anything on a running server. The rain, the cloud, the grenades, the beasts and the wave are
docs/test-diablocraft-vawmy.31.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_rain_of_vengeance.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_rain_of_vengeance.h"
DOT = "src/classes/demon_hunter/dc_demon_hunter_dot.h"
PICK = "src/classes/demon_hunter/dc_demon_hunter_pick.h"
SOURCES = [HEADER, DOT, PICK, "tests/demon_hunter_rain_of_vengeance/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_rain_of_vengeance.cpp"
SKILL = "Rain of Vengeance"
RUNES = ["Shade", "Dark Cloud", "Anathema", "Flying Strike", "Stampede"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_rain_of_vengeance/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "damage_pct"), value("", "dot_duration_seconds"), tune("rain_of_vengeance_tick_seconds"),
                         value("Dark Cloud", "damage_pct"), value("Dark Cloud", "dot_duration_seconds"),
                         tune("rain_of_vengeance_cloud_storm_interval_seconds"), value("Anathema", "damage_pct"),
                         value("Anathema", "dot_duration_seconds"), tune("rain_of_vengeance_grenade_interval_seconds"),
                         tune("rain_of_vengeance_delay_seconds"), value("Flying Strike", "pet_count"), value("Flying Strike", "damage_pct"),
                         value("Stampede", "pet_count"), value("Stampede", "dot_duration_seconds"), tune("rain_of_vengeance_stampede_radius_yards")]
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
            ("two runes share a name", (HEADER, 'if (name == "Dark Cloud")\n            return Rune::DarkCloud;',
                                        'if (name == "Dark Cloud")\n            return Rune::Shade;')),
            ("a share is the whole total", (DOT, "return ticks ? totalPct / ticks : 0.0;", "return totalPct;")),
            ("the first lands before the delay", (HEADER, "(delaySeconds > 0 ? delaySeconds : 0.0) + (intervalSeconds > 0", "0.0 + (intervalSeconds > 0")),
            ("the series lands together", (HEADER, "(intervalSeconds > 0 ? intervalSeconds : 0.0) * index;", "0.0;")),
            ("the distance is not even over the area", (HEADER, "radius * std::sqrt(distanceRoll < 0 ? 0.0 : (distanceRoll > 1 ? 1.0 : distanceRoll))",
                                                        "radius * (distanceRoll < 0 ? 0.0 : (distanceRoll > 1 ? 1.0 : distanceRoll))")),
            ("a point can fall outside the disc", (HEADER, "radius * std::sqrt(distanceRoll < 0 ? 0.0 : (distanceRoll > 1 ? 1.0 : distanceRoll))",
                                                   "radius * std::sqrt(distanceRoll < 0 ? 0.0 : distanceRoll * 1.1)")),
            ("the first beast is at the start", (HEADER, "length * double(index + 1) / double(count)", "length * double(index) / double(count)")),
            ("the wave reaches every beast at once", (HEADER, "(seconds > 0 ? seconds : 0.0) * double(index + 1) / double(count)", "0.0")),
            ("the wave takes no time", (HEADER, "(seconds > 0 ? seconds : 0.0) * double(index + 1) / double(count)", "(seconds > 0 ? seconds : 0.0)")),
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

    def test_the_record_is_the_engines_ground_cast(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["radius_yards"]), ("ground_area", "30"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "damage_pct"), value("", "dot_duration_seconds")], [30, 1500, 5])
        self.assertEqual([value("Shade", "damage_pct"), value("Shade", "dot_duration_seconds")], [2800, 5])
        self.assertEqual([value("Dark Cloud", "damage_pct"), value("Dark Cloud", "dot_duration_seconds")], [3500, 8])
        self.assertEqual([value("Anathema", "damage_pct"), value("Anathema", "dot_duration_seconds")], [5800, 2])
        self.assertEqual([value("Flying Strike", n) for n in ("pet_count", "damage_pct", "freeze_duration_seconds")], [8, 3800, 2])
        self.assertEqual([value("Stampede", n) for n in ("pet_count", "damage_pct", "dot_duration_seconds")], [10, 4600, 3])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("rain_of_vengeance_delay_seconds", "0.5", "SF_3"), ("rain_of_vengeance_tick_seconds", "0.25", "SF_5"),
                                 ("rain_of_vengeance_radius_yards", "30", "SF_7"), ("rain_of_vengeance_anathema_radius_yards", "37", "SF_7"),
                                 ("rain_of_vengeance_cloud_storm_interval_seconds", "0.5", "SF_38"), ("rain_of_vengeance_cloud_search_yards", "50", "SF_18"),
                                 ("rain_of_vengeance_cloud_storm_radius_yards", "10", "SF_34"), ("rain_of_vengeance_grenade_interval_seconds", "0.1", "SF_31"),
                                 ("rain_of_vengeance_grenade_lifetime_seconds", "2", "SF_33"), ("rain_of_vengeance_grenade_radius_yards", "7", "SF_32"),
                                 ("rain_of_vengeance_flyer_interval_seconds", "0.1", "SF_4"), ("rain_of_vengeance_flyer_radius_yards", "11", "SF_13")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_RainOfVengeance.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_the_stampedes_radius_and_knockback_are_marked_placeholders(self):
        for name, stand_in in (("rain_of_vengeance_stampede_radius_yards", "8"), ("rain_of_vengeance_stampede_knockback_yards", "5")):
            row = tunables()[name]
            self.assertEqual((row["d3_value"], row["value"]), ("", stand_in), name)
            self.assertIn("placeholder", row["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("rain_of_vengeance_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_RainOfVengeance.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        def rune_value(n):
            return float(str(sf[n]).split("?")[1].split(":")[0])

        self.assertAlmostEqual(number(35), value("", "cooldown_seconds"))
        self.assertAlmostEqual(number(1) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(6), value("", "dot_duration_seconds"))
        self.assertAlmostEqual(rune_value(20) * 100, value("Shade", "damage_pct"))
        self.assertAlmostEqual(rune_value(19) * 100, value("Dark Cloud", "damage_pct"))
        self.assertAlmostEqual(number(16), value("Dark Cloud", "dot_duration_seconds"))
        self.assertAlmostEqual(number(9) * 100, value("Anathema", "damage_pct"))
        self.assertAlmostEqual(number(30), value("Anathema", "dot_duration_seconds"))
        self.assertAlmostEqual(number(14), value("Flying Strike", "pet_count"))
        self.assertAlmostEqual(number(12) * 100, value("Flying Strike", "damage_pct"))
        self.assertAlmostEqual(number(37), value("Flying Strike", "freeze_duration_seconds"))
        self.assertAlmostEqual(number(15), value("Stampede", "pet_count"))
        self.assertAlmostEqual(number(11) * 100, value("Stampede", "damage_pct"))
        self.assertAlmostEqual(number(8), value("Stampede", "dot_duration_seconds"))
        self.assertAlmostEqual(number(3), tune("rain_of_vengeance_delay_seconds"))
        self.assertAlmostEqual(number(5), tune("rain_of_vengeance_tick_seconds"))
        self.assertAlmostEqual(number(38), tune("rain_of_vengeance_cloud_storm_interval_seconds"))
        self.assertAlmostEqual(number(18), tune("rain_of_vengeance_cloud_search_yards"))
        self.assertAlmostEqual(number(34), tune("rain_of_vengeance_cloud_storm_radius_yards"))
        self.assertAlmostEqual(number(31), tune("rain_of_vengeance_grenade_interval_seconds"))
        self.assertAlmostEqual(number(33), tune("rain_of_vengeance_grenade_lifetime_seconds"))
        self.assertAlmostEqual(number(13), tune("rain_of_vengeance_flyer_radius_yards"))
        self.assertAlmostEqual(float(str(sf[4]).split(":")[1]), tune("rain_of_vengeance_flyer_interval_seconds"))
        base_radius, anathema_radius = str(sf[7]).split(":")[1].strip(" ()"), str(sf[7]).split("(")[1].split(")")[0]
        self.assertAlmostEqual(float(base_radius), tune("rain_of_vengeance_radius_yards"))
        self.assertEqual(anathema_radius.replace(" ", ""), "35+Rune_C*2")
        self.assertAlmostEqual(37, tune("rain_of_vengeance_anathema_radius_yards"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto rain = RainOfVengeance::BasePct(spellId)) return rain;"), 1)
        self.assertLess(self.dispatch.index("ElementalArrow::BasePct(spellId)"), self.dispatch.index("RainOfVengeance::BasePct(spellId)"))
        self.assertLess(self.dispatch.index("RainOfVengeance::BasePct(spellId)"), self.dispatch.index("return Caltrops::BasePct(spellId);"))
        self.assertEqual(self.dispatch.count("RainOfVengeance::Ground(player, spellId, center);"), 1)

    def test_the_cast_hits_nothing_and_every_strike_is_a_damage_over_time_strike(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        rain = self.code[self.code.index("std::vector<Unit*> Rain("):self.code.index("Position At(")]
        self.assertIn("Combat::Strike(player, enemy, spellId, pct, true)", rain)

    def test_work_comes_due_on_the_players_queue_if_the_demon_hunter_is_still_there(self):
        after = self.code[self.code.index("void After("):self.code.index("std::vector<Unit*> Rain(")]
        self.assertIn("player->m_Events.AddEventAtOffset(", after)
        self.assertIn("if (player->IsAlive() && player->IsInWorld()) work();", after)

    def test_the_rain_and_the_cloud(self):
        falls = self.code[self.code.index("void Falls("):self.code.index("void Storms(")]
        self.assertIn('Count(Numbers::Num(spellId, "dot_duration_seconds"), Tune("rain_of_vengeance_tick_seconds"))', falls)
        self.assertIn('Share(Numbers::Num(spellId, "damage_pct"), ticks)', falls)
        self.assertIn('StartMs(i, DelaySeconds(), Tune("rain_of_vengeance_tick_seconds"))', falls)
        storms = self.code[self.code.index("void Storms("):self.code.index("void Grenades(")]
        self.assertIn('Tune("rain_of_vengeance_cloud_search_yards")', storms)
        self.assertIn("enemies[PickAt(Roll(), enemies.size())]->GetPosition()", storms)
        self.assertIn('Tune("rain_of_vengeance_cloud_storm_radius_yards")', storms)

    def test_the_beasts_and_the_grenades(self):
        grenades = self.code[self.code.index("void Grenades("):self.code.index("void Flyers(")]
        self.assertIn('Tune("rain_of_vengeance_anathema_radius_yards")', grenades)
        self.assertIn('Tune("rain_of_vengeance_grenade_lifetime_seconds")', grenades)
        self.assertIn('Tune("rain_of_vengeance_grenade_radius_yards")', grenades)
        flyers = self.code[self.code.index("void Flyers("):self.code.index("void Wave(")]
        self.assertIn('unsigned(Numbers::Num(spellId, "pet_count"))', flyers)
        self.assertIn('Tune("rain_of_vengeance_flyer_radius_yards")', flyers)
        self.assertIn('Stun(player, enemy, Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));', flyers)
        wave = self.code[self.code.index("void Wave("):self.code.index("} // namespace")]
        self.assertIn("start.GetAbsoluteAngle(&center)", wave)
        self.assertIn('WaveMs(i, beasts, DelaySeconds(), Numbers::Num(spellId, "dot_duration_seconds"))', wave)
        self.assertIn('Abilities::Knockback(player, enemy, Tune("rain_of_vengeance_stampede_knockback_yards"));', wave)
        self.assertIn('Tune("rain_of_vengeance_stampede_radius_yards")', wave)


if __name__ == "__main__":
    unittest.main()
