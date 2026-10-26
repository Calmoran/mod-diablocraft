"""Witch Doctor Sacrifice and its five runes (src/classes/witch_doctor/dc_witch_doctor_sacrifice.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_sacrifice/harness.cpp compiles the real dc_witch_doctor_sacrifice.h with the sheets'
    own rune names and numbers: each rune name is its rune; one Zombie Dog is banished and every dog for For the Master; Pride pays 280 Mana for
    each dog; a roll under Next of Kin's 35 brings a dog back; Provoke the Pack's bonus lasts its 5 seconds from the cast. Seven mutations
    planted in a scratch copy (two runes share a name, For the Master banishes one, the others banish them all, Pride pays once, the
    resurrection roll is turned round, the bonus is not its seconds, outlasts them) must each make it fail.
  * **The record needs no change.** The cast is the engine's ground cast (a `ground_area` row of skill_targeting.csv); the radius and each
    rune's school are the record's, and the skill has no cost and no cooldown.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of witch_doctor_skill_values.csv for Sacrifice (or
    the rune that states it): 1090% in 12 yards, For the Master's 1300%, Black Blood's 3 seconds, Pride's 280 Mana, Next of Kin's 35%,
    Provoke the Pack's 20% for 5 seconds; the one tunable is a row of data/tunables/witchdoctor.csv, and the numbers equal the decoded
    Power/Witchdoctor_Sacrifice.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the damage, ground and damage-done seams and the engine calls the last beside the other classes';
    the cast banishes through the pets' own SacrificeDog, and does nothing when no dog stands; the explosion falls after the file's delay on
    the player's own queue; Black Blood stuns with the stun factor; Next of Kin raises a dog where the old one stood.

What it does not prove: anything on a running server. The explosion, the stun, the Mana, the returning dog and the bonus are
docs/test-diablocraft-vxrcu.21.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_sacrifice.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_sacrifice.h"
BUCKETS = "src/combat/dc_damage_buckets.h"
SOURCES = [HEADER, BUCKETS, "tests/witch_doctor_sacrifice/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_sacrifice.cpp"
SKILL = "Sacrifice"
RUNES = ["Provoke the Pack", "For the Master", "Black Blood", "Pride", "Next of Kin"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_sacrifice/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("Pride", "gain_resource"), value("Next of Kin", "proc_chance_pct"), value("Provoke the Pack", "duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 11, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Black Blood")\n            return Rune::BlackBlood;',
                                        'if (name == "Black Blood")\n            return Rune::Pride;')),
            ("For the Master banishes one", (HEADER, "return rune == Rune::ForTheMaster ? standing : std::min(standing, 1u);", "return std::min(standing, 1u);")),
            ("the others banish them all", (HEADER, "return rune == Rune::ForTheMaster ? standing : std::min(standing, 1u);", "return standing;")),
            ("Pride pays once", (HEADER, "return perDog > 0 ? perDog * dogs : 0.0;", "return perDog > 0 ? perDog : 0.0;")),
            ("the resurrection roll is turned round", (HEADER, "return chancePct > 0 && roll < chancePct;", "return chancePct > 0 && roll >= chancePct;")),
            ("the bonus is not its seconds", (HEADER, "nowMs + static_cast<std::uint64_t>(seconds * 1000.0 + 0.5)", "nowMs + static_cast<std::uint64_t>(seconds + 0.5)")),
            ("the bonus outlasts its seconds", (HEADER, "return nowMs < untilMs;", "return nowMs <= untilMs;")),
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

    def test_the_record_is_the_engines_ground_cast_with_no_cost_or_cooldown(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["radius_yards"]), ("ground_area", "12"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])
        skill = next(r for r in read(D3 / "witch_doctor_skills.csv") if r["skill_name"] == SKILL)
        self.assertEqual((skill["resource_cost"], skill["cooldown_seconds"]), ("", ""))

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", n) for n in ("damage_pct", "radius_yards")], [1090, 12])
        self.assertEqual([value("Provoke the Pack", n) for n in ("damage_bonus_pct", "duration_seconds")], [20, 5])
        self.assertEqual(value("For the Master", "damage_pct"), 1300)
        self.assertEqual(value("Black Blood", "stun_duration_seconds"), 3)
        self.assertEqual(value("Pride", "gain_resource"), 280)
        self.assertEqual(value("Next of Kin", "proc_chance_pct"), 35)

    def test_the_tunable(self):
        row = tunables()["sacrifice_explode_delay_seconds"]
        self.assertEqual((row["d3_value"], row["value"]), ("0.2", ""))
        self.assertIn("SF_3", row["notes"])
        self.assertIn("Power/Witchdoctor_Sacrifice.pow", row["notes"])
        self.assertNotIn("placeholder", row["notes"].lower())

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("sacrifice_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()>-]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "radius_yards", "stun_duration_seconds", "gain_resource", "proc_chance_pct", "duration_seconds",
                                  "damage_bonus_pct"})
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "damage_pct", "own"), ("", "radius_yards", "own"), ("Provoke the Pack", "damage_pct", "inherited"),
                                    ("Provoke the Pack", "damage_bonus_pct", "own"), ("Provoke the Pack", "duration_seconds", "own"),
                                    ("For the Master", "damage_pct", "own"), ("Black Blood", "stun_duration_seconds", "own"),
                                    ("Pride", "gain_resource", "own"), ("Next of Kin", "proc_chance_pct", "own")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token)]["origin"], origin)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_Sacrifice.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(8) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(2), value("", "radius_yards"))
        self.assertAlmostEqual(number(4) * 100, value("Provoke the Pack", "damage_bonus_pct"))
        self.assertAlmostEqual(number(5), value("Provoke the Pack", "duration_seconds"))
        self.assertAlmostEqual(number(6) * 100, value("For the Master", "damage_pct"))
        self.assertAlmostEqual(number(7), value("Black Blood", "stun_duration_seconds"))
        self.assertAlmostEqual(number(9), value("Pride", "gain_resource"))
        self.assertAlmostEqual(number(10) * 100, value("Next of Kin", "proc_chance_pct"))
        self.assertAlmostEqual(number(3), tune("sacrifice_explode_delay_seconds"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))
        engine = (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8")
        self.engine = re.sub(r"\s+", " ", engine)

    def test_the_dispatch_answers_the_seams_and_the_engine_calls_the_damage_one(self):
        self.assertEqual(self.dispatch.count("Sacrifice::BasePct(spellId)"), 1)
        self.assertEqual(self.dispatch.count("Sacrifice::Ground(player, spellId, center);"), 1)
        self.assertEqual(self.dispatch.count("Sacrifice::Multipliers(player, out);"), 1)
        self.assertEqual(self.engine.count("WitchDoctor::Multipliers(player, target, shell.spellId, hit.factors);"), 1)
        self.assertLess(self.engine.index("Necromancer::Multipliers(player, target, shell.spellId, hit.factors);"),
                        self.engine.index("WitchDoctor::Multipliers(player, target, shell.spellId, hit.factors);"))

    def test_the_cast_needs_a_dog_which_it_banishes_and_hits_nothing_itself(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        ground = self.code[self.code.index("void Ground("):self.code.index("void Multipliers(")]
        self.assertIn('Sacrificed(rune, Minions::Alive(player, "dog"))', ground)
        self.assertIn("Pets::SacrificeDog(player)", ground)
        self.assertIn("if (banished.empty()) return;", ground)
        self.assertLess(ground.index("if (banished.empty()) return;"), ground.index("player->m_Events.AddEventAtOffset("))
        self.assertIn('Tune("sacrifice_explode_delay_seconds")', ground)

    def test_each_rune_does_its_one_thing(self):
        explode = self.code[self.code.index("void Explode("):self.code.index("} // namespace")]
        self.assertIn('Combat::Enemies(player, spellId, center, Numbers::Num(spellId, "radius_yards"))', explode)
        self.assertIn("for (unsigned dog = 0; dog < dogs; ++dog) Combat::Strike(player, enemy, spellId, pct);", explode)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', explode)
        ground = self.code[self.code.index("void Ground("):self.code.index("void Multipliers(")]
        self.assertIn('BonusUntil(Now(), Numbers::Num(spellId, "duration_seconds")), Numbers::Num(spellId, "damage_bonus_pct")', ground)
        self.assertIn('PrideMana(Numbers::Num(spellId, "gain_resource"), dogs)', ground)
        self.assertIn('Resurrects(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct"))', ground)
        self.assertIn('Minions::Raise(player, "zombie_dog", at);', ground)
        multipliers = self.code[self.code.index("void Multipliers("):]
        self.assertIn('AddFactor(out, "Provoke the Pack", bonus.pct);', multipliers)
        self.assertIn("BonusOn(Now(), bonus.until)", multipliers)


if __name__ == "__main__":
    unittest.main()
