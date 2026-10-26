"""Witch Doctor Wall of Death and its five runes (src/classes/witch_doctor/dc_witch_doctor_wall_of_death.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_wall_of_death/harness.cpp compiles the real dc_witch_doctor_wall_of_death.h
    with the sheets' own rune names and numbers: each rune name is its rune; the wall is a line of the sheet's width with a round
    capsule of the file's radius about it (its middle, ends, sides and rounded corners, for any heading); which enemies are in front
    of it and how far Wall of Zombies shoves them; the ticks make the damage; Fire Wall burns an enemy again only once its burn is
    over. Mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of witch_doctor_skill_values.csv for Wall of Death
    (or the rune that states it) the engine can read, qualified or inherited as the code asks; every tunable is a row of
    data/tunables/witchdoctor.csv; the numbers equal the decoded Power/Witchdoctor_WallOfZombies.pow (skipped where the game archives
    are not on this machine).
  * **The wiring.** The dispatch answers the seams; the cast hits nothing; the wall, the circles and the ring are periodic devices of
    the shared piece with their rune's life; Wall of Zombies shoves the enemies in front; Communing with Spirits chills and
    weakens; Ring of Poison poisons once; Fire Wall burns.

What it does not prove: anything on a running server. The wall, the circles and the runes are docs/test-diablocraft-vxrcu.26.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_wall_of_death.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_wall_of_death.h"
SOURCES = [HEADER, "src/combat/dc_periodic_strike.h", "tests/witch_doctor_wall_of_death/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_wall_of_death.cpp"
SKILL = "Wall of Death"
POWER = "Power/Witchdoctor_WallOfZombies.pow"
RUNES = ["Surrounded by Death", "Ring of Poison", "Communing with Spirits", "Wall of Zombies", "Fire Wall"]


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_wall_of_death/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "radius_yards"), value("Wall of Zombies", "radius_yards"), tune("wall_of_death_capsule_radius_yards"),
                         tune("wall_of_death_tick_seconds"), value("", "damage_pct"), value("", "dot_duration_seconds"),
                         value("Fire Wall", "dot_duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Ring of Poison")\n            return Rune::RingOfPoison;',
                                        'if (name == "Ring of Poison")\n            return Rune::FireWall;')),
            ("the reach is the width", (HEADER, "return width / 2 + capsule;", "return width + capsule;")),
            ("the wall has no capsule", (HEADER, "return std::hypot(along, std::max(0.0, across - width / 2)) <= capsule;",
                                         "return along == 0 && across <= width / 2;")),
            ("the wall's end is square", (HEADER, "return std::hypot(along, std::max(0.0, across - width / 2)) <= capsule;",
                                          "return std::fabs(along) <= capsule && across <= width / 2 + capsule;")),
            ("the wall is as wide as its half", (HEADER, "std::max(0.0, across - width / 2)", "std::max(0.0, across - width / 4)")),
            ("the wall ignores its heading", (HEADER, "return dx * std::cos(heading) + dy * std::sin(heading);", "return dy;")),
            ("an enemy behind is in front", (HEADER, "return alongEnemy < 0 && std::fabs(acrossEnemy) <= width / 2;",
                                             "return std::fabs(acrossEnemy) <= width / 2;")),
            ("an enemy far to a side is in front", (HEADER, "return alongEnemy < 0 && std::fabs(acrossEnemy) <= width / 2;",
                                                    "return alongEnemy < 0;")),
            ("the shove stops at the wall", (HEADER, "return capsule - alongEnemy;", "return -alongEnemy;")),
            ("a tick is the whole damage", (HEADER, "return PeriodicStrike::TickPct(totalPct, PeriodicStrike::Ticks(seconds, tickSeconds));", "return totalPct;")),
            ("Fire Wall never burns again", (HEADER, "return !lastMs || nowMs >= *lastMs + burnMs;", "return !lastMs;")),
            ("Fire Wall burns again at once", (HEADER, "return !lastMs || nowMs >= *lastMs + burnMs;", "return true;")),
            ("Fire Wall burns one tick early", (HEADER, "nowMs >= *lastMs + burnMs", "nowMs + 1 >= *lastMs + burnMs")),
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
        self.assertEqual([value("", "cooldown_seconds"), value("", "radius_yards"), value("", "damage_pct"), value("", "dot_duration_seconds")],
                         [8, 28, 1200, 6])
        self.assertEqual([value("Surrounded by Death", "damage_pct"), value("Surrounded by Death", "dot_duration_seconds")], [1250, 5])
        self.assertEqual([value("Ring of Poison", "duration_seconds"), value("Ring of Poison", "damage_pct"),
                          value("Ring of Poison", "dot_duration_seconds")], [5, 1200, 8])
        self.assertEqual([value("Communing with Spirits", "duration_seconds", "circle"), value("Communing with Spirits", "damage_pct"),
                          value("Communing with Spirits", "chill_pct"), value("Communing with Spirits", "enemy_damage_pct"),
                          value("Communing with Spirits", "duration_seconds", "debuff")], [6, 1200, 60, 25, 3])
        self.assertEqual(value("Wall of Zombies", "radius_yards"), 50)
        self.assertEqual([value("Fire Wall", "radius_yards"), value("Fire Wall", "duration_seconds"), value("Fire Wall", "damage_pct"),
                          value("Fire Wall", "dot_duration_seconds")], [40, 8, 1100, 4])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("wall_of_death_capsule_radius_yards", "6", "SF_4"), ("wall_of_death_tick_seconds", "0.2", "SF_15"),
                                 ("wall_of_death_circle_radius_yards", "15", "SF_3"), ("wall_of_death_ring_tick_seconds", "0.25", "SF_35"),
                                 ("wall_of_death_fire_tick_seconds", "0.25", "SF_34")):
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""))
                self.assertIn(source, rows[name]["notes"])
                self.assertIn(POWER, rows[name]["notes"])
                self.assertNotIn("placeholder", rows[name]["notes"].lower())

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'"(wall_of_death_[a-z_]+)"', text)), {n for n in tunables() if n.startswith("wall_of_death_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"], r["qualifier"]): r["origin"] for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for key, origin in ((("", "damage_pct", ""), "own"), (("", "radius_yards", ""), "own"), (("", "dot_duration_seconds", ""), "own"),
                            (("Surrounded by Death", "damage_pct", ""), "own"), (("Surrounded by Death", "dot_duration_seconds", ""), "own"),
                            (("Ring of Poison", "duration_seconds", ""), "own"), (("Ring of Poison", "damage_pct", ""), "own"),
                            (("Ring of Poison", "dot_duration_seconds", ""), "own"), (("Communing with Spirits", "duration_seconds", "circle"), "own"),
                            (("Communing with Spirits", "duration_seconds", "debuff"), "own"), (("Communing with Spirits", "chill_pct", ""), "own"),
                            (("Communing with Spirits", "enemy_damage_pct", ""), "own"), (("Wall of Zombies", "radius_yards", ""), "own"),
                            (("Wall of Zombies", "damage_pct", ""), "inherited"), (("Wall of Zombies", "dot_duration_seconds", ""), "inherited"),
                            (("Fire Wall", "radius_yards", ""), "own"), (("Fire Wall", "duration_seconds", ""), "own"), (("Fire Wall", "damage_pct", ""), "own"),
                            (("Fire Wall", "dot_duration_seconds", ""), "own")):
            self.assertEqual(mapped[key], origin, key)

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract(POWER))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(13), value("", "cooldown_seconds"))
        self.assertAlmostEqual(number(6), value("", "radius_yards"))
        self.assertAlmostEqual(number(14) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(0), value("", "dot_duration_seconds"))
        self.assertAlmostEqual(number(11) * 100, value("Surrounded by Death", "damage_pct"))
        self.assertAlmostEqual(number(8), value("Surrounded by Death", "dot_duration_seconds"))
        self.assertAlmostEqual(number(26), value("Ring of Poison", "duration_seconds"))
        self.assertAlmostEqual(number(12) * 100, value("Ring of Poison", "damage_pct"))
        self.assertAlmostEqual(number(20), value("Ring of Poison", "dot_duration_seconds"))
        self.assertAlmostEqual(number(29), value("Communing with Spirits", "duration_seconds", "circle"))
        self.assertAlmostEqual(number(16) * 100, value("Communing with Spirits", "damage_pct"))
        self.assertAlmostEqual(number(17) * 100, value("Communing with Spirits", "chill_pct"))
        self.assertAlmostEqual(number(22) * 100, value("Communing with Spirits", "enemy_damage_pct"))
        self.assertAlmostEqual(number(18), value("Communing with Spirits", "duration_seconds", "debuff"))
        self.assertAlmostEqual(number(6) + 22.0, value("Wall of Zombies", "radius_yards"))
        self.assertAlmostEqual(number(10), value("Fire Wall", "radius_yards"))
        self.assertAlmostEqual(number(27), value("Fire Wall", "duration_seconds"))
        self.assertAlmostEqual(number(25) * 100, value("Fire Wall", "damage_pct"))
        self.assertAlmostEqual(number(28), value("Fire Wall", "dot_duration_seconds"))
        for name, n in (("wall_of_death_capsule_radius_yards", 4), ("wall_of_death_tick_seconds", 15), ("wall_of_death_circle_radius_yards", 3),
                        ("wall_of_death_ring_tick_seconds", 35), ("wall_of_death_fire_tick_seconds", 34)):
            self.assertAlmostEqual(number(n), tune(name), msg=name)
        self.assertEqual({number(3), number(7), number(23)}, {tune("wall_of_death_circle_radius_yards")})
        self.assertAlmostEqual(number(31), tune("wall_of_death_capsule_radius_yards"))
        # The file's D damage (SF_24, 10) is not the sheet's: Wall of Zombies keeps the skill's damage, which the sheet states.
        self.assertNotAlmostEqual(number(24) * 100, value("", "damage_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto wall = WallOfDeath::BasePct(spellId)) return wall;"), 1)
        self.assertEqual(self.dispatch.count("WallOfDeath::Ground(player, spellId, center);"), 1)

    def test_the_cast_hits_nothing(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_each_part_is_a_periodic_device_of_the_shared_piece_with_its_runes_life(self):
        device = self.code[self.code.index("GroundDevice::Setup Device("):self.code.index("void Shove(")]
        self.assertIn("device.spec.mode = GroundDevice::Mode::Periodic;", device)
        self.assertIn("device.spec.lifetimeMs = life * 1000.0;", device)
        self.assertIn("device.spec.intervalMs = tickSeconds * 1000.0;", device)
        life = self.code[self.code.index("double LifeSeconds("):self.code.index("GroundDevice::Setup Device(")]
        self.assertIn('Numbers::Num(spellId, "duration_seconds", "circle")', life)
        self.assertIn('case Rune::RingOfPoison: case Rune::FireWall: return Numbers::Num(spellId, "duration_seconds");', life)
        self.assertIn('default: return Numbers::Num(spellId, "dot_duration_seconds");', life)
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn("case Rune::SurroundedByDeath: case Rune::CommuningWithSpirits: Circle(player, spellId, rune, center);", ground)
        self.assertIn("case Rune::RingOfPoison: Ring(player, spellId, rune, center);", ground)
        self.assertIn("default: Raise(player, spellId, rune, center);", ground)

    def test_the_wall_hurts_what_stands_in_it_and_wall_of_zombies_shoves(self):
        raise_ = self.code[self.code.index("void Raise("):self.code.index("void Circle(")]
        self.assertIn('Numbers::Num(spellId, "radius_yards")', raise_)
        self.assertIn('Tune("wall_of_death_capsule_radius_yards")', raise_)
        self.assertIn("if (rune == Rune::WallOfZombies) Shove(player, spellId, center, heading, width, capsule);", raise_)
        self.assertIn("InWall(enemy->GetPositionX() - x, enemy->GetPositionY() - y, heading, width, capsule)", raise_)
        self.assertIn("Combat::Strike(owner, enemy, spellId, pct);", raise_)
        self.assertIn("WallReach(width, capsule)", raise_)
        shove = self.code[self.code.index("void Shove("):self.code.index("void Raise(")]
        self.assertIn("if (InFront(along, Across(dx, dy, heading), width)) Abilities::Knock(player, enemy, KnockYards(along, capsule));", shove)

    def test_fire_wall_burns_and_the_circles_and_ring_part(self):
        raise_ = self.code[self.code.index("void Raise("):self.code.index("void Circle(")]
        self.assertIn("BurnsAgain(", raise_)
        self.assertIn('PeriodicStrike::Start(owner, enemy, spellId, Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "dot_duration_seconds"), Tune("wall_of_death_fire_tick_seconds"));', raise_)
        circle = self.code[self.code.index("void Circle("):self.code.index("void Ring(")]
        self.assertIn('Tune("wall_of_death_circle_radius_yards")', circle)
        self.assertIn('Slow(owner, enemy, Numbers::Num(spellId, "chill_pct"), seconds);', circle)
        self.assertIn('EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), seconds);', circle)
        self.assertIn('Numbers::Num(spellId, "duration_seconds", "debuff")', circle)
        ring = self.code[self.code.index("void Ring("):self.code.index("} // namespace\n") if "} // namespace\n" in self.code else None]
        self.assertIn("if (poisoned->emplace(enemy->GetGUID().GetRawValue(), Now()).second) PeriodicStrike::Start(", ring)
        self.assertIn('Tune("wall_of_death_ring_tick_seconds")', ring)


if __name__ == "__main__":
    unittest.main()
