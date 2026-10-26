"""Bone Spear and its five runes (src/classes/necromancer/dc_necromancer_bone_spear*.h/.cpp, dc_necromancer_life_math.h, the
dispatch in dc_necromancer.cpp, the engine's four call sites).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_bone_spear/harness.cpp compiles the real
    dc_necromancer_bone_spear_math.h and dc_necromancer_life_math.h with the sheets' own rune names and numbers: each rune
    name is its rune; Blighted Marrow adds its bonus for each enemy already passed and none for the first; Teeth strike inside
    their reach only; Shatter's first impact detonates and no other; Blood Spear takes a share of maximum Life and never
    leaves less than 1. Planted differences in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_necromancer_bone_spear.cpp reads by name is a row of
    necromancer_skill_values.csv for Bone Spear (or the rune that states it), the generated value map says whose record holds
    it, and the numbers are the researched ones: 500% pierce, Crystallization 20% on the enemy and 3% on the Necromancer for
    3 seconds up to 10 stacks, Shatter 500% in 15 yards, Blighted Marrow 15%, Blood Spear 650%, Teeth 300%. Every tunable it
    reads is a row of data/tunables/necromancer.csv with its source number.
  * **The wiring.** The engine asks the class at the four places it asks the Crusader: the cast's beginning, a projectile's
    impact, a landed hit, the hit's multipliers; Shatter and Teeth stop the engine's own hit, the others add to it.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_bone_spear.py
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
MATH = "src/classes/necromancer/dc_necromancer_bone_spear_math.h"
LIFE = "src/classes/necromancer/dc_necromancer_life_math.h"
HARNESS = MODULE / "tests/necromancer_bone_spear/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_bone_spear.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Bone Spear"


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
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (MATH, LIFE)}
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
    numbers = [value("Blighted Marrow", "damage_bonus_pct"), float(rows["bone_spear_teeth_reach_yards"]["d3_value"]),
               float(rows["blood_spear_life_cost_pct"]["d3_value"])] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 15, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (MATH, 'if (name == "Teeth")\n            return Rune::Teeth;', 'if (name == "Teeth")\n            return Rune::Shatter;')),
            ("the bonus starts at the first enemy", (MATH, "bonusPct * passed", "bonusPct * (passed + 1)")),
            ("the bonus is flat", (MATH, "bonusPct * passed", "bonusPct")),
            ("a negative bonus lowers the hit", (MATH, "return bonusPct > 0 ? bonusPct * passed : 0.0;", "return bonusPct * passed;")),
            ("an enemy at the reach is spared", (MATH, "distance <= reach", "distance < reach")),
            ("the teeth have no reach", (MATH, "return reach <= 0 || distance <= reach;", "return true;")),
            ("no reach stated spares everything", (MATH, "reach <= 0 || distance <= reach", "distance <= reach")),
            ("every impact detonates", (MATH, "return impactIndex == 0;", "return true;")),
            ("no impact detonates", (MATH, "return impactIndex == 0;", "return false;")),
            ("the second impact detonates", (MATH, "return impactIndex == 0;", "return impactIndex <= 1;")),
            ("the cost is not a percent", (LIFE, "maxLife * pct / 100.0", "maxLife * pct")),
            ("the cost can kill", (LIFE, "std::max(0.0, health - 1.0)", "std::max(0.0, health)")),
            ("the cost is a share of the Life left", (LIFE, "maxLife * pct / 100.0", "health * pct / 100.0")),
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
        self.assertEqual(runes(), ["Crystallization", "Shatter", "Blighted Marrow", "Blood Spear", "Teeth"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct")], [20, 500])
        self.assertEqual([value("Crystallization", "attack_speed_pct", q) for q in ("enemy", "self")], [20, 3])
        self.assertEqual([value("Crystallization", t) for t in ("duration_seconds", "max_stacks_count")], [3, 10])
        self.assertEqual([value("Shatter", t) for t in ("damage_pct", "radius_yards")], [500, 15])
        self.assertEqual(value("Blighted Marrow", "damage_bonus_pct"), 15)
        self.assertEqual(value("Blood Spear", "damage_pct"), 650)
        self.assertEqual(value("Teeth", "damage_pct"), 300)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"radius_yards", "duration_seconds", "attack_speed_pct", "max_stacks_count", "damage_bonus_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "cost_resource", ""), ("", "damage_pct", ""), ("Crystallization", "attack_speed_pct", "enemy"),
                                       ("Crystallization", "attack_speed_pct", "self"), ("Crystallization", "duration_seconds", ""),
                                       ("Crystallization", "max_stacks_count", ""), ("Shatter", "damage_pct", ""),
                                       ("Shatter", "radius_yards", ""), ("Blighted Marrow", "damage_bonus_pct", ""),
                                       ("Blood Spear", "damage_pct", ""), ("Teeth", "damage_pct", "")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertIn((rune, token, qualifier), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"bone_spear_teeth_reach_yards": "70", "blood_spear_life_cost_pct": "10"}

    def test_the_rows_hold_the_sourced_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertIn(name, rows)
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))

    def test_the_cost_is_the_runes_tooltip(self):
        tooltip = [r["full_rune_text"] for r in read(D3 / "necromancer_runes.csv") if (r["skill_name"], r["rune_name"]) == (SKILL, "Blood Spear")][0]
        self.assertIn("at the cost of 10% Health", tooltip)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))
        self.combat = MODULE / "src/combat"

    def test_the_dispatch_answers_the_four_seams(self):
        self.assertIn("BoneSpear::Casting(player, spellId);", self.dispatch)
        self.assertIn("BoneSpear::Impact(player, target, spellId, index)", self.dispatch)
        self.assertIn("BoneSpear::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("BoneSpear::Multipliers(player, spellId, out);", self.dispatch)

    def test_the_engine_asks_the_class_where_it_asks_the_crusader(self):
        resolve = re.sub(r"\s+", " ", (self.combat / "dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        self.assertIn("Monk::Casting(player, shell.spellId); Necromancer::Casting(player, shell.spellId);", resolve)
        self.assertEqual(resolve.count("Crusader::Landed(player, target, shell.spellId); Necromancer::Landed(player, target, shell.spellId);"), 1)
        self.assertEqual(resolve.count("Crusader::Landed(player, target, spellId); Necromancer::Landed(player, target, spellId);"), 1)
        self.assertIn("if (Necromancer::Impact(player, target, shell.spellId, unsigned(impacted.size()) - 1)) return;", resolve)
        combat = (self.combat / "dc_combat.cpp").read_text(encoding="utf-8")
        self.assertIn("Crusader::Multipliers(player, shell.spellId, hit.factors);\n        Necromancer::Multipliers(player, target, shell.spellId, hit.factors);", combat)

    def test_the_impact_seam_is_asked_after_the_enemy_is_counted(self):
        resolve = re.sub(r"\s+", " ", (self.combat / "dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        counted = resolve.index("if (!impacted.insert(target->GetGUID().GetRawValue()).second) return;")
        self.assertLess(counted, resolve.index("Necromancer::Impact(player, target, shell.spellId"))

    def test_shatter_detonates_on_the_first_enemy_and_stops_the_rest(self):
        self.assertIn("if (Detonates(index)) Combat::StrikeArea(player, spellId, target->GetPosition(), Numbers::Num(spellId, \"radius_yards\")); return true;", self.code)

    def test_teeth_stop_the_far_enemies_and_blighted_marrow_counts_the_ones_passed(self):
        self.assertIn('return !WithinReach(player->GetExactDist(target), Tune("bone_spear_teeth_reach_yards"));', self.code)
        self.assertIn("passed[player->GetGUID().GetRawValue()] = index;", self.code)
        self.assertIn('AddFactor(out, "Blighted Marrow", bonus);', self.code)

    def test_blood_spear_pays_when_the_cast_begins(self):
        self.assertIn('if (player && RuneAt(spellId) == Rune::BloodSpear) SpendLife(player, Tune("blood_spear_life_cost_pct"));', self.code)

    def test_crystallization_slows_the_enemy_and_stacks_the_necromancer(self):
        self.assertIn('Weary(player, target, Numbers::Num(spellId, "attack_speed_pct", "enemy"), seconds);', self.code)
        self.assertIn('Buffs::Stack(player, spellId, Stat::AttackSpeed, Bucket::Flat, Numbers::Num(spellId, "attack_speed_pct", "self"),', self.code)


if __name__ == "__main__":
    unittest.main()
