"""Witch Doctor Plague of Toads and its five runes (src/classes/witch_doctor/dc_witch_doctor_plague_of_toads.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_plague_of_toads/harness.cpp compiles the real dc_witch_doctor_plague_of_toads.h
    and the shared damage-over-time arithmetic with the sheets' own rune names and numbers: each rune name is its rune; the toads reach the
    nearest enemy of the line, the first on a tie; only Rain of Toads casts faster; the rain's ticks make its total, the first a tick after
    the cast and the last at its end; Addling Toads' chance edge to edge. Seven mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The cast is the engine's line (a `line_pierce` row of skill_targeting.csv, 3 yards wide by the designer's
    default); it is free, each rune's school and Toad Affinity's Mana (the class's Connected seam) are the record's and the sheet's.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Plague of Toads (or the rune
    that states it); every tunable is a row of data/tunables/witchdoctor.csv; the numbers equal the decoded
    Power/Witchdoctor_PlagueOfToads.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Cast`, `AttackSpeed`); the engine's two attack-speed lines carry the class's
    factor; Piercing Toads is the engine's hit and every other rune's is struck at the nearest enemy; the rain is scheduled on the player's
    own queue; Addling Toads confuses.

What it does not prove: anything on a running server. The toads, the rain, the pierce, the Mana and the confusion are
docs/test-diablocraft-vxrcu.10.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_plague_of_toads.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_plague_of_toads.h"
PICK = "src/classes/witch_doctor/dc_witch_doctor_pick.h"
PERIODIC = "src/combat/dc_periodic_strike.h"
SOURCES = [HEADER, PICK, PERIODIC, "tests/witch_doctor_plague_of_toads/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_plague_of_toads.cpp"
SKILL = "Plague of Toads"
RUNES = ["Explosive Toads", "Rain of Toads", "Piercing Toads", "Toad Affinity", "Addling Toads"]


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


def reach():
    rows = [r for r in read(D3 / "skill_targeting.csv") if r["skill"] == SKILL]
    assert len(rows) == 1 and rows[0]["target_type"] == "line_pierce", rows
    return float(rows[0]["range_yards"])


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_plague_of_toads/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("Rain of Toads", "damage_pct"), value("Rain of Toads", "dot_duration_seconds"), tune("plague_of_toads_rain_tick_seconds"),
                         tune("plague_of_toads_rain_speed_bonus"), value("Addling Toads", "proc_chance_pct"), reach()]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 12, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Rain of Toads")\n            return Rune::RainOfToads;',
                                        'if (name == "Rain of Toads")\n            return Rune::ExplosiveToads;')),
            ("the farthest enemy is reached", (HEADER, "if (distances[place] < distances[nearest])", "if (distances[place] > distances[nearest])")),
            ("the last of a tie is reached", (HEADER, "if (distances[place] < distances[nearest])", "if (distances[place] <= distances[nearest])")),
            ("every rune casts faster", (HEADER, "return rune == Rune::RainOfToads ? 1.0 + (bonus > 0 ? bonus : 0.0) : 1.0;", "return 1.0 + (bonus > 0 ? bonus : 0.0);")),
            ("the first tick is at the cast", (HEADER, "* 1000.0 * (index + 1) + 0.5", "* 1000.0 * index + 0.5")),
            ("a roll at the chance confuses", (HEADER, "return roll < chancePct;", "return roll <= chancePct;")),
            ("a selected enemy past the reach centres the rain", (HEADER, "return distance <= reach && inSight;", "return inSight;")),
            ("a selected enemy out of sight centres the rain", (HEADER, "return distance <= reach && inSight;", "return distance <= reach;")),
            ("the reach's edge is out", (HEADER, "return distance <= reach && inSight;", "return distance < reach && inSight;")),
            ("a tick is the whole total", (PERIODIC, "return ticks ? totalPct / ticks : 0.0;", "return totalPct;")),
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

    def test_the_record_is_the_engines_line(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["range_yards"], rows[SKILL]["width_yards"]), ("line_pierce", "49", "3"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual(value("", "damage_pct"), 190)
        self.assertEqual(value("Explosive Toads", "damage_pct"), 245)
        self.assertEqual([value("Rain of Toads", "damage_pct"), value("Rain of Toads", "dot_duration_seconds")], [130, 2])
        self.assertEqual(value("Piercing Toads", "damage_pct"), 130)
        self.assertEqual(value("Toad Affinity", "gain_resource"), 9)
        self.assertEqual([value("Addling Toads", n) for n in ("damage_pct", "proc_chance_pct", "duration_seconds")], [190, 15, 4])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("plague_of_toads_rain_radius_yards", "8", "SF_9"), ("plague_of_toads_rain_tick_seconds", "0.5", "SF_11"),
                                 ("plague_of_toads_rain_speed_bonus", "0.4", "SF_1")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/Witchdoctor_PlagueOfToads.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("plague_of_toads_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_pct", "own"), ("Explosive Toads", "damage_pct", "own"), ("Rain of Toads", "damage_pct", "own"),
                                    ("Rain of Toads", "dot_duration_seconds", "own"), ("Piercing Toads", "damage_pct", "own"),
                                    ("Toad Affinity", "gain_resource", "own"), ("Addling Toads", "proc_chance_pct", "own"),
                                    ("Addling Toads", "duration_seconds", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_PlagueOfToads.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(0) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(17) * 100, value("Explosive Toads", "damage_pct"))
        self.assertAlmostEqual(number(8) * 100, value("Rain of Toads", "damage_pct"))
        self.assertAlmostEqual(number(10), value("Rain of Toads", "dot_duration_seconds"))
        self.assertAlmostEqual(number(22) * 100, value("Piercing Toads", "damage_pct"))
        self.assertAlmostEqual(number(7), value("Toad Affinity", "gain_resource"))
        self.assertAlmostEqual(number(12) * 100, value("Addling Toads", "proc_chance_pct"))
        self.assertAlmostEqual(number(13), value("Addling Toads", "duration_seconds"))
        self.assertAlmostEqual(number(9), tune("plague_of_toads_rain_radius_yards"))
        self.assertAlmostEqual(number(11), tune("plague_of_toads_rain_tick_seconds"))
        self.assertAlmostEqual(float(str(sf[1]).split("+")[1].split("*")[0]), tune("plague_of_toads_rain_speed_bonus"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))
        self.combat = (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8")

    def test_the_dispatch_answers_the_seams(self):
        for call in ("if (auto toads = PlagueOfToads::BasePct(spellId)) return toads;", "PlagueOfToads::Cast(player, spellId, targets);",
                     "return PlagueOfToads::AttackSpeed(spellId, base);"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_engines_two_attack_speed_lines_carry_the_classes_factor(self):
        self.assertEqual(self.combat.count("WitchDoctor::AttackSpeed(player, spellId, Necromancer::AttackSpeed(player, spellId, Crusader::AttackSpeed("), 2)

    def test_only_piercing_toads_is_the_engines_hit_the_rest_struck_at_the_nearest(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn('RuneAt(spellId) == Rune::PiercingToads ? Numbers::Num(spellId, "damage_pct") : 0.0', base)
        cast = self.code[self.code.index("void Cast("):self.code.index("double AttackSpeed(")]
        self.assertIn("rune == Rune::PiercingToads) return;", cast)
        self.assertIn("Unit* nearest = Nearest(player, targets);", cast)
        self.assertIn('Combat::Strike(player, nearest, spellId, Numbers::Num(spellId, "damage_pct"))', cast)
        self.assertIn("Combat::Connected(player, spellId, 1);", cast)

    def rain_aim_problems(self, code):
        """What is missing from how the rain picks its centre: the selected enemy kept only within the line's reach and in sight, the
        fallback the nearest by distance (never the list's first), and the non-rain toads reaching the nearest by the same pick."""
        cast = code[code.index("void Cast("):code.index("double AttackSpeed(")]
        nearest = code[code.index("Unit* Nearest("):code.index("void Rain(")]
        problems = []
        for needle in ("player->GetSelectedUnit()",
                       "SelectedHolds(player->GetExactDist(aim), Combat::TargetRange(spellId), player->IsWithinLOSInMap(aim))",
                       "aim = Nearest(player, targets);", "Unit* nearest = Nearest(player, targets);"):
            if needle not in cast:
                problems.append(needle)
        if "targets.front()" in cast or "targets[0]" in cast:
            problems.append("the list's first enemy is taken")
        for needle in ("distances.push_back(player->GetExactDist(enemy));", "return targets[NearestOf(distances)];"):
            if needle not in nearest:
                problems.append(needle)
        return problems

    def test_the_rain_falls_on_the_selected_enemy_in_reach_and_sight_else_the_nearest(self):
        self.assertEqual(self.rain_aim_problems(self.code), [])

    def test_a_planted_difference_in_the_rains_centre_is_caught(self):
        mutations = [
            ("the selected enemy is kept at any distance",
             "!SelectedHolds(player->GetExactDist(aim), Combat::TargetRange(spellId), player->IsWithinLOSInMap(aim))", "false"),
            ("the selected enemy is kept out of sight",
             "Combat::TargetRange(spellId), player->IsWithinLOSInMap(aim))", "Combat::TargetRange(spellId), true)"),
            ("the fallback is the list's first enemy", "aim = Nearest(player, targets);", "aim = targets.empty() ? nullptr : targets.front();"),
            ("the nearest is picked by the list's order", "return targets[NearestOf(distances)];", "return targets.front();"),
        ]
        for label, old, new in mutations:
            with self.subTest(label):
                self.assertEqual(self.code.count(old), 1, old)
                self.assertNotEqual(self.rain_aim_problems(self.code.replace(old, new)), [], f"{label} was not caught")

    def test_the_rain_falls_on_the_selected_enemy_on_the_players_queue(self):
        rain = self.code[self.code.index("void Rain("):self.code.index("} // namespace")]
        self.assertIn('PeriodicStrike::Ticks(Numbers::Num(spellId, "dot_duration_seconds"), Tune("plague_of_toads_rain_tick_seconds"))', rain)
        self.assertIn('PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), ticks)', rain)
        self.assertIn('Tune("plague_of_toads_rain_radius_yards")', rain)
        self.assertIn("player->m_Events.AddEventAtOffset(", rain)
        self.assertIn('RainMs(tick, Tune("plague_of_toads_rain_tick_seconds"))', rain)

    def test_addling_toads_confuses(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("double AttackSpeed(")]
        self.assertIn('rune == Rune::AddlingToads && Confuses(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct"))', cast)
        self.assertIn('Confuse(player, nearest, Numbers::Num(spellId, "duration_seconds"));', cast)
        self.assertIn('base * SpeedFactor(RuneAt(spellId), Tune("plague_of_toads_rain_speed_bonus"))', self.code)


if __name__ == "__main__":
    unittest.main()
