"""Decrepify and its five runes (src/classes/necromancer/dc_necromancer_decrepify*.{h,cpp} and the curses, dc_necromancer_curses.*).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_decrepify/harness.cpp compiles the real dc_necromancer_decrepify_math.h with
    the sheet's rune names and numbers: each name is its rune; Enfeeblement's slow decays by the decay each second to the normal and no
    further, reaching it in the rune's seconds; the Necromancer's gain for the enemies cursed stops at the most; Dizzying Curse's stun
    lands on a roll under the chance. Planted mutations must each turn it red.
  * **The numbers.** The sheet rows come from the tooltip and agree with the power file (decode_pow.py power P6_Necro_Decrepify: SF_2 0.3,
    SF_3 0.75, SF_5 5, SF_6 1, SF_7 0.03 and SF_9 10, SF_10 0.01 and SF_11 20, SF_14 0.4, SF_16 30, SF_18 0.1, SF_19 2); the radius and the
    decay are tunables with their SF cited.
  * **It is wired.** The dispatch answers BasePct, Ground, Landed and RegisterScripts; the cast curses through the registry (one curse
    on an enemy at a time, the newest replacing it and the old one's skill lifting its effects); each rune's part.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_decrepify.py
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
HEADER = "src/classes/necromancer/dc_necromancer_decrepify_math.h"
HARNESS = MODULE / "tests/necromancer_decrepify/harness.cpp"
CODE = FOLDER / "dc_necromancer_decrepify.cpp"
CURSES = FOLDER / "dc_necromancer_curses.cpp"
SKILL = "Decrepify"


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


def tune(name):
    return float(tunables()[name]["d3_value"])


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
    numbers = [value("", "slow_pct"), value("Enfeeblement", "slow_pct"), tune("decrepify_slow_decay_pct_per_second"),
               value("Enfeeblement", "duration_seconds"), value("Opportunist", "movement_speed_pct"),
               value("Opportunist", "max_bonus_pct"), value("Borrowed Time", "cooldown_reduction_pct"),
               value("Borrowed Time", "max_bonus_pct"), value("Dizzying Curse", "proc_chance_pct")]
    return harness_env.run([str(binary)] + runes() + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 18, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::DizzyingCurse;\n        return Rune::None;', 'return Rune::Wither;\n        return Rune::None;')),
            ("a rune is no rune", ('if (name == "Wither")', 'if (name == "Withers")')),
            ("the slow does not decay", ("startPct - std::max(0.0, perSecond) * std::max(0.0, elapsed)", "startPct")),
            ("the slow decays too fast", ("std::max(0.0, perSecond) * std::max(0.0, elapsed)", "std::max(0.0, perSecond) * std::max(0.0, elapsed) * 2")),
            ("the slow weakens below the normal", ("return std::max(basePct, startPct", "return (startPct")),
            ("a negative decay strengthens", ("std::max(0.0, perSecond) * std::max(0.0, elapsed)", "perSecond * std::max(0.0, elapsed)")),
            ("a step is lost to rounding", ("std::floor(seconds / step + 1e-9)", "std::floor(seconds / step)")),
            ("the bonus has no most", ("std::min(cursed * std::max(0.0, perEnemy), most)", "cursed * std::max(0.0, perEnemy)")),
            ("the bonus is one enemy's", ("std::min(cursed * std::max(0.0, perEnemy), most)", "std::min(std::max(0.0, perEnemy), most)")),
            ("a negative most gives a penalty", ("return std::max(0.0, std::min(cursed", "return (std::min(cursed")),
            ("the chance itself lands", ("return roll < chancePct;", "return roll <= chancePct;")),
            ("every roll lands", ("return roll < chancePct;", "return true;")),
            ("a roll over the chance lands", ("return roll < chancePct;", "return roll > chancePct;")),
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
        self.assertEqual(runes(), ["Enfeeblement", "Opportunist", "Borrowed Time", "Wither", "Dizzying Curse"])

    def test_the_sheet_numbers_agree_with_the_power_file(self):
        self.assertEqual([value("", t) for t in ("cost_resource", "slow_pct", "enemy_damage_pct", "duration_seconds")], [10, 75, 30, 30])  # SF_3, SF_2, SF_16
        self.assertEqual([value("Enfeeblement", t) for t in ("slow_pct", "duration_seconds")], [100, 5])  # SF_6, SF_5
        self.assertEqual([value("Opportunist", t) for t in ("movement_speed_pct", "max_bonus_pct")], [3, 30])  # SF_7 x SF_9 10
        self.assertEqual([value("Borrowed Time", t) for t in ("cooldown_reduction_pct", "max_bonus_pct")], [1, 20])  # SF_10 x SF_11 20
        self.assertEqual(value("Wither", "enemy_damage_pct"), 40)  # SF_14
        self.assertEqual([value("Dizzying Curse", t) for t in ("proc_chance_pct", "stun_duration_seconds")], [10, 2])  # SF_18, SF_19

    def test_the_decay_takes_the_rune_from_its_start_to_the_normal_in_its_seconds(self):
        decay = tune("decrepify_slow_decay_pct_per_second")
        self.assertEqual((value("Enfeeblement", "slow_pct") - value("", "slow_pct")) / decay, value("Enfeeblement", "duration_seconds"))

    def test_every_name_the_cast_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+?, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"duration_seconds", "slow_pct", "enemy_damage_pct", "movement_speed_pct", "cooldown_reduction_pct",
                                  "max_bonus_pct", "proc_chance_pct", "stun_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "slow_pct"), ("", "enemy_damage_pct"), ("", "duration_seconds"), ("Enfeeblement", "slow_pct"),
                            ("Enfeeblement", "duration_seconds"), ("Opportunist", "movement_speed_pct"), ("Opportunist", "max_bonus_pct"),
                            ("Borrowed Time", "cooldown_reduction_pct"), ("Borrowed Time", "max_bonus_pct"),
                            ("Wither", "enemy_damage_pct"), ("Dizzying Curse", "proc_chance_pct"),
                            ("Dizzying Curse", "stun_duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"decrepify_radius_yards": "20", "decrepify_slow_decay_pct_per_second": "5"}  # SF_15, SF_12

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                self.assertIn("decode_pow.py power P6_Necro_Decrepify", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.curses = squeeze(CURSES.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (auto curse = Decrepify::BasePct(spellId)) return curse;", self.dispatch)
        self.assertIn("Decrepify::Ground(player, spellId, center);", self.dispatch)
        self.assertIn("Decrepify::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("Decrepify::RegisterScripts();", self.dispatch)

    def test_the_curse_has_no_hit_of_its_own(self):
        self.assertIn("return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_the_cast_curses_every_enemy_around_the_place_for_the_skills_seconds(self):
        self.assertIn('Combat::Enemies(player, spellId, center, Tune("decrepify_radius_yards"))', self.code)
        self.assertIn('Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(Skill), "duration_seconds"))', self.code)
        self.assertIn("Curses::Put(player, enemy, spellId, seconds);", self.code)
        self.assertIn('EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), seconds);', self.code)

    def test_wither_slows_nothing_and_the_others_slow(self):
        self.assertIn("if (rune != Rune::Wither) Slow(player, enemy, Numbers::Num(spellId, \"slow_pct\"), seconds);", self.code)

    def test_enfeeblement_decays_the_slow_while_its_curse_stands(self):
        self.assertIn("if (!target || !target->IsAlive() || Curses::On(player, target, Skill) != spellId) return;", self.code)
        self.assertIn("DecayedSlow(start, base, perSecond, step * StepSeconds)", self.code)
        self.assertIn('Steps(Numbers::Num(spellId, "duration_seconds"), StepSeconds)', self.code)

    def test_opportunist_and_borrowed_time_follow_the_enemies_cursed_and_end_with_the_last(self):
        self.assertIn("Curses::Follow(player, Skill, spellId, Apply);", self.code)
        self.assertIn("Curses::Unfollow(player, Skill);", self.code)
        self.assertIn("Buffs::Set(player, spellId, Stat::MovementSpeed, Bucket::Flat, value);", self.code)
        self.assertIn("Buffs::Set(player, spellId, Stat::CooldownReduction, Bucket::Flat, value); Passives::RefreshModifiers(player);", self.code)
        self.assertIn("StackBonus(cursed, per, Numbers::Num(spellId, \"max_bonus_pct\"))", self.code)
        # The follower itself (every second while any enemy stays cursed, 0 when the last is gone) is the curses', proved in the Leech test.

    def test_dizzying_curse_stuns_a_cursed_enemy_that_is_hit_with_the_worn_powers(self):
        self.assertIn('Procs(rand_chance(), Numbers::Num(curse, "proc_chance_pct"))', self.code)
        self.assertIn('Stun(player, target, Numbers::Num(curse, "stun_duration_seconds") * ItemPowers::StunFactor(player));', self.code)

    def test_a_new_curse_replaces_the_old_and_the_old_skill_lifts_it(self):
        self.assertIn("if (!Lifts(stand, sameSkill, live, held, spellId)) return;", self.curses)
        self.assertIn("lift(player, enemy, held);", self.curses)
        self.assertIn("Curses::Define(Skill, Lift);", self.code)
        self.assertIn("Unslow(player, enemy); EnemyEffects::Remove(enemy, spellId);", self.code)


if __name__ == "__main__":
    unittest.main()
