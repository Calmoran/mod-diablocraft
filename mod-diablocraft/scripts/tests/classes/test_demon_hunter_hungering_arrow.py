"""Demon Hunter Hungering Arrow and its five runes (src/classes/demon_hunter/dc_demon_hunter_hungering_arrow.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_hungering_arrow/harness.cpp compiles the real
    dc_demon_hunter_hungering_arrow.h with the sheets' own rune names and numbers: each rune name is its rune; the arrow
    that has pierced N enemies hits for the skill's 155% raised by Devouring Arrow's 70% once for each pierce; the next enemy
    it seeks is the nearest one not struck yet inside the radius; the split takes the sheet's three arrows' worth of enemies,
    nearest first, inside the 50 degree cone behind the enemy and the split's radius; the arrow reaches no farther than its
    travel. Ten mutations planted in a scratch copy (two runes share a name, the pierce adds no bonus, adds it once however
    many pierces, the seek goes to the farthest, to an enemy already struck, past the radius, the cone is twice as wide, does
    not wrap a full turn, the split sends more arrows than the sheet says, the travel has no limit) must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of demon_hunter_skill_values.csv for
    Hungering Arrow (or the rune that states it), the generated value map says whose record holds it, and the numbers are the
    researched ones: 155%, a 35% chance to pierce (50% for Puncturing Arrow), 4 Hatred (7 for Serrated Arrow), 3 arrows for
    Shatter Shot, +70% for each pierce of Devouring Arrow, Spray of Teeth's 60% within 10 yards. Every tunable it reads is a row
    of data/tunables/demonhunter.csv with its power-file source, and the numbers of the sheets and the tunables equal the decoded
    Power/DemonHunter_HungeringArrow.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The class's dispatch hands the arrow its two seams, the engine's loader asks the class for the hit, and
    both strike paths tell the class whether the hit was a critical one.

What it does not prove: anything on a running server. The shot, the pierces, the split and the burst are
docs/test-diablocraft-vawmy.6.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_hungering_arrow.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_hungering_arrow.h"
SEEK = "src/classes/demon_hunter/dc_demon_hunter_seek.h"
SOURCES = [HEADER, SEEK, "tests/demon_hunter_hungering_arrow/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_hungering_arrow.cpp"
SKILL = "Hungering Arrow"


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
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_hungering_arrow/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "damage_pct"), value("Devouring Arrow", "damage_bonus_pct"),
                         value("Shatter Shot", "projectile_count"), tune("hungering_arrow_seek_after_pierce_yards"),
                         tune("hungering_arrow_shatter_seek_yards"), tune("hungering_arrow_shatter_cone_degrees"),
                         tune("hungering_arrow_travel_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 27, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, "return Rune::ShatterShot;", "return Rune::DevouringArrow;")),
            ("the pierce adds no bonus", (HEADER, "return basePct * (1.0 + bonusPct * pierces / 100.0);", "return basePct;")),
            ("the bonus is added once however many pierces",
             (HEADER, "return basePct * (1.0 + bonusPct * pierces / 100.0);", "return basePct * (1.0 + bonusPct / 100.0);")),
            ("the seek goes to the farthest", (SEEK, "return distances[a] < distances[b];", "return distances[a] > distances[b];")),
            ("the seek goes to an enemy already struck", (SEEK, "if (!struck[i] && distances[i] <= radius", "if (distances[i] <= radius")),
            ("the seek goes past the radius", (SEEK, "distances[i] <= radius && InCone", "InCone")),
            ("the cone is twice as wide", (SEEK, "<= coneDegrees * Pi / 360.0;", "<= coneDegrees * Pi / 180.0;")),
            ("the cone does not wrap a full turn", (SEEK, "std::fabs(std::remainder(bearing - heading, 2.0 * Pi))", "std::fabs(bearing - heading)")),
            ("the split sends more arrows than the sheet says", (SEEK, "inside.resize(count);", "inside.resize(inside.size());")),
            ("the travel has no limit", (HEADER, "return travel <= 0 || distanceFromCaster <= travel;", "return true;")),
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
        self.assertEqual(runes(), ["Serrated Arrow", "Shatter Shot", "Devouring Arrow", "Puncturing Arrow", "Spray of Teeth"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("generated_resource", "damage_pct", "proc_chance_pct")], [4, 155, 35])
        self.assertEqual(value("Serrated Arrow", "generated_resource"), 7)
        self.assertEqual(value("Shatter Shot", "projectile_count"), 3)
        self.assertEqual(value("Devouring Arrow", "damage_bonus_pct"), 70)
        self.assertEqual(value("Puncturing Arrow", "proc_chance_pct"), 50)
        self.assertEqual([value("Spray of Teeth", t) for t in ("damage_pct", "radius_yards")], [60, 10])

    def test_the_tunables_are_the_power_files_and_nobody_has_set_them(self):
        rows = tunables()
        for name, number, source in (("hungering_arrow_seek_after_pierce_yards", "20", "SF_13"),
                                     ("hungering_arrow_shatter_seek_yards", "11", "SF_4"),
                                     ("hungering_arrow_shatter_cone_degrees", "50", "SF_19"),
                                     ("hungering_arrow_travel_yards", "90", "SF_14")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_HungeringArrow.pow", rows[name]["notes"])
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("hungering_arrow_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "proc_chance_pct", "damage_bonus_pct", "projectile_count", "radius_yards"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_pct"), ("", "proc_chance_pct"), ("Puncturing Arrow", "proc_chance_pct"),
                            ("Shatter Shot", "projectile_count"), ("Devouring Arrow", "damage_bonus_pct"),
                            ("Spray of Teeth", "damage_pct"), ("Spray of Teeth", "radius_yards")):
            with self.subTest(rune=rune, token=token):
                self.assertEqual(mapped[(rune, token, "")]["origin"], "own")

    def test_the_arrow_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_HungeringArrow.pow"))["sf"]

        def number(n):
            return float(sf[n])

        self.assertAlmostEqual(number(0) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(17) * 100, value("", "proc_chance_pct"))
        # SF_15 is "Rune_D ? 0.15 : 0": Puncturing Arrow's increase over the base chance.
        increase = float(sf[15].split("?")[1].split(":")[0])
        self.assertAlmostEqual((number(17) + increase) * 100, value("Puncturing Arrow", "proc_chance_pct"))
        self.assertAlmostEqual(number(20), value("", "generated_resource"))
        self.assertAlmostEqual(number(20) + number(8), value("Serrated Arrow", "generated_resource"))
        self.assertAlmostEqual(number(9) + 1, value("Shatter Shot", "projectile_count"))
        self.assertAlmostEqual(number(10) * 100, value("Devouring Arrow", "damage_bonus_pct"))
        self.assertAlmostEqual(number(11) * 100, value("Spray of Teeth", "damage_pct"))
        self.assertAlmostEqual(number(12), value("Spray of Teeth", "radius_yards"))
        for n, name in ((13, "hungering_arrow_seek_after_pierce_yards"), (4, "hungering_arrow_shatter_seek_yards"),
                        (19, "hungering_arrow_shatter_cone_degrees"), (14, "hungering_arrow_travel_yards")):
            self.assertAlmostEqual(number(n), tune(name), msg=name)

    def test_the_hit_is_the_skills_for_every_rune_and_the_burst_is_the_runes_own(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('return Numbers::Get(BaseId(Skill), "damage_pct");', text)
        self.assertIn('auto const pct = Numbers::Own(spellId, "damage_pct");', text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        engine = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat/dc_combat_internal.h",
                                                                 *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.engine = re.sub(r"\s+", " ", engine)

    def test_the_dispatch_hands_the_arrow_its_seams(self):
        self.assertEqual(self.dispatch.count("if (auto arrow = HungeringArrow::BasePct(spellId)) return arrow;"), 1)
        self.assertEqual(self.dispatch.count("HungeringArrow::Landed(player, target, spellId, critical);"), 1)

    def test_the_loader_asks_the_class_for_the_hit(self):
        self.assertEqual(self.engine.count("DemonHunter::BasePct(ability.id)"), 1)
        self.assertLess(self.engine.index("Necromancer::BasePct(ability.id)"), self.engine.index("DemonHunter::BasePct(ability.id)"))
        self.assertLess(self.engine.index("DemonHunter::BasePct(ability.id)"), self.engine.index("DamageWaits(ability.id)"))

    def test_both_strike_paths_tell_the_class_whether_the_hit_was_critical(self):
        self.assertIn("DemonHunter::Landed(player, target, shell.spellId, hit.critical);", self.engine)
        self.assertIn("DemonHunter::Landed(player, target, spellId, hit.critical);", self.engine)

    def test_a_chain_starts_only_from_the_arrows_own_hit_and_a_burst_starts_nothing(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("if (bursting || !player || !target || !row) return;", landed)
        self.assertIn("if (!chaining) { Scope scope(chaining);", landed)
        self.assertLess(landed.index("Scope scope(chaining);"), landed.index("Burst(player, spellId, target);"))
        self.assertIn("if (rune == Rune::SprayOfTeeth && critical) Burst(player, spellId, target);", landed)
        self.assertIn("Scope scope(bursting);", self.code[self.code.index("void Burst("):])

    def test_the_burst_is_not_an_attack_of_its_own(self):
        # StrikeArea would call Connected again and pay the Hatred a second time.
        burst = self.code[self.code.index("void Burst("):self.code.index("bool Is(")]
        self.assertNotIn("StrikeArea", burst)
        self.assertIn("Combat::Strike(player, enemy, spellId, pct);", burst)

    def test_the_pierce_rolls_after_every_enemy_and_stops_when_nothing_is_left(self):
        pierce = self.code[self.code.index("void Pierce("):self.code.index("void Split(")]
        self.assertIn("roll_chance_f(float(chance))", pierce)
        self.assertIn("PiercedDamagePct(damage, bonus, pierces)", pierce)
        self.assertIn("if (next.empty() || !Combat::Strike(", pierce)
        self.assertIn('rune == Rune::DevouringArrow ? Numbers::Num(spellId, "damage_bonus_pct") : 0.0', pierce)

    def test_shatter_shot_splits_only_on_the_first_enemys_pierce(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("if (rune == Rune::ShatterShot) Split(player, spellId, target); else Pierce(player, spellId, rune, target);", landed)
        split = self.code[self.code.index("void Split("):self.code.index("void Burst(")]
        self.assertLess(split.index("roll_chance_f"), split.index("Combat::Strike"))
        self.assertIn('std::size_t(Numbers::Num(spellId, "projectile_count"))', split)
        self.assertIn("player->GetAngle(first)", split)


if __name__ == "__main__":
    unittest.main()
