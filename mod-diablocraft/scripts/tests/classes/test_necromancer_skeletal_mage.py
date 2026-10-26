"""Skeletal Mage and its five runes (src/classes/necromancer/dc_necromancer_skeletal_mage*.h/.cpp, the mage's kind in
dc_necromancer_pets.cpp, the shared minions' new fields in src/combat/dc_minions.*).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_skeletal_mage/harness.cpp compiles the real
    dc_necromancer_skeletal_mage_math.h with the sheets' own rune names and numbers: each rune name is its rune; Singularity
    adds its bonus for every point of Essence consumed; the module takes the pool beyond the cost the core takes; Life Support
    adds its seconds and no other rune does. Planted differences in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token the cast and the mage's kind read by name is a row of
    necromancer_skill_values.csv for Skeletal Mage (or the rune that states it), the generated value map says whose record
    holds it, and the numbers are the researched ones: 400% over two attacks for 6 seconds, Singularity 3% a point, Life Support
    2 more seconds, Contamination 100%, Skeleton Archer 400% with 3% attack speed for 5 seconds up to 10 stacks. Every tunable
    is a row of data/tunables/necromancer.csv: Life Support's cost with its source, the aura's radius and the archer's range
    (35, decode_pow.py power P6_Necro_RaiseDead_E_ArcherAttack) with the sources named; the mage's rise toward the enemy is 0.3 of the way, 1.0 for Contamination.
  * **The wiring.** The cast has no hit of its own and raises the mage on the shared minions; the mage kind carries each rune's
    part (a corpse at its end, an aura, an archer's blows and range); the shared piece lets a kind end, strike, shoot and pulse.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_skeletal_mage.py
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
MATH = "src/classes/necromancer/dc_necromancer_skeletal_mage_math.h"
HARNESS = MODULE / "tests/necromancer_skeletal_mage/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_skeletal_mage.cpp"
PETS = MODULE / "src/classes/necromancer/dc_necromancer_pets.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Skeletal Mage"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token):
    rows = [r for r in read(D3 / "necromancer_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, "")]
    assert len(rows) == 1, (rune, token, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "necromancer_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}


def scratch_tree(mutate=None):
    key = MATH[len("src/"):]
    files = {key: (MODULE / MATH).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {MATH}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Singularity", "damage_bonus_pct"), value("", "cost_resource"), value("", "duration_seconds"),
               value("Life Support", "duration_seconds")] + runes()
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
            ("two runes share a name", ('if (name == "Life Support")\n            return Rune::LifeSupport;', 'if (name == "Life Support")\n            return Rune::Singularity;')),
            ("the bonus is flat", ("perPoint * points", "perPoint")),
            ("the bonus is a point short", ("perPoint * points", "perPoint * (points - 1)")),
            ("a negative bonus lowers the hit", ("perPoint > 0 && points > 0 ?", "points > 0 ?")),
            ("no points still gives a bonus", ("perPoint > 0 && points > 0 ?", "perPoint > 0 ?")),
            ("the module takes the cost too", ("points - std::max(0.0, cost)", "points")),
            ("the module takes the cost twice", ("points - std::max(0.0, cost)", "points - 2 * std::max(0.0, cost)")),
            ("a pool below the cost goes negative", ("return std::max(0.0, points - std::max(0.0, cost));", "return points - std::max(0.0, cost);")),
            ("Life Support adds nothing", ("(lifeSupport ? std::max(0.0, extraSeconds) : 0.0)", "0.0")),
            ("every rune adds the seconds", ("(lifeSupport ? std::max(0.0, extraSeconds) : 0.0)", "std::max(0.0, extraSeconds)")),
            ("the rune replaces the seconds", ("std::max(0.0, baseSeconds) +", "")),
            ("the mage rises at the Necromancer", ("return from + (to - from) * std::clamp(share, 0.0, 1.0);", "return from;")),
            ("the mage rises at the enemy", ("return from + (to - from) * std::clamp(share, 0.0, 1.0);", "return to;")),
            ("the mage rises past the enemy", ("std::clamp(share, 0.0, 1.0)", "std::max(share, 0.0)")),
            ("the mage rises behind the Necromancer", ("std::clamp(share, 0.0, 1.0)", "std::min(share, 1.0)")),
            ("a negative extra shortens the mage", ("std::max(0.0, extraSeconds)", "extraSeconds")),
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
        self.assertEqual(runes(), ["Gift of Death", "Singularity", "Life Support", "Contamination", "Skeleton Archer"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("cost_resource", "damage_pct", "duration_seconds")], [40, 400, 6])
        self.assertEqual(value("Singularity", "damage_bonus_pct"), 3)
        self.assertEqual(value("Life Support", "duration_seconds"), 2)
        self.assertEqual(value("Contamination", "damage_pct"), 100)
        self.assertEqual([value("Skeleton Archer", t) for t in ("damage_pct", "attack_speed_pct", "duration_seconds", "max_stacks_count")],
                         [400, 3, 5, 10])

    def test_every_name_read_exists_and_the_engine_can_read_it(self):
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        cast = set(re.findall(call, CODE.read_text(encoding="utf-8")))
        self.assertEqual(cast - sheet_tokens, set())
        self.assertEqual(cast, {"cost_resource", "damage_bonus_pct"})
        mage = PETS.read_text(encoding="utf-8")
        mage = mage[mage.index("Minions::Kind Mage(Player* owner)"):mage.index("// Command Skeletons")]
        kind = set(re.findall(call, mage))
        self.assertEqual(kind - sheet_tokens, set())
        self.assertEqual(kind, {"damage_pct", "duration_seconds", "attack_speed_pct", "max_stacks_count"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "cost_resource"), ("", "damage_pct"), ("", "duration_seconds"), ("Singularity", "damage_bonus_pct"),
                            ("Life Support", "duration_seconds"), ("Contamination", "damage_pct"), ("Skeleton Archer", "damage_pct"),
                            ("Skeleton Archer", "attack_speed_pct"), ("Skeleton Archer", "duration_seconds"),
                            ("Skeleton Archer", "max_stacks_count")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"life_support_life_cost_pct": "10", "contamination_radius_yards": "15", "skeleton_archer_range_yards": "35",
               "skeletal_mage_rise_share": "0.3", "contamination_mage_rise_share": "1"}

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
        text = CODE.read_text(encoding="utf-8") + PETS.read_text(encoding="utf-8")
        read_here = set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
        shares = {"skeletal_mage_rise_share", "contamination_mage_rise_share"}
        self.assertTrue(set(self.NUMBERS) - shares <= read_here, set(self.NUMBERS) - shares - read_here)
        for name in shares:
            self.assertIn(f'"{name}"', text)

    def test_the_cost_is_the_runes_tooltip(self):
        tooltip = [r["full_rune_text"] for r in read(D3 / "necromancer_runes.csv") if (r["skill_name"], r["rune_name"]) == (SKILL, "Life Support")][0]
        self.assertIn("cost 10% health", tooltip)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.pets = re.sub(r"\s+", " ", PETS.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))
        self.minions = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_minions.cpp").read_text(encoding="utf-8"))
        self.header = (MODULE / "src/combat/dc_minions.h").read_text(encoding="utf-8")

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (auto mage = SkeletalMage::BasePct(spellId)) return mage;", self.dispatch)
        self.assertIn("SkeletalMage::Casting(player, spellId);", self.dispatch)
        self.assertIn("SkeletalMage::Cast(player, spellId, targets);", self.dispatch)

    def test_the_cast_has_no_hit_and_raises_the_mage_beside_the_necromancer(self):
        self.assertIn("std::optional<double>(0.0) : std::nullopt", self.code)
        self.assertIn("Pets::RaiseMage(player, RisePlace(player, spellId, targets), spellId, bonus);", self.code)
        self.assertIn('Tune(RuneAt(spellId) == Rune::Contamination ? "contamination_mage_rise_share" : "skeletal_mage_rise_share")', self.code)
        self.assertIn("Along(player->GetPositionX(), enemy->GetPositionX(), share)", self.code)

    def test_life_support_pays_in_life_and_singularity_takes_the_pool(self):
        self.assertIn('SpendLife(player, Tune("life_support_life_cost_pct"));', self.code)
        self.assertIn("Resources::ToPoints(Essence, Resources::Units(player, Essence))", self.code)
        self.assertIn('EssenceBeyondCost(points, Numbers::Num(spellId, "cost_resource"))', self.code)

    def test_each_rune_gives_the_mage_its_part(self):
        self.assertIn("kind.ended = [](Player* player, Position const& at) { Corpses::LeaveMade(player, at, 0); };", self.pets)
        self.assertIn("kind.auraPct = kind.damagePct; kind.damagePct = 0;", self.pets)
        self.assertIn('kind.auraRadius = Tune("contamination_radius_yards");', self.pets)
        self.assertIn('kind.rangeYards = Tune("skeleton_archer_range_yards");', self.pets)
        self.assertIn("Buffs::Stack(player, record, Stat::AttackSpeed, Bucket::Flat", self.pets)
        self.assertIn('Numbers::Num(BaseId(MageSkill), "duration_seconds")', self.pets)

    def test_the_shared_piece_lets_a_kind_end_strike_shoot_and_pulse(self):
        for field in ("rangeYards", "auraRadius", "auraPct", "ended", "struck"):
            self.assertIn(field, self.header)
        self.assertNotIn("Necromancer", self.header)
        self.assertIn("if (kind.ended && player && player->IsAlive() && player->IsInMap(me) && player->InSamePhase(me)) kind.ended(player, me->GetPosition());", self.minions)
        self.assertIn("if (Combat::Strike(player, target, kind.record, share)) { if (kind.struck) kind.struck(player, target); if (kind.struckBy) kind.struckBy(player, me, target); Struck(player, target); }", self.minions)
        self.assertIn("if (Combat::Strike(player, enemy, record, BoostedPct(kind.auraPct, kind.bonusAgainst ? kind.bonusAgainst(player, enemy) : 0.0), true)) Struck(player, enemy);", self.minions)
        self.assertIn("kind.lifeMs + net", self.minions)


if __name__ == "__main__":
    unittest.main()
