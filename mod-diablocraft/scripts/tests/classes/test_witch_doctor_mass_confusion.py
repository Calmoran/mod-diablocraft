"""Witch Doctor Mass Confusion and its five runes (src/classes/witch_doctor/dc_witch_doctor_mass_confusion.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_mass_confusion/harness.cpp compiles the real dc_witch_doctor_mass_confusion.h and
    the shared arithmetic with the sheets' own rune names and numbers: each rune name is its rune; an enemy whose roll is under the half the
    confusion takes is taken; Mass Hysteria stuns as many of the others as it has, up to 10; the spirit's 0.3 a frame is 18 yards a second, so
    a quarter second is 4.5 yards; it walks towards the enemy, stops at one nearer than a step and keeps its direction; its ticks make its 400%
    a second over the 12 seconds. Eight mutations planted in a scratch copy (two runes share a name, the roll is turned round, the stun has
    no count, the speed is a second's not a frame's, the spirit overshoots an enemy, walks away from it, its ticks are lost, a tick carries the
    whole second) must each make it fail.
  * **The record needs no change.** The cast is the engine's self-centred area cast (a `self_aoe` row of skill_targeting.csv, radius 30); the
    cooldown, Unstable Realm's shorter one and each rune's school are the record's (test_witch_doctor_records.py).
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of witch_doctor_skill_values.csv for Mass Confusion
    (or the rune that states it): 12 seconds of charm, Paranoia's 30% for 12 seconds, Mass Hysteria's 10 enemies for 3 seconds, Mass
    Hallucination's 400%; every tunable is a row of data/tunables/witchdoctor.csv, and the numbers equal the decoded
    Power/Witchdoctor_MassConfusion.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the damage and cast seams; each enemy in the area rolls the proportion and is charmed, or confused
    where the charm cannot hold; the enemies it missed are the ones Mass Hysteria stuns, with the stun factor; the spirit walks on the
    player's own queue.

What it does not prove: anything on a running server. The charm, the confusion, the weakness, the stun and the spirit are
docs/test-diablocraft-vxrcu.22.md's, live; Devolution's Zombie Dog is docs/test-diablocraft-vxrcu.37.md's.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_mass_confusion.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_mass_confusion.h"
CLOCK = "src/classes/witch_doctor/dc_witch_doctor_clock.h"
PICK = "src/classes/witch_doctor/dc_witch_doctor_pick.h"
PERIODIC = "src/combat/dc_periodic_strike.h"
SOURCES = [HEADER, CLOCK, PICK, PERIODIC, "tests/witch_doctor_mass_confusion/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_mass_confusion.cpp"
SKILL = "Mass Confusion"
RUNES = ["Paranoia", "Mass Hysteria", "Mass Hallucination", "Unstable Realm", "Devolution"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_mass_confusion/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("mass_confusion_affected_proportion"), value("Mass Hysteria", "target_count"), value("", "charm_duration_seconds"),
                         tune("mass_confusion_spirit_tick_seconds"), tune("mass_confusion_spirit_speed_per_frame"),
                         value("Mass Hallucination", "damage_pct"), value("Devolution", "proc_chance_pct")]
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
            ("two runes share a name", (HEADER, 'if (name == "Mass Hysteria")\n            return Rune::MassHysteria;',
                                        'if (name == "Mass Hysteria")\n            return Rune::Paranoia;')),
            ("the roll is turned round", (HEADER, "return proportion > 0 && roll < proportion;", "return proportion > 0 && roll >= proportion;")),
            ("the stun has no count", (HEADER, "return std::min(unaffected, most);", "return unaffected;")),
            ("the speed is a second's not a frame's", (HEADER, "speedPerFrame * 60.0 * tickSeconds", "speedPerFrame * tickSeconds")),
            ("the spirit overshoots an enemy", (HEADER, "if (distance <= step)\n            return to;", "if (false)\n            return to;")),
            ("the spirit walks away from the enemy", (HEADER, "return {from.x + dx / distance * step, from.y + dy / distance * step};",
                                                       "return {from.x - dx / distance * step, from.y - dy / distance * step};")),
            ("the spirit's ticks are lost", (PERIODIC, "std::floor(seconds / tickSeconds + 1e-9)", "std::floor(seconds / tickSeconds - 0.5)")),
            ("the confusion counts for no time", (HEADER, "return seconds > 0 ? std::uint64_t(seconds * 1000.0 + 0.5) : 0;", "return 0;")),
            ("a death after the confusion still counts", (HEADER, "return nowMs < untilMs;", "return true;")),
            ("a roll at the chance leaves a dog", (HEADER, "return chancePct > 0 && roll < chancePct;", "return chancePct > 0 && roll <= chancePct;")),
            ("a roll above the chance leaves a dog", (HEADER, "return chancePct > 0 && roll < chancePct;", "return chancePct > 0;")),
            ("a tick carries the whole second", (CLOCK, "return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;",
                                                 "return perSecond > 0 && tickSeconds > 0 ? perSecond : 0.0;")),
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

    def test_the_record_is_the_engines_self_area_cast(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["radius_yards"]), ("self_aoe", "30"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", n) for n in ("cooldown_seconds", "charm_duration_seconds")], [60, 12])
        self.assertEqual([value("Paranoia", n) for n in ("enemy_damage_pct", "duration_seconds")], [30, 12])
        self.assertEqual([value("Mass Hysteria", n) for n in ("target_count", "stun_duration_seconds")], [10, 3])
        self.assertEqual(value("Mass Hallucination", "damage_pct"), 400)
        self.assertEqual(value("Unstable Realm", "cooldown_seconds"), 30)
        self.assertEqual(value("Devolution", "proc_chance_pct"), 100)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("mass_confusion_affected_proportion", "0.5", "SF_2"), ("mass_confusion_radius_yards", "30", "SF_1"),
                                 ("mass_confusion_spirit_tick_seconds", "0.25", "SF_9"), ("mass_confusion_spirit_radius_yards", "8", "SF_10"),
                                 ("mass_confusion_spirit_speed_per_frame", "0.3", "SF_16")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/Witchdoctor_MassConfusion.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("mass_confusion_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"charm_duration_seconds", "enemy_damage_pct", "duration_seconds", "target_count", "stun_duration_seconds",
                                  "damage_pct", "proc_chance_pct"})
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token in (("", "charm_duration_seconds"), ("Paranoia", "enemy_damage_pct"), ("Paranoia", "duration_seconds"),
                            ("Mass Hysteria", "target_count"), ("Mass Hysteria", "stun_duration_seconds"), ("Mass Hallucination", "damage_pct"), ("Devolution", "proc_chance_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token)]["origin"], "own")

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_MassConfusion.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(0), value("", "charm_duration_seconds"))
        self.assertAlmostEqual(number(14), value("", "cooldown_seconds"))
        self.assertAlmostEqual(number(14) - 30, value("Unstable Realm", "cooldown_seconds"))
        self.assertAlmostEqual(number(3) * 100, value("Paranoia", "enemy_damage_pct"))
        self.assertAlmostEqual(number(4), value("Mass Hysteria", "target_count"))
        self.assertAlmostEqual(number(6), value("Mass Hysteria", "stun_duration_seconds"))
        self.assertAlmostEqual(number(11) * 100, value("Mass Hallucination", "damage_pct"))
        self.assertAlmostEqual(number(18), value("Devolution", "proc_chance_pct"))
        for name, n in (("mass_confusion_affected_proportion", 2), ("mass_confusion_radius_yards", 1), ("mass_confusion_spirit_tick_seconds", 9),
                        ("mass_confusion_spirit_radius_yards", 10), ("mass_confusion_spirit_speed_per_frame", 16)):
            self.assertAlmostEqual(number(n), tune(name), msg=name)
        # The spirit lasts the confusion: SF_8 is SF_0.
        self.assertEqual(str(sf[8]).strip(), "SF_0")


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("MassConfusion::BasePct(spellId)"), 1)
        self.assertEqual(self.dispatch.count("MassConfusion::Cast(player, spellId, targets);"), 1)
        self.assertEqual(self.dispatch.count("MassConfusion::RegisterScripts();"), 1)

    def test_devolution_marks_the_enemies_taken_and_a_death_raises_one_dog(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("if (rune == Rune::Devolution) Watch(player, enemy, spellId, seconds);", cast)
        self.assertEqual(self.code.count("Watch(player, enemy"), 1)
        deaths = self.code[self.code.index("class Deaths"):self.code.index("void Watch(")]
        self.assertIn("UNITHOOK_ON_UNIT_DEATH", deaths)
        self.assertIn("confused.erase(found);", deaths)
        self.assertIn("!Confused(Now(), held.until)", deaths)
        self.assertIn('Rises(frand(0.0f, 100.0f), Numbers::Num(held.spellId, "proc_chance_pct"))', deaths)
        self.assertEqual(deaths.count("Pets::RaiseDogAt(witchDoctor, at)"), 1)
        self.assertIn("witchDoctor->m_Events.AddEventAtOffset(", deaths)
        self.assertIn("new Deaths();", self.code)

    def test_each_enemy_rolls_the_proportion_and_is_charmed_or_confused(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('Affected(frand(0.0f, 1.0f), Tune("mass_confusion_affected_proportion"))', cast)
        self.assertIn("missed.push_back(enemy);", cast)
        self.assertIn("missed.push_back(enemy); continue; } if (!CharmEffect::Apply(player, enemy, spellId, seconds)) Confuse(player, enemy, seconds);", cast)
        self.assertIn('Numbers::Num(BaseId(Skill), "charm_duration_seconds")', cast)
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_each_rune_does_its_one_thing(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), Numbers::Num(spellId, "duration_seconds"));', cast)
        self.assertIn('ToStun(unsigned(missed.size()), unsigned(Numbers::Num(spellId, "target_count")))', cast)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', cast)
        self.assertIn("Rampage(player, spellId, walk);", cast)
        rampage = self.code[self.code.index("void Rampage("):self.code.index("} // namespace")]
        self.assertIn("player->m_Events.AddEventAtOffset(", rampage)
        self.assertIn('Tune("mass_confusion_radius_yards")', rampage)
        self.assertIn('Tune("mass_confusion_spirit_radius_yards")', rampage)
        self.assertIn('StepYards(Tune("mass_confusion_spirit_speed_per_frame"), tick)', rampage)
        self.assertIn('PerTick(Numbers::Num(spellId, "damage_pct"), tick), true);', rampage)


if __name__ == "__main__":
    unittest.main()
