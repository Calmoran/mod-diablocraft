"""Leech and its five runes (src/classes/necromancer/dc_necromancer_leech*.{h,cpp}), and the curses' follower
(dc_necromancer_curses.*) that Leech's Osmosis and Decrepify's Opportunist and Borrowed Time share.

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_leech/harness.cpp compiles the real dc_necromancer_leech_math.h with the
    sheet's rune names and numbers: each name is its rune; only Cursed Ground curses the ground and does not heal when struck; the
    heals are shares of the Life; Osmosis stops at its most enemies. Planted mutations must each turn it red.
  * **The numbers.** The sheet rows come from the tooltip and agree with the power file (decode_pow.py power P6_Necro_Leech: SF_3 20,
    SF_4 2.0, SF_5 and SF_16 30, SF_6 0.01, SF_14 1, SF_17 0.02); the four radii and the period are tunables with their SF cited. Osmosis'
    751 is the sheet's level-70 value of the power's 0.0014 x the Healing table (SF_1).
  * **It is wired.** The dispatch answers BasePct, Ground, Landed and RegisterScripts; the cast curses through the registry; each
    rune's part; the potion cooldown reducer; the follower.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_leech.py
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
HEADER = "src/classes/necromancer/dc_necromancer_leech_math.h"
TABLE = "src/combat/dc_healing_table.h"
HARNESS = MODULE / "tests/necromancer_leech/harness.cpp"
CODE = FOLDER / "dc_necromancer_leech.cpp"
CURSES = FOLDER / "dc_necromancer_curses.cpp"
SKILL = "Leech"


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
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (HEADER, TABLE)}
    if mutate:
        old, new = mutate[0], mutate[1]
        path = mutate[2] if len(mutate) > 2 else HEADER
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def healing(level):
    return float(next(r for r in read(D3 / "healing_table.csv") if int(r["level"]) == level)["value"])


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "heal_pct"), value("Osmosis", "heal_per_second_life"), value("Osmosis", "target_count"),
               value("Cursed Ground", "heal_pct"), value("Sanguine End", "life_per_kill_share_pct"),
               float(tunables()["osmosis_healing_share"]["d3_value"]), healing(10), healing(35), healing(70),
               value("Osmosis", "heal_per_second_life")]
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
            ("two runes share a name", ('return Rune::BloodFlask;\n        return Rune::None;', 'return Rune::CursedGround;\n        return Rune::None;')),
            ("a rune is no rune", ('if (name == "Osmosis")', 'if (name == "Osmosiss")')),
            ("every rune heals when struck", ("return rune != Rune::CursedGround;\n    }\n\n    // The curse", "return true;\n    }\n\n    // The curse")),
            ("Cursed Ground heals when struck", ("return rune != Rune::CursedGround;\n    }\n\n    // The curse", "return rune != Rune::BloodFlask;\n    }\n\n    // The curse")),
            ("Cursed Ground curses the enemies", ("return rune != Rune::CursedGround;\n    }\n\n    // \"heal the attacker", "return true;\n    }\n\n    // \"heal the attacker")),
            ("a struck hit heals the whole Life", ("maxLife * healPct / 100.0 : 0.0;\n    }\n\n    // Osmosis", "maxLife : 0.0;\n    }\n\n    // Osmosis")),
            ("a struck hit heals with no percent", ("return maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 : 0.0;\n    }\n\n    // Osmosis", "return maxLife > 0 ? maxLife * healPct / 100.0 : 0.0;\n    }\n\n    // Osmosis")),
            ("Osmosis ignores the level", ("return std::max(0.0, share) * std::max(0.0, healing);", "return std::max(0.0, share) * 536421.0;")),
            ("Osmosis is the table itself", ("return std::max(0.0, share) * std::max(0.0, healing);", "return std::max(0.0, healing);")),
            ("a negative table gives a heal", ("return std::max(0.0, share) * std::max(0.0, healing);", "return std::max(0.0, share) * healing;")),
            ("the table reads past its end", ("sizeof(Table) / sizeof(Table[0]) - 1)", "sizeof(Table) / sizeof(Table[0]) - 2)", TABLE)),
            ("the table is read a level off", ("return Table[std::min<std::size_t>(level,", "return Table[1 + std::min<std::size_t>(level,", TABLE)),
            ("Osmosis has no most", ("std::min(cursed, most) * std::max(0.0, perEnemy)", "cursed * std::max(0.0, perEnemy)")),
            ("Osmosis counts the most only", ("std::min(cursed, most) * std::max(0.0, perEnemy)", "most * std::max(0.0, perEnemy)")),
            ("a negative regeneration drains", ("std::min(cursed, most) * std::max(0.0, perEnemy)", "std::min(cursed, most) * perEnemy")),
            ("the patch ignores the enemies", ("return StruckHeal(maxLife, healPct) * enemies;", "return StruckHeal(maxLife, healPct);")),
            ("the kill heals the whole Life per Kill", ("lifePerKill * sharePct / 100.0 : 0.0", "lifePerKill : 0.0")),
            ("the kill share is not a percent", ("lifePerKill * sharePct / 100.0 : 0.0", "lifePerKill * sharePct : 0.0")),
            ("a negative share heals", ("return lifePerKill > 0 && sharePct > 0 ?", "return lifePerKill > 0 ?")),
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
        self.assertEqual(runes(), ["Osmosis", "Transmittable", "Sanguine End", "Cursed Ground", "Blood Flask"])

    def test_the_sheet_numbers_agree_with_the_power_file(self):
        self.assertEqual([value("", t) for t in ("cost_resource", "heal_pct", "duration_seconds")], [10, 2, 30])  # SF_17 0.02, SF_16
        self.assertEqual([value("Osmosis", t) for t in ("heal_per_second_life", "target_count")], [751, 20])  # SF_1 (level 70), SF_3
        self.assertEqual(value("Sanguine End", "life_per_kill_share_pct"), 200)  # SF_4 2.0
        self.assertEqual(value("Cursed Ground", "heal_pct"), 1.0)  # SF_6 0.01
        # The tooltip's 751 is the power's 0.0014 of the Healing table at level 70 (SF_1), which the code scales by level.
        self.assertEqual(round(0.0014 * healing(70)), value("Osmosis", "heal_per_second_life"))
        self.assertEqual(value("Blood Flask", "cooldown_reduction_seconds"), 1)  # SF_14

    def test_every_name_the_cast_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+?, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"duration_seconds", "heal_pct", "target_count", "life_per_kill_share_pct",
                                  "cooldown_reduction_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "heal_pct"), ("", "duration_seconds"), ("Osmosis", "heal_per_second_life"), ("Osmosis", "target_count"),
                            ("Sanguine End", "life_per_kill_share_pct"), ("Cursed Ground", "heal_pct"),
                            ("Blood Flask", "cooldown_reduction_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"leech_radius_yards": "20", "cursed_ground_radius_yards": "20", "cursed_ground_period_seconds": "1",
               "transmittable_radius_yards": "15", "osmosis_healing_share": "0.0014"}  # SF_15, SF_7, SF_8, SF_10, SF_1

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                self.assertIn("decode_pow.py power P6_Necro_Leech", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.curses = squeeze(CURSES.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (auto leech = Leech::BasePct(spellId)) return leech;", self.dispatch)
        self.assertIn("Leech::Ground(player, spellId, center);", self.dispatch)
        self.assertIn("Leech::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("Leech::RegisterScripts();", self.dispatch)

    def test_the_cast_curses_every_enemy_around_the_place_for_the_skills_seconds(self):
        self.assertIn('Combat::Enemies(player, spellId, center, Tune("leech_radius_yards"))', self.code)
        self.assertIn('Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(Skill), "duration_seconds"))', self.code)
        self.assertIn("Curses::Put(player, enemy, spellId, Passive::CurseSeconds(player, seconds));", self.code)

    def test_a_struck_hit_heals_the_attacker_by_the_skills_percent(self):
        self.assertIn('Heal(player, curse, StruckHeal(player->GetMaxHealth(), Numbers::Num(BaseId(Skill), "heal_pct")));', self.code)
        self.assertIn("!HealsWhenStruck(RuneAt(curse))", self.code)

    def test_osmosis_grows_with_the_necromancers_level_along_the_healing_table(self):
        self.assertIn('OsmosisPerEnemy(Tune("osmosis_healing_share"), Healing::At(player->GetLevel()))', self.code)
        self.assertIn('OsmosisRegen(cursed, perEnemy, unsigned(Numbers::Num(spellId, "target_count")))', self.code)
        self.assertIn('#include "../../combat/dc_healing_table.h"', CODE.read_text(encoding="utf-8"))

    def test_osmosis_follows_the_enemies_cursed_and_another_rune_takes_it_off(self):
        self.assertIn("Curses::Follow(player, Skill, spellId, Regen);", self.code)
        self.assertIn("Curses::Unfollow(player, Skill);", self.code)
        self.assertIn("Buffs::Set(player, spellId, Stat::LifeRegen, Bucket::Flat,", self.code)

    def test_cursed_ground_heals_every_period_for_each_enemy_in_the_patch_for_the_skills_seconds(self):
        self.assertIn('Combat::Enemies(player, spellId, center, Tune("cursed_ground_radius_yards")).size()', self.code)
        self.assertIn("GroundHeal(player->GetMaxHealth(), Numbers::Num(spellId, \"heal_pct\"), enemies)", self.code)
        self.assertIn("Patch(player, spellId, center, period > 0 ? unsigned(seconds / period + 1e-9) : 0u);", self.code)

    def test_the_death_of_a_cursed_enemy_is_answered_by_the_curser_of_each_rune(self):
        self.assertIn("for (auto const& [player, curse] : Curses::Cursers(victim))", self.code)
        self.assertIn("Spread(player, curse, victim, Curses::Left(player, victim, Skill));", self.code)
        self.assertIn("KillHeal((*sheet)[Stat::LifePerKill], Numbers::Num(curse, \"life_per_kill_share_pct\"))", self.code)
        self.assertIn('Classes::ReducePotionCooldown(player, Millis(Numbers::Num(curse, "cooldown_reduction_seconds")));', self.code)

    def test_the_curse_spreads_to_the_nearest_unaffected_enemy_in_the_search_radius(self):
        self.assertIn('Tune("transmittable_radius_yards")', self.code)
        self.assertIn("enemy != dead && enemy->IsAlive() && !Curses::On(player, enemy)", self.code)

    def test_the_potion_cooldown_reducer_shortens_every_potion_shell_on_cooldown(self):
        classes = squeeze((MODULE / "src/classes/dc_classes.cpp").read_text(encoding="utf-8"))
        self.assertIn("void ReducePotionCooldown(Player* player, std::uint32_t ms) {", classes)
        self.assertIn("player->ModifySpellCooldown(shell, -static_cast<int32>(ms));", classes)
        self.assertIn("void ReducePotionCooldown(Player* player, std::uint32_t ms);", squeeze((MODULE / "src/classes/dc_classes.h").read_text(encoding="utf-8")))

    def test_the_follower_applies_every_second_while_any_enemy_is_cursed_and_zero_when_the_last_is_gone(self):
        self.assertIn("unsigned const cursed = Cursed(player); follower.apply(player, follower.spellId, cursed);", self.curses)
        self.assertIn("if (cursed == 0) {", self.curses)
        self.assertIn("constexpr std::chrono::milliseconds FollowEvery{1000};", self.curses)
        # A new follower of another record takes the old one's number off; a stale tick finds its stamp gone.
        self.assertIn("if (old.stamp && old.spellId != spellId) old.apply(player, old.spellId, 0);", self.curses)
        self.assertIn("found->second.stamp != stamp", self.curses)


if __name__ == "__main__":
    unittest.main()
