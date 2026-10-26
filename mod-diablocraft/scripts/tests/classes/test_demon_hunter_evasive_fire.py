"""Demon Hunter Evasive Fire and its five runes (src/classes/demon_hunter/dc_demon_hunter_evasive_fire.h and .cpp, and the
timed armor in dc_demon_hunter_buffs.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_evasive_fire/harness.cpp compiles the real
    dc_demon_hunter_evasive_fire.h, dc_demon_hunter_seek.h and dc_demon_hunter_buffs.h with the sheets' own rune names and numbers:
    each rune name is its rune; Hardened and Focus do not backflip and the others do; an enemy sets off the backflip when it is
    inside the search radius and half the search cone to either side of the facing, and one that qualifies is enough; the bolts reach
    the enemy aimed at and the nearest two beside it inside the spread cone; Hardened's armor is one stack that lasts its seconds and
    restarts, and starts again from one once it ran out. Nine mutations planted in a scratch copy (two runes share a name, the
    skill flips as Hardened, the trigger has no radius, no cone, the cone is twice as wide, the bolts go to the farthest, ignore the
    spread, the armor never ends or stacks) must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads by name is a row of demon_hunter_skill_values.csv for Evasive
    Fire (or the rune that states it), the generated value map says whose record holds it, and the numbers are the researched ones: 4
    Hatred (7 for Focus), 200% to the enemy aimed at and 100% to two others (Covering Fire 200%), a 5 yard backflip (15 for Surge),
    Hardened's 25% armor for 3 seconds, Parting Gift's 150% in 12 yards after 0.6 seconds. Every tunable it reads is a row of
    data/tunables/demonhunter.csv, and the sheet's and the tunables' numbers equal the decoded Power/X1_DemonHunter_EvasiveFire.pow
    (skipped where the game archives are not on this machine).
  * **The wiring.** The class's dispatch hands the skill its three seams after the others', the cast and the impact seams are called
    from the engine in the order the engine's own hits follow, the bolts at the enemy aimed at fall through to the engine's hit and
    the other bolts are the class's own, and the backflip rides the engine's pull.

What it does not prove: anything on a running server. The backflip, the bolts, the armor and the bomb are
docs/test-diablocraft-vawmy.9.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_evasive_fire.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_evasive_fire.h"
SEEK = "src/classes/demon_hunter/dc_demon_hunter_seek.h"
BUFFS = "src/classes/demon_hunter/dc_demon_hunter_buffs.h"
SOURCES = [HEADER, SEEK, BUFFS, "tests/demon_hunter_evasive_fire/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_evasive_fire.cpp"
SKILL = "Evasive Fire"


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_evasive_fire/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [tune("evasive_fire_flip_search_yards"), tune("evasive_fire_flip_search_degrees"),
                         tune("evasive_fire_enemies_hit"), tune("evasive_fire_spread_degrees"),
                         value("Hardened", "armor_pct"), value("Hardened", "duration_seconds")]
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
            ("two runes share a name", (HEADER, "return Rune::Surge;", "return Rune::Focus;")),
            ("the skill flips as Hardened does not", (HEADER, "return rune != Rune::Hardened && rune != Rune::Focus;", "return true;")),
            ("Hardened flips too", (HEADER, "return rune != Rune::Hardened && rune != Rune::Focus;", "return rune != Rune::Focus;")),
            ("the trigger has no radius", (HEADER, "if (distances[i] <= radius && InCone(", "if (InCone(")),
            ("the trigger has no cone", (HEADER, "distances[i] <= radius && InCone(facing, bearings[i], coneDegrees)", "distances[i] <= radius")),
            ("the cone is twice as wide", (SEEK, "<= coneDegrees * Pi / 360.0;", "<= coneDegrees * Pi / 180.0;")),
            ("the bolts go to the farthest", (SEEK, "return distances[a] < distances[b];", "return distances[a] > distances[b];")),
            ("the armor never ends", (BUFFS, "return Over(held, now) ? 0.0 : perStack * held.stacks;", "return perStack * held.stacks;")),
            ("a second cast does not restart the time", (BUFFS, "held.until = now + ms;", "held.until = held.until ? held.until : now + ms;")),
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
        self.assertEqual(runes(), ["Hardened", "Covering Fire", "Parting Gift", "Surge", "Focus"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual(value("", "generated_resource"), 4)
        self.assertEqual([value("", "damage_pct", q) for q in ("primary", "other")], [200, 100])
        self.assertEqual(value("", "distance_yards"), 5)
        self.assertEqual([value("Hardened", t) for t in ("armor_pct", "duration_seconds")], [25, 3])
        self.assertEqual(value("Covering Fire", "damage_pct"), 200)
        self.assertEqual([value("Parting Gift", t) for t in ("damage_pct", "radius_yards", "delay_seconds")], [150, 12, 0.6])
        self.assertEqual(value("Surge", "distance_yards"), 15)
        self.assertEqual(value("Focus", "generated_resource"), 7)

    def test_the_tunables_are_the_power_files_and_nobody_has_set_them(self):
        rows = tunables()
        for name, number, source in (("evasive_fire_flip_search_yards", "25", "SF_5"), ("evasive_fire_flip_search_degrees", "60", "SF_6"),
                                     ("evasive_fire_enemies_hit", "3", "SF_24"), ("evasive_fire_spread_degrees", "50", "SF_26")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/X1_DemonHunter_EvasiveFire.pow", rows[name]["notes"])
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        self.assertEqual(read_tunables, {name for name in tunables() if name.startswith("evasive_fire_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "armor_pct", "duration_seconds", "distance_yards", "radius_yards", "delay_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]): r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "damage_pct", "primary"), ("", "damage_pct", "other"), ("", "distance_yards", ""),
                                       ("Hardened", "armor_pct", ""), ("Hardened", "duration_seconds", ""),
                                       ("Covering Fire", "damage_pct", ""), ("Parting Gift", "damage_pct", ""),
                                       ("Parting Gift", "radius_yards", ""), ("Parting Gift", "delay_seconds", ""),
                                       ("Surge", "distance_yards", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertEqual(mapped[(rune, token, qualifier)]["origin"], "own")

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/X1_DemonHunter_EvasiveFire.pow"))["sf"]

        def number(n):
            return float(sf[n])

        def rune_part(n):
            return float(sf[n].split("?")[1].split(":")[0])

        self.assertAlmostEqual(number(9) * 100, value("", "damage_pct", "primary"))
        self.assertAlmostEqual(number(23) * 100, value("", "damage_pct", "other"))
        self.assertAlmostEqual(number(22) * 100, value("Covering Fire", "damage_pct"))
        self.assertAlmostEqual(number(4), value("", "generated_resource"))
        self.assertAlmostEqual(number(4) + rune_part(10), value("Focus", "generated_resource"))
        self.assertAlmostEqual(number(1), value("", "distance_yards"))
        self.assertAlmostEqual(number(1) + rune_part(12), value("Surge", "distance_yards"))
        self.assertAlmostEqual(number(16) * 100, value("Hardened", "armor_pct"))
        self.assertAlmostEqual(number(17), value("Hardened", "duration_seconds"))
        self.assertAlmostEqual(number(28) * 100, value("Parting Gift", "damage_pct"))
        self.assertAlmostEqual(number(29), value("Parting Gift", "radius_yards"))
        self.assertAlmostEqual(number(30), value("Parting Gift", "delay_seconds"))
        for n, name in ((5, "evasive_fire_flip_search_yards"), (6, "evasive_fire_flip_search_degrees"),
                        (24, "evasive_fire_enemies_hit"), (26, "evasive_fire_spread_degrees")):
            self.assertAlmostEqual(number(n), tune(name), msg=name)

    def test_the_primary_bolt_is_the_skills_primary_for_every_rune(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('return Numbers::Get(BaseId(Skill), "damage_pct", "primary");', text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        engine = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat/dc_combat_internal.h",
                                                                 *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.engine = re.sub(r"\s+", " ", engine)

    def test_the_dispatch_hands_the_skill_its_seams_after_the_others(self):
        self.assertEqual(self.dispatch.count("if (auto fire = EvasiveFire::BasePct(spellId)) return fire;"), 1)
        self.assertLess(self.dispatch.index("Bolas::BasePct(spellId)"), self.dispatch.index("EvasiveFire::BasePct(spellId)"))
        self.assertEqual(self.dispatch.count("EvasiveFire::Casting(player, spellId);"), 1)
        self.assertEqual(self.dispatch.count("return EvasiveFire::Impact(player, target, aimed, cone, spellId) ||"), 1)

    def test_the_engine_calls_the_cast_and_the_impact_in_their_places(self):
        self.assertEqual(self.engine.count("DemonHunter::Casting(player, shell.spellId);"), 1)
        self.assertLess(self.engine.index("Necromancer::Casting(player, shell.spellId);"), self.engine.index("DemonHunter::Casting(player, shell.spellId);"))
        impact = "DemonHunter::Impact(player, target, GetExplTargetUnit(), native, shell.spellId)"
        self.assertEqual(self.engine.count(impact), 1)
        self.assertLess(self.engine.index("Necromancer::Impact(player, target"), self.engine.index(impact))
        self.assertLess(self.engine.index(impact), self.engine.index("ResolveHit(player, target, shell, GetSpellInfo())"))

    def test_the_bolt_at_the_enemy_aimed_at_is_the_engines_and_the_others_are_the_classes(self):
        impact = self.code[self.code.index("bool Impact("):]
        self.assertIn("|| target == aimed) return false;", impact)
        self.assertIn("std::find(beside.begin(), beside.end(), target) != beside.end()", impact)
        self.assertIn('Numbers::Num(spellId, "damage_pct", "other")', impact)
        self.assertIn("RuneOf(row->rune) == Rune::CoveringFire", impact)
        self.assertTrue(impact.rstrip().endswith("return true; } } // namespace DC::Combat::DemonHunter::EvasiveFire"))

    def test_the_backflip_rides_the_engines_pull_and_the_bomb_is_left_where_it_began(self):
        casting = self.code[self.code.index("void Casting("):self.code.index("bool Impact(")]
        self.assertIn("Abilities::Pull(player, to);", casting)
        self.assertIn("player->GetOrientation() + M_PI", casting)
        self.assertIn("if (rune == Rune::PartingGift) LeaveBomb(player, spellId, from);", casting)
        self.assertIn("if (!Backflips(rune)) return;", casting)
        self.assertLess(casting.index("Rune::Hardened"), casting.index("Backflips(rune)"))
        self.assertIn("Buffs::Stack(player, spellId, Stat::Armor, Bucket::Percent", casting)

    def test_the_bolts_beside_are_the_nearest_inside_the_spread(self):
        beside = self.code[self.code.index("std::vector<Unit*> Beside("):self.code.index("void LeaveBomb(")]
        self.assertIn("excluded.push_back(enemy == aimed);", beside)
        self.assertIn('Tune("evasive_fire_spread_degrees")', beside)
        self.assertIn('Tune("evasive_fire_enemies_hit") - 1', beside)


if __name__ == "__main__":
    unittest.main()
