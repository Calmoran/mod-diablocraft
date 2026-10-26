"""Corpse Explosion and its five runes (src/classes/necromancer/dc_necromancer_corpse_explosion*.h/.cpp, the dispatch in
dc_necromancer.cpp, the cast check in dc_combat.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_corpse_explosion/harness.cpp compiles the real
    dc_necromancer_corpse_explosion_math.h and the shared dc_corpses_math.h with the sheets' own rune names and numbers (the
    corpse cap and lifetime, blank until the designer answers q-1021-35, are set in the harness): each rune name is its rune; Close
    Quarters takes its corpses around the Necromancer and the others around the point aimed at; Shrapnel's cone holds what
    lies ahead of the corpse and no cone means the circle; a corpse pulls toward the nearest enemy inside the radius; Final
    Embrace costs a share for each corpse; a cast takes up to the most corpses within the range, nearest first. Planted
    differences in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_necromancer_corpse_explosion.cpp reads by name is a row of
    necromancer_skill_values.csv for Corpse Explosion (or the rune that states it), the generated value map says whose record
    holds it, and the numbers are the researched ones: 1050% in 20 yards around up to 5 corpses within 11 yards, Close Quarters
    1575%, Bloody Mess 25 yards, Dead Cold 2 seconds. Every tunable is a row of data/tunables/necromancer.csv: the most
    corpses and Final Embrace's cost with their sources, the cone's width a named placeholder.
  * **The wiring.** The cast has no hit of the engine's, refuses with no corpse in reach, and the engine asks the class where
    it asks the Crusader.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_corpse_explosion.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
MATH = "src/classes/necromancer/dc_necromancer_corpse_explosion_math.h"
CORPSES = "src/combat/dc_corpses_math.h"
HARNESS = MODULE / "tests/necromancer_corpse_explosion/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_corpse_explosion.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Corpse Explosion"
TEST_CONE_DEGREES = 90  # the placeholder is blank; the harness is given a width to test the rule with


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "necromancer_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "necromancer_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (MATH, CORPSES)}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    rows = tunables()
    numbers = [float(rows["corpse_explosion_max_corpses"]["d3_value"]), value("", "radius_yards", "corpse_range"),
               value("", "radius_yards", "explosion"), float(rows["final_embrace_life_cost_pct"]["d3_value"]),
               TEST_CONE_DEGREES] + runes()
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
            ("two runes share a name", (MATH, 'if (name == "Dead Cold")\n            return Rune::DeadCold;', 'if (name == "Dead Cold")\n            return Rune::Shrapnel;')),
            ("every rune takes near the Necromancer", (MATH, "return rune == Rune::CloseQuarters;", "return rune != Rune::None;")),
            ("Close Quarters takes near the point", (MATH, "return rune == Rune::CloseQuarters;", "return false;")),
            ("the cone has no limit", (MATH, "return cosine >= std::cos(", "return true || cosine >= std::cos(")),
            ("the cone is twice as wide", (MATH, "std::cos(degrees / 2.0 *", "std::cos(degrees *")),
            ("the cone is half as wide", (MATH, "std::cos(degrees / 2.0 *", "std::cos(degrees / 4.0 *")),
            ("the cone opens backward", (MATH, "(rx * dx + ry * dy) / length", "-(rx * dx + ry * dy) / length")),
            ("no angle stated, no enemy", (MATH, "if (degrees <= 0 || degrees >= 360)\n            return true;", "if (degrees >= 360)\n            return true;")),
            ("the nearest enemy is the farthest", (MATH, "distances[i] < distances[best]", "distances[i] > distances[best]")),
            ("the enemy beyond the radius is drawn", (MATH, "distances[i] <= radius &&", "")),
            ("an enemy at the radius is not", (MATH, "distances[i] <= radius &&", "distances[i] < radius &&")),
            ("the cost is for the cast", (MATH, "perCorpsePct * double(corpses)", "perCorpsePct")),
            ("a negative cost heals", (MATH, "return perCorpsePct > 0 ? perCorpsePct * double(corpses) : 0.0;", "return perCorpsePct * double(corpses);")),
            ("the pile takes the farthest corpses", (CORPSES, "GroundDistance(corpses_[a].spot, x, y) <", "GroundDistance(corpses_[a].spot, x, y) >")),
            ("the pile ignores the most", (CORPSES, "if (near.size() > max)", "if (false)")),
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
        self.assertEqual(runes(), ["Shrapnel", "Final Embrace", "Close Quarters", "Bloody Mess", "Dead Cold"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "radius_yards", q) for q in ("corpse_range", "explosion")], [11, 20])
        self.assertEqual(value("", "damage_pct"), 1050)
        self.assertEqual([value("Close Quarters", t) for t in ("damage_pct", "radius_yards")], [1575, 20])
        self.assertEqual(value("Bloody Mess", "radius_yards"), 25)
        self.assertEqual(value("Dead Cold", "freeze_duration_seconds"), 2)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"radius_yards", "damage_pct", "freeze_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "radius_yards", "corpse_range"), ("", "radius_yards", "explosion"), ("", "damage_pct", ""),
                                       ("Shrapnel", "damage_pct", ""), ("Final Embrace", "radius_yards", "explosion"),
                                       ("Close Quarters", "damage_pct", ""), ("Close Quarters", "radius_yards", ""),
                                       ("Bloody Mess", "radius_yards", ""), ("Dead Cold", "freeze_duration_seconds", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertIn((rune, token, qualifier), mapped)

    def test_the_unqualified_radius_is_the_explosions_of_exactly_two_runes(self):
        own = {r["rune"] for r in read(MODULE / "data/generated/spell_value_map.csv")
               if r["skill"] == SKILL and r["token"] == "radius_yards" and r["qualifier"] == "" and r["origin"] == "own"}
        self.assertEqual(own, {"Close Quarters", "Bloody Mess"})


class Tunables(unittest.TestCase):
    NUMBERS = {"corpse_explosion_max_corpses": "5", "final_embrace_life_cost_pct": "2", "shrapnel_cone_degrees": "70",
               "shrapnel_cone_yards": "45", "final_embrace_search_yards": "45", "close_quarters_corpse_range_yards": "14"}

    def test_the_rows_hold_the_sourced_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertIn(name, rows)
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                if number:
                    self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                else:
                    self.assertTrue(rows[name]["notes"].startswith("PLACEHOLDER for the designer"))

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))

    def test_the_decoded_rows_name_their_source(self):
        rows = tunables()
        for name in ("shrapnel_cone_degrees", "shrapnel_cone_yards", "final_embrace_search_yards", "close_quarters_corpse_range_yards"):
            self.assertIn("decode_pow.py power P6_Necro_CorpseExplosion", rows[name]["notes"])

    def test_the_cost_is_the_runes_tooltip(self):
        tooltip = [r["full_rune_text"] for r in read(D3 / "necromancer_runes.csv") if (r["skill_name"], r["rune_name"]) == (SKILL, "Final Embrace")][0]
        self.assertIn("costs 2% life per corpse", tooltip)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))
        self.combat = (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8")

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (auto explosion = CorpseExplosion::BasePct(spellId)) return explosion;", self.dispatch)
        self.assertIn("CorpseExplosion::CanCast(player, spellId, aim)", self.dispatch)
        self.assertIn("CorpseExplosion::Ground(player, spellId, center);", self.dispatch)

    def test_the_engine_asks_the_class_before_the_cast(self):
        text = re.sub(r"\s+", " ", self.combat)
        self.assertIn("Necromancer::CanCast( player, spell->GetSpellInfo()->Id, spell->m_targets.HasDst() ? spell->m_targets.GetDstPos() : nullptr, spell->m_targets.GetUnitTarget());", text)
        self.assertLess(text.index("Crusader::CanCast(player"), text.index("Necromancer::CanCast("))

    def test_the_cast_has_no_engine_hit_and_needs_a_corpse(self):
        self.assertIn("std::optional<double>(0.0) : std::nullopt", self.code)
        self.assertIn("Corpses::Count(player, centre, CorpseRange(spellId)) ? SPELL_CAST_OK : SPELL_FAILED_NO_VALID_TARGETS", self.code)

    def test_the_corpses_are_taken_nearest_first_up_to_the_most_around_the_search_centre(self):
        self.assertIn("Corpses::Consume(player, SearchCentre(player, spellId, center), CorpseRange(spellId), MostCorpses())", self.code)
        self.assertIn('return std::size_t(Tune("corpse_explosion_max_corpses"));', self.code)

    def test_each_corpse_strikes_the_enemies_around_it_for_the_skills_number(self):
        self.assertIn('double const pct = Numbers::Num(spellId, "damage_pct");', self.code)
        self.assertIn("Combat::Enemies(player, spellId, where, radius)", self.code)

    def test_final_embrace_pays_in_life_and_dead_cold_stuns_with_the_worn_powers(self):
        self.assertIn('SpendLife(player, LifeCostPct(Tune("final_embrace_life_cost_pct"), taken.size()));', self.code)
        self.assertIn('Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player)', self.code)

    def test_close_quarters_searches_further_shrapnel_reaches_the_cones_length_and_final_embrace_looks_far(self):
        self.assertIn('if (RuneAt(spellId) == Rune::CloseQuarters) return float(Tune("close_quarters_corpse_range_yards"));', self.code)
        self.assertIn('if (RuneAt(spellId) == Rune::Shrapnel) return Tune("shrapnel_cone_yards");', self.code)
        self.assertIn('double const search = Tune("final_embrace_search_yards");', self.code)

    def test_the_cone_opens_away_from_the_necromancer(self):
        self.assertIn('Tune("shrapnel_cone_degrees")', self.code)
        self.assertIn("corpse.GetPositionY() - player->GetPositionY(), corpse.GetPositionX() - player->GetPositionX()", self.code)


if __name__ == "__main__":
    unittest.main()
