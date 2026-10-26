"""Witch Doctor Grasp of the Dead and its five runes (src/classes/witch_doctor/dc_witch_doctor_grasp_of_the_dead.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_grasp_of_the_dead/harness.cpp compiles the real dc_witch_doctor_grasp_of_the_dead.h and
    the shared damage-over-time arithmetic with the sheets' own rune names and numbers: each rune name is its rune; a pulse's slow outlasts the
    pulse; the hands' pulses make the sheet's total, the first a pulse after they rise and the last at the end; Rain of Corpses' corpses make
    its total; Death Is Life's area outlasts the last pulse, ends with its time and stops at the radius, and its roll rises below the sheet's
    chance only. Ten mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The cast is the engine's ground cast (a `ground_area` row of skill_targeting.csv, radius 14); the Mana
    cost, the cooldown, Unbreakable Grasp's free cast and Desperate Grasp's cooldown, each rune's school are the record's.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Grasp of the Dead (or the
    rune that states it); every tunable is a row of data/tunables/witchdoctor.csv; the numbers equal the decoded
    Power/Witchdoctor_GraspOfTheDead.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (`BasePct`, `Ground`, `RegisterScripts`); the cast hits nothing; the hands pulse on the player's own queue;
    Rain of Corpses states its corpses' damage as its own and the hands keep the skill's; Death Is Life watches the area the hands stand
    in and an enemy that dies there raises one dog through the pets piece's `RaiseDogAt` (the cap and the room are the pets piece's); the
    health globe is a seam with no caller.

What it does not prove: anything on a running server. The hands, the slow and the corpses are docs/test-diablocraft-vxrcu.12.md's, live.
**Not built**: Death Is Life's health globe (the globes are on hold): `SpawnGlobe` is a seam nothing calls.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_grasp_of_the_dead.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_grasp_of_the_dead.h"
PICK = "src/classes/witch_doctor/dc_witch_doctor_pick.h"
PERIODIC = "src/combat/dc_periodic_strike.h"
SOURCES = [HEADER, PICK, PERIODIC, "tests/witch_doctor_grasp_of_the_dead/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_grasp_of_the_dead.cpp"
SKILL = "Grasp of the Dead"
RUNES = ["Groping Eels", "Rain of Corpses", "Unbreakable Grasp", "Desperate Grasp", "Death Is Life"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_grasp_of_the_dead/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "damage_pct"), value("", "dot_duration_seconds"), tune("grasp_of_the_dead_pulse_seconds"),
                         tune("grasp_of_the_dead_slow_extra_seconds"), value("Rain of Corpses", "damage_pct"),
                         value("Rain of Corpses", "dot_duration_seconds"), tune("grasp_of_the_dead_corpse_seconds"), value("Death Is Life", "proc_chance_pct"),
                         tune("grasp_of_the_dead_radius_yards")]
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
            ("two runes share a name", (HEADER, 'if (name == "Rain of Corpses")\n            return Rune::RainOfCorpses;',
                                        'if (name == "Rain of Corpses")\n            return Rune::GropingEels;')),
            ("the slow lapses between pulses", (HEADER, "(extraSeconds > 0 ? extraSeconds : 0.0);", "0.0;")),
            ("the first pulse is when the hands rise", (HEADER, "* 1000.0 * (index + 1) + 0.5", "* 1000.0 * index + 0.5")),
            ("a pulse is the whole damage", (PERIODIC, "return ticks ? totalPct / ticks : 0.0;", "return totalPct;")),
            ("a pulse is lost", (PERIODIC, "std::floor(seconds / tickSeconds + 1e-9)", "std::floor(seconds / tickSeconds - 0.5)")),
            ("the area ends with the last pulse", (HEADER, "return std::uint64_t(SlowSeconds(seconds, extraSeconds) * 1000.0 + 0.5);",
                                                   "return std::uint64_t(SlowSeconds(seconds, 0.0) * 1000.0 + 0.5);")),
            ("the area reaches past its radius", (HEADER, "return nowMs < untilMs && distance <= radius;", "return nowMs < untilMs;")),
            ("a death after the area has ended counts", (HEADER, "return nowMs < untilMs && distance <= radius;", "return distance <= radius;")),
            ("a roll at the chance rises", (HEADER, "return chancePct > 0 && roll < chancePct;", "return chancePct > 0 && roll <= chancePct;")),
            ("every roll picks the first enemy", (PICK, "std::min(count - 1, std::size_t(std::max(0.0, roll) * double(count)))", "0")),
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
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["radius_yards"]), ("ground_area", "14"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", n) for n in ("cost_resource", "cooldown_seconds", "slow_pct", "damage_pct", "dot_duration_seconds")], [150, 8, 60, 760, 8])
        self.assertEqual(value("Groping Eels", "damage_pct"), 1360)
        self.assertEqual([value("Rain of Corpses", "damage_pct"), value("Rain of Corpses", "dot_duration_seconds")], [420, 3])
        self.assertEqual(value("Unbreakable Grasp", "slow_pct"), 80)
        self.assertEqual(value("Desperate Grasp", "cooldown_seconds"), 4)
        self.assertEqual(value("Death Is Life", "proc_chance_pct"), 70)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("grasp_of_the_dead_radius_yards", "14", "SF_3"), ("grasp_of_the_dead_pulse_seconds", "0.5", "SF_4"),
                                 ("grasp_of_the_dead_slow_extra_seconds", "0.25", "SF_6"), ("grasp_of_the_dead_corpse_seconds", "1.5", "SF_13"),
                                 ("grasp_of_the_dead_corpse_search_yards", "45", "SF_14"), ("grasp_of_the_dead_corpse_radius_yards", "10", "SF_15")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/Witchdoctor_GraspOfTheDead.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("grasp_of_the_dead_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_pct", "own"), ("", "dot_duration_seconds", "own"), ("", "slow_pct", "own"),
                                    ("Groping Eels", "damage_pct", "own"), ("Groping Eels", "slow_pct", "inherited"),
                                    ("Rain of Corpses", "damage_pct", "own"), ("Rain of Corpses", "dot_duration_seconds", "own"),
                                    ("Unbreakable Grasp", "slow_pct", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_GraspOfTheDead.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        def rune_value(n):
            return float(str(sf[n]).split("?")[1].split(":")[0].strip(" ()"))

        self.assertAlmostEqual(number(17), value("", "cost_resource"))
        self.assertAlmostEqual(number(7), value("", "cooldown_seconds"))
        self.assertAlmostEqual(number(16) * 100, value("", "slow_pct"))
        self.assertAlmostEqual(number(18) * number(8) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(8), value("", "dot_duration_seconds"))
        self.assertAlmostEqual((number(18) + rune_value(20)) * number(8) * 100, value("Groping Eels", "damage_pct"))
        self.assertAlmostEqual(number(10) * 100, value("Rain of Corpses", "damage_pct"))
        self.assertAlmostEqual(number(12), value("Rain of Corpses", "dot_duration_seconds"))
        self.assertAlmostEqual((number(16) + rune_value(22)) * 100, value("Unbreakable Grasp", "slow_pct"))
        self.assertAlmostEqual(number(7) - rune_value(9), value("Desperate Grasp", "cooldown_seconds"))
        self.assertAlmostEqual(number(21) * 100, value("Death Is Life", "proc_chance_pct"))
        self.assertAlmostEqual(number(3), tune("grasp_of_the_dead_radius_yards"))
        self.assertAlmostEqual(number(4), tune("grasp_of_the_dead_pulse_seconds"))
        self.assertAlmostEqual(number(6), tune("grasp_of_the_dead_slow_extra_seconds"))
        self.assertAlmostEqual(number(13), tune("grasp_of_the_dead_corpse_seconds"))
        self.assertAlmostEqual(number(14), tune("grasp_of_the_dead_corpse_search_yards"))
        self.assertAlmostEqual(number(15), tune("grasp_of_the_dead_corpse_radius_yards"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        for call in ("GraspOfTheDead::BasePct(spellId)", "GraspOfTheDead::Ground(player, spellId, center);", "GraspOfTheDead::RegisterScripts();"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_cast_hits_nothing_and_the_hands_pulse_on_the_players_queue(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        hands = self.code[self.code.index("void Hands("):self.code.index("void Corpses(")]
        self.assertIn('Numbers::Num(BaseId(Skill), "dot_duration_seconds"), Tune("grasp_of_the_dead_pulse_seconds")', hands)
        self.assertIn('RuneAt(spellId) == Rune::RainOfCorpses ? Numbers::Num(BaseId(Skill), "damage_pct") : Numbers::Num(spellId, "damage_pct")', hands)
        self.assertIn('Combat::Strike(player, enemy, spellId, pct, true);', hands)
        self.assertIn('Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), slow);', hands)
        self.assertIn('Tune("grasp_of_the_dead_radius_yards")', hands)
        after = self.code[self.code.index("void After("):self.code.index("void Hands(")]
        self.assertIn("player->m_Events.AddEventAtOffset(", after)

    def test_rain_of_corpses_falls_on_a_random_enemy_near_the_point(self):
        corpses = self.code[self.code.index("void Corpses("):self.code.index("} // namespace")]
        self.assertIn('Tune("grasp_of_the_dead_corpse_search_yards")', corpses)
        self.assertIn("enemies[PickAt(frand(0.0f, 1.0f), enemies.size())]->GetPosition()", corpses)
        self.assertIn('Tune("grasp_of_the_dead_corpse_radius_yards")', corpses)
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn("if (RuneAt(spellId) == Rune::RainOfCorpses) Corpses(player, spellId, center);", ground)

    def test_death_is_life_raises_one_dog_where_an_enemy_died_in_the_hands(self):
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn("if (RuneAt(spellId) == Rune::DeathIsLife) Watch(player, spellId, center);", ground)
        watch = self.code[self.code.index("void Watch("):self.code.index("} // namespace")]
        self.assertIn('Tune("grasp_of_the_dead_radius_yards")', watch)
        self.assertIn('AreaMs(Numbers::Num(BaseId(Skill), "dot_duration_seconds"), Tune("grasp_of_the_dead_slow_extra_seconds"))', watch)
        deaths = self.code[self.code.index("class Deaths"):self.code.index("void Watch(")]
        self.assertIn("UNITHOOK_ON_UNIT_DEATH", deaths)
        self.assertIn("creature->IsControlledByPlayer()", deaths)
        self.assertIn("creature->IsFriendlyTo(witchDoctor)", deaths)
        self.assertIn("InArea(now, area.until, creature->GetExactDist2d(area.x, area.y), area.radius)", deaths)
        self.assertIn('Rises(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct"))', deaths)
        self.assertIn("Pets::RaiseDogAt(witchDoctor, at)", deaths)
        self.assertIn("witchDoctor->m_Events.AddEventAtOffset(", deaths)

    def test_the_health_globe_is_a_seam_nothing_calls(self):
        self.assertIn("void SpawnGlobe(Player* /*player*/, Position const& /*at*/) {}", self.code)
        callers = [p.name for p in (MODULE / "src").rglob("*.cpp") if "SpawnGlobe(" in p.read_text(encoding="utf-8")
                   and "GraspOfTheDead::SpawnGlobe" in p.read_text(encoding="utf-8")]
        self.assertEqual(callers, [])


if __name__ == "__main__":
    unittest.main()
