"""Bone Spikes and its five runes (src/classes/necromancer/dc_necromancer_bone_spikes*.h/.cpp, the dispatch in
dc_necromancer.cpp, the three engine sites).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_bone_spikes/harness.cpp compiles the real
    dc_necromancer_bone_spikes_math.h with the sheets' own rune names and numbers: each rune name is its rune; the line and
    the pillars deal their own hit and the other runes leave the engine's; an enemy is on Path of Bones' line only inside
    its length and half its width, and its damage grows from the skill's number to the rune's largest bonus; Bone Pillars'
    the pillars take the nearest enemies inside the reach; the bleed
    is whole ticks of equal shares and the heal is split the same way. Planted differences in a scratch copy must each make
    it fail.
  * **The code reads what the sheets state.** Every token dc_necromancer_bone_spikes.cpp reads by name is a row of
    necromancer_skill_values.csv for Bone Spikes (or the rune that states it) and the generated value map says whose record
    holds it; the numbers are the researched ones: 120% on the area, Sudden Impact 1 second, Path of Bones 100% with up to
    100% more, Bone Pillars 180% a second, Frost Spikes 60% for 2 seconds, Blood Spikes 50% over 2 seconds with 0.5% of Life.
    Every tunable it reads is a row of data/tunables/necromancer.csv with its source number, or a named PLACEHOLDER.
  * **The wiring.** The dispatch answers the engine's four seams; the engine calls them where the Crusader's are called; a
    primary pays the Essence the sheet states, once per attack.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_bone_spikes.py
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
HEADER = "src/classes/necromancer/dc_necromancer_bone_spikes_math.h"
HARNESS = MODULE / "tests/necromancer_bone_spikes/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_bone_spikes.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Bone Spikes"


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
    numbers = [float(tunables()["path_of_bones_length_yards"]["d3_value"]), value("Path of Bones", "damage_pct"),
               value("Path of Bones", "max_bonus_pct"), value("Bone Pillars", "damage_pct"),
               value("Blood Spikes", "damage_pct"), value("Blood Spikes", "dot_duration_seconds"),
               value("Blood Spikes", "heal_pct")] + runes() + [float(tunables()["sudden_impact_icd_seconds"]["d3_value"])]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 35, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::BloodSpikes;\n        return Rune::None;', 'return Rune::FrostSpikes;\n        return Rune::None;')),
            ("the line deals no hit of its own", ("return rune == Rune::PathOfBones || rune == Rune::BonePillars;", "return rune == Rune::BonePillars;")),
            ("every rune deals its own", ("return rune == Rune::PathOfBones || rune == Rune::BonePillars;", "return rune != Rune::None;")),
            ("the line has no end", ("along < 0 || along > length", "along < 0")),
            ("the line is twice as wide", ("aside > width / 2.0", "aside > width")),
            ("the line is half as wide", ("aside > width / 2.0", "aside > width / 4.0")),
            ("the sides are not told apart", ("std::fabs(rx * dy - ry * dx)", "std::fabs(rx * dx - ry * dy)")),
            ("the bonus starts too high", ("basePct * (1.0 + std::max(0.0, maxBonusPct) / 100.0 * share)", "basePct * (1.0 + std::max(0.0, maxBonusPct) / 100.0)")),
            ("the bonus is not a percent", ("std::max(0.0, maxBonusPct) / 100.0 * share", "std::max(0.0, maxBonusPct) * share")),
            ("the bonus runs past the end", ("std::clamp(along / length, 0.0, 1.0)", "std::max(0.0, along / length)")),
            ("a negative bonus lowers the hit", ("std::max(0.0, maxBonusPct)", "maxBonusPct")),
            ("the pillars take the farthest", ("return distances[a] < distances[b];", "return distances[a] > distances[b];")),
            ("the pillars ignore the reach", ("if (distances[i] <= radius)", "if (true)")),
            ("the pillars take every enemy", ("if (inside.size() > count)", "if (false)")),
            ("a tick is lost to rounding", ("std::floor(seconds / tickSeconds + 1e-9)", "std::floor(seconds / tickSeconds)")),
            ("a bleed loses its last tick", ("std::floor(seconds / tickSeconds + 1e-9)", "std::floor(seconds / tickSeconds - 1.0)")),
            ("a tick is the whole bleed", ("return ticks ? total / ticks : 0.0;", "return ticks ? total : 0.0;")),
            ("the heal is a share of the wrong total", ("maxLife * healPct / 100.0 / ticks", "maxLife * healPct / 100.0")),
            ("the heal is not a percent", ("maxLife * healPct / 100.0 / ticks", "maxLife * healPct / ticks")),
            ("a stunned enemy is stunned again at once", ("return nowMs >= lastMs && nowMs - lastMs >= icdMs;", "return true;")),
            ("the cooldown is a millisecond short", ("nowMs - lastMs >= icdMs;", "nowMs - lastMs + 1 >= icdMs;")),
            ("the cooldown is a millisecond long", ("nowMs - lastMs >= icdMs;", "nowMs - lastMs > icdMs;")),
            ("a clock behind the stun is ready", ("return nowMs >= lastMs && nowMs - lastMs >= icdMs;", "return nowMs < lastMs || nowMs - lastMs >= icdMs;")),
            ("an enemy never stunned waits", ("if (!stunnedBefore)\n            return true;", "if (!stunnedBefore)\n            return false;")),
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
        self.assertEqual(runes(), ["Sudden Impact", "Path of Bones", "Bone Pillars", "Frost Spikes", "Blood Spikes"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "generated_resource"), value("", "damage_pct")], [24, 120])
        self.assertEqual(value("Sudden Impact", "stun_duration_seconds"), 1)
        self.assertEqual([value("Path of Bones", t) for t in ("damage_pct", "max_bonus_pct")], [100, 100])
        self.assertEqual(value("Bone Pillars", "damage_pct"), 180)
        self.assertEqual([value("Frost Spikes", t) for t in ("slow_pct", "slow_duration_seconds")], [60, 2])
        self.assertEqual([value("Blood Spikes", t) for t in ("damage_pct", "dot_duration_seconds", "heal_pct")], [50, 2, 0.5])

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "max_bonus_pct", "stun_duration_seconds", "slow_pct", "slow_duration_seconds",
                                  "dot_duration_seconds", "heal_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "generated_resource"), ("", "damage_pct"), ("Sudden Impact", "stun_duration_seconds"),
                            ("Path of Bones", "damage_pct"), ("Path of Bones", "max_bonus_pct"),
                            ("Bone Pillars", "damage_pct"), ("Frost Spikes", "slow_pct"),
                            ("Frost Spikes", "slow_duration_seconds"), ("Blood Spikes", "damage_pct"),
                            ("Blood Spikes", "dot_duration_seconds"), ("Blood Spikes", "heal_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "bone_pillars_reach_yards": "20",     # SF_15
        "path_of_bones_length_yards": "80",   # SF_21: 8 + 9 x 8
        "path_of_bones_width_yards": "3",     # the designer's standing default: a line attack is 3 yards wide
        "blood_spikes_tick_seconds": "0.5",   # the designer's standing default: a bleed ticks every 0.5 s
        "path_of_bones_essence": "30",        # SF_28
        "sudden_impact_icd_seconds": "3",     # SF_29: RUNEA ICD Duration
        "bone_pillars_extra_enemies": "2",    # the rune text: the target and up to two nearby enemies
    }

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

    def test_the_two_defaults_and_the_decoded_numbers_name_their_source(self):
        rows = tunables()
        for name in ("path_of_bones_width_yards", "blood_spikes_tick_seconds"):
            self.assertIn("standing default", rows[name]["notes"])
        for name in ("path_of_bones_length_yards", "path_of_bones_essence", "sudden_impact_icd_seconds"):
            self.assertIn("decode_pow.py power P6_Necro_BoneSpikes", rows[name]["notes"])

    def test_the_pillars_enemies_besides_the_target_are_the_rune_texts_count_and_a_row(self):
        text = [r["full_rune_text"] for r in read(D3 / "necromancer_runes.csv") if (r["skill_name"], r["rune_name"]) == (SKILL, "Bone Pillars")][0]
        words = {"one": 1, "two": 2, "three": 3}
        said = re.search(r"target and up to (\w+) nearby enemies", text)
        self.assertIsNotNone(said, text)
        row = tunables()["bone_pillars_extra_enemies"]
        self.assertEqual(float(row["d3_value"]), words[said.group(1)])
        self.assertEqual((row["value"], row["unit"]), ("", "count"))
        code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertNotIn("PillarsBesides", code)
        self.assertIn('std::size_t const besides = std::size_t(std::max(0.0, Tune("bone_pillars_extra_enemies")));', code)

    def test_path_of_bones_generates_its_own_essence_and_the_others_the_skills(self):
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertIn('RuneAt(spellId) == Rune::PathOfBones ? std::optional<double>(Tune("path_of_bones_essence")) : std::nullopt', text)
        dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))
        self.assertIn("BoneSpikes::GeneratedEssence(spellId) ? BoneSpikes::GeneratedEssence(spellId) : Numbers::Get(spellId, \"generated_resource\")", dispatch)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_four_seams(self):
        self.assertIn("if (auto spikes = BoneSpikes::BasePct(spellId)) return spikes;", self.dispatch)
        self.assertIn("BoneSpikes::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("BoneSpikes::Ground(player, spellId, center);", self.dispatch)
        self.assertIn('Numbers::Get(spellId, "generated_resource")', self.dispatch)
        self.assertIn("PayEssence(player, spellId, perEnemy ? GrimScythe::EssenceOfHits(*points, enemies) : *points);", self.dispatch)

    def test_the_engine_calls_them_beside_the_crusaders(self):
        combat = MODULE / "src/combat"
        loader = (combat / "dc_combat.cpp").read_text(encoding="utf-8")
        self.assertIn("else if (auto necromancer = Necromancer::BasePct(ability.id))", loader)
        resolve = re.sub(r"\s+", " ", (combat / "dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        self.assertEqual(resolve.count("Necromancer::Cast(player, shell.spellId, targets);"), 1)
        self.assertEqual(resolve.count("Necromancer::Ground(player, shell.spellId, center);"), 1)
        self.assertEqual(resolve.count("Necromancer::Connected(player, spellId, enemies);"), 1)

    def test_the_runes_that_deal_their_own_hit_say_so_and_blood_spikes_keeps_the_skills(self):
        self.assertIn("if (DealsItsOwnHit(rune)) return 0.0;", self.code)
        self.assertIn('return Numbers::Get(BaseId(Skill), "damage_pct");', self.code)

    def test_the_line_and_the_pillars_report_their_hit_once(self):
        self.assertEqual(self.code.count("Combat::Connected(player, spellId, hit);"), 2)

    def test_a_stun_is_stretched_by_the_worn_powers(self):
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', self.code)

    def test_sudden_impact_stuns_an_enemy_once_per_cooldown_for_each_necromancer(self):
        self.assertIn("std::map<std::pair<std::uint64_t, std::uint64_t>, std::uint64_t> stuns;", self.code)
        self.assertIn('std::uint64_t(std::max(0.0, Tune("sudden_impact_icd_seconds")) * 1000 + 0.5)', self.code)
        self.assertIn("if (!StunReady(found != stuns.end(), found != stuns.end() ? found->second : 0, now, icdMs)) return false;", self.code)
        self.assertIn("stuns[key] = now; return true;", self.code)
        self.assertIn("for (Unit* enemy : targets) if (TakeStun(player, enemy)) Stun(player, enemy, stun);", self.code)
        # The key is the Necromancer and the enemy, so two Necromancers do not share a cooldown.
        self.assertIn("player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue()}", self.code)

    def test_the_bleed_is_one_per_necromancer_enemy_and_spell(self):
        self.assertIn("using Key = std::tuple<std::uint64_t, std::uint64_t, std::uint32_t>;", self.code)

    def test_the_pillars_hit_for_the_scalar_of_a_hit(self):
        self.assertIn('double const pct = Numbers::Num(spellId, "damage_pct");', self.code)
        self.assertNotIn("AttacksPerSecond", self.code)


if __name__ == "__main__":
    unittest.main()
