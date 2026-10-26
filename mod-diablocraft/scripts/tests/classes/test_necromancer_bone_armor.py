"""Bone Armor and its five runes (src/classes/necromancer/dc_necromancer_bone_armor*.{h,cpp}) and the shared control immunity
(src/combat/dc_control_immunity.*).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_bone_armor/harness.cpp compiles the real dc_necromancer_bone_armor_math.h with the
    sheet's rune names and numbers: each name is its rune; the enemies hit give their share up to the most; the armor cuts a hit by the
    percent and never below nothing; only Limited Immunity absorbs all. Planted mutations must each turn it red.
  * **The numbers.** The sheet rows come from the tooltip and agree with the power file (decode_pow.py power P6_Necro_BoneArmor: SF_0 60,
    SF_2 0.03, SF_3 1.25, SF_4 10, SF_5 1.45, SF_6 5, SF_7 45, SF_10 2, SF_11 10, SF_13 0.1, SF_14 0.01); the Life cost is a tunable with its
    SF cited.
  * **It is wired.** The dispatch answers Casting, Cast and Reduce; the armor replaces the one before; each rune's part; the armor ends with
    its seconds and takes its rune off.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_bone_armor.py
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
FOLDER = MODULE / "src/classes/necromancer"
HEADER = "src/classes/necromancer/dc_necromancer_bone_armor_math.h"
HARNESS = MODULE / "tests/necromancer_bone_armor/harness.cpp"
CODE = FOLDER / "dc_necromancer_bone_armor.cpp"
SKILL = "Bone Armor"


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


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def scratch_tree(mutate=None):
    key = HEADER[len("src/"):]
    files = {key: (MODULE / HEADER).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "damage_reduction_pct"), value("", "target_count"), value("Thy Flesh Sustained", "life_regen_pct"),
               value("Harvest of Anguish", "movement_speed_pct")]
    return harness_env.run([str(binary)] + runes() + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 14, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::HarvestOfAnguish;\n        return Rune::None;', 'return Rune::Dislocation;\n        return Rune::None;')),
            ("a rune is no rune", ('if (name == "Dislocation")', 'if (name == "Dislocations")')),
            ("the armor has no most", ("std::min(hit, most) * std::max(0.0, perEnemy)", "hit * std::max(0.0, perEnemy)")),
            ("the armor counts the most only", ("std::min(hit, most) * std::max(0.0, perEnemy)", "most * std::max(0.0, perEnemy)")),
            ("a negative share drains", ("std::min(hit, most) * std::max(0.0, perEnemy)", "std::min(hit, most) * perEnemy")),
            ("the cut is the percent itself", ("return std::max(0.0, 1.0 - std::max(0.0, reductionPct) / 100.0);", "return std::max(0.0, reductionPct / 100.0);")),
            ("the cut is not a percent", ("1.0 - std::max(0.0, reductionPct) / 100.0", "1.0 - std::max(0.0, reductionPct)")),
            ("a hit can heal", ("return std::max(0.0, 1.0 - std::max(0.0, reductionPct) / 100.0);", "return 1.0 - std::max(0.0, reductionPct) / 100.0;")),
            ("a negative cut adds damage", ("1.0 - std::max(0.0, reductionPct) / 100.0", "1.0 - reductionPct / 100.0")),
            ("every rune absorbs all", ("return rune == Rune::LimitedImmunity;", "return rune != Rune::None;")),
            ("Limited Immunity absorbs nothing", ("return rune == Rune::LimitedImmunity;", "return false;")),
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
        self.assertEqual(runes(), ["Vengeful Armaments", "Limited Immunity", "Dislocation", "Thy Flesh Sustained", "Harvest of Anguish"])

    def test_the_sheet_numbers_agree_with_the_power_file(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "damage_pct", "damage_reduction_pct", "target_count", "duration_seconds")],
                         [10, 125, 3, 10, 60])  # SF_11, SF_3, SF_2, SF_4, SF_0
        self.assertEqual(value("Vengeful Armaments", "damage_pct"), 145)  # SF_5
        self.assertEqual([value("Limited Immunity", t) for t in ("cooldown_seconds", "duration_seconds")], [45, 5])  # SF_7, SF_6
        self.assertEqual(value("Dislocation", "stun_duration_seconds"), 2)  # SF_10
        self.assertEqual(value("Thy Flesh Sustained", "life_regen_pct"), 10)  # SF_13 0.1
        self.assertEqual(value("Harvest of Anguish", "movement_speed_pct"), 1)  # SF_14 0.01

    def test_every_name_the_cast_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+?, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"target_count", "duration_seconds", "damage_reduction_pct", "stun_duration_seconds", "life_regen_pct",
                                  "movement_speed_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_reduction_pct"), ("", "target_count"), ("", "duration_seconds"), ("Limited Immunity", "duration_seconds"),
                            ("Limited Immunity", "cooldown_seconds"), ("Dislocation", "stun_duration_seconds"),
                            ("Thy Flesh Sustained", "life_regen_pct"), ("Harvest of Anguish", "movement_speed_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    def test_the_life_cost_is_the_power_files_and_not_alexs(self):
        row = tunables()["thy_flesh_sustained_life_cost_pct"]
        self.assertEqual((row["d3_value"], row["value"]), ("20", ""))  # SF_12 0.2
        self.assertIn("decode_pow.py power P6_Necro_BoneArmor", row["notes"])
        self.assertNotIn("PLACEHOLDER", row["notes"])

    def test_the_code_reads_exactly_this(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {"thy_flesh_sustained_life_cost_pct"})


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))
        self.immunity = squeeze((MODULE / "src/combat/dc_control_immunity.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("BoneArmor::Casting(player, spellId);", self.dispatch)
        self.assertIn("BoneArmor::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("return Simulacrum::Reduce(victim, Passive::Reduce(victim, BoneArmor::Reduce(victim, CorpseRevive::Reduce(victim, damage))));", self.dispatch)

    def test_the_armor_is_the_enemies_hit_up_to_the_most_for_the_seconds_and_the_next_cast_replaces_it(self):
        self.assertIn('PerEnemy(hit, Numbers::Num(spellId, "damage_reduction_pct"), most)', self.code)
        self.assertIn('unsigned const most = unsigned(Numbers::Num(spellId, "target_count"));', self.code)
        self.assertIn('Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(spellId, "duration_seconds"))', self.code)
        self.assertIn("if (old.stamp) Take(player, old.spellId);", self.code)
        self.assertIn("if (found == worn.end() || found->second.stamp != stamp) return;", self.code)

    def test_the_armor_cuts_the_damage_taken_or_absorbs_it_all(self):
        self.assertIn("if (found == worn.end() || Now() >= found->second.until) return damage;", self.code)
        self.assertIn("return AbsorbsAll(RuneAt(armor.spellId)) ? 0.0 : damage * TakenFactor(armor.reductionPct);", self.code)

    def test_limited_immunity_grants_the_control_immunity_for_its_seconds_and_takes_it_off(self):
        self.assertIn("ControlImmunity::Set(player, spellId, true);", self.code)
        self.assertIn("ControlImmunity::Set(player, spellId, false);", self.code)
        self.assertIn("player->RemoveAurasWithMechanic(ControlImpairing);", self.immunity)

    def test_dislocation_stuns_the_enemies_hit_with_the_worn_powers(self):
        self.assertIn('Stun(player, enemy, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));', self.code)

    def test_thy_flesh_sustained_takes_life_and_raises_regeneration_in_percent_and_it_comes_off(self):
        self.assertIn('if (player && RuneAt(spellId) == Rune::ThyFleshSustained) SpendLife(player, Tune("thy_flesh_sustained_life_cost_pct"));', self.code)
        self.assertIn("Buffs::Set(player, spellId, Stat::LifeRegen, Bucket::Percent,", self.code)
        self.assertIn("Buffs::Set(player, spellId, Stat::LifeRegen, Bucket::Percent, 0);", self.code)

    def test_harvest_of_anguish_raises_movement_speed_and_it_comes_off(self):
        self.assertIn("Buffs::Set(player, spellId, Stat::MovementSpeed, Bucket::Flat,", self.code)
        self.assertIn("Buffs::Set(player, spellId, Stat::MovementSpeed, Bucket::Flat, 0);", self.code)


if __name__ == "__main__":
    unittest.main()
