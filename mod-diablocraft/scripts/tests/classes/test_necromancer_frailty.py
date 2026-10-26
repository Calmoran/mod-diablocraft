"""Frailty and its five runes (src/classes/necromancer/dc_necromancer_frailty*.{h,cpp}); the minions' bonus against an enemy
(combat/dc_minions*) and the curses' CursedBy (dc_necromancer_curses.*).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_frailty/harness.cpp compiles the real dc_necromancer_frailty_math.h with the
    sheet's rune names and thresholds: each name is its rune; the curse kills under the threshold and not at it; Early Grave's is higher.
    Planted mutations must each turn it red.
  * **The numbers.** The sheet rows come from the tooltip and agree with the power file (decode_pow.py power P6_Necro_Frailty: SF_5 0.15,
    SF_3 0.18, SF_2 2, SF_6 1.0, SF_7 0.15, SF_8 15, SF_10 0.5, SF_16 30); the radius, the life cost, the aura tick and most increase and
    the explosion radius are tunables with their SF cited; the check every 0.25 s is the designer's standing default.
  * **It is wired.** The dispatch answers BasePct, Casting, Ground and RegisterScripts; the cast curses through the registry; the check; each
    rune's part; every minion kind carries the bonus against the cursed and the minions read it.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_frailty.py
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
HEADER = "src/classes/necromancer/dc_necromancer_frailty_math.h"
HARNESS = MODULE / "tests/necromancer_frailty/harness.cpp"
CODE = FOLDER / "dc_necromancer_frailty.cpp"
PETS = FOLDER / "dc_necromancer_pets.cpp"
SKILL = "Frailty"


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
    numbers = [value("", "life_threshold_pct"), value("Early Grave", "life_threshold_pct")]
    return harness_env.run([str(binary)] + runes() + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 8, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::AuraOfFrailty;\n        return Rune::None;', 'return Rune::ScentOfBlood;\n        return Rune::None;')),
            ("a rune is no rune", ('if (name == "Early Grave")', 'if (name == "Early Graves")')),
            ("the threshold itself dies", ("return lifePct < thresholdPct;", "return lifePct <= thresholdPct;")),
            ("above the threshold dies", ("return lifePct < thresholdPct;", "return lifePct > thresholdPct;")),
            ("everything dies", ("return lifePct < thresholdPct;", "return true;")),
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
        self.assertEqual(runes(), ["Early Grave", "Harvest Essence", "Volatile Death", "Scent of Blood", "Aura of Frailty"])

    def test_the_sheet_numbers_agree_with_the_power_file(self):
        self.assertEqual([value("", t) for t in ("cost_resource", "life_threshold_pct", "duration_seconds")], [10, 15, 30])  # SF_5, SF_16
        self.assertEqual(value("Early Grave", "life_threshold_pct"), 18)  # SF_3
        self.assertEqual(value("Harvest Essence", "gain_resource"), 2)  # SF_2
        self.assertEqual(value("Volatile Death", "damage_pct"), 100)  # SF_6
        self.assertEqual(value("Scent of Blood", "damage_taken_pct"), 15)  # SF_7
        self.assertEqual([value("Aura of Frailty", t) for t in ("radius_yards", "radius_share_pct")], [15, 50])  # SF_8, SF_10

    def test_every_name_the_cast_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+?, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"duration_seconds", "life_threshold_pct", "radius_yards", "radius_share_pct", "gain_resource",
                                  "damage_pct", "damage_taken_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "life_threshold_pct"), ("", "duration_seconds"), ("Early Grave", "life_threshold_pct"),
                            ("Harvest Essence", "gain_resource"), ("Volatile Death", "damage_pct"),
                            ("Scent of Blood", "damage_taken_pct"), ("Aura of Frailty", "radius_yards"),
                            ("Aura of Frailty", "radius_share_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"frailty_radius_yards": "20", "early_grave_life_cost_pct": "10", "frailty_aura_tick_seconds": "0.5",
               "frailty_aura_max_increase_yards": "20", "volatile_death_radius_yards": "12",
               "frailty_check_seconds": "0.25"}  # SF_15, SF_4, SF_9, SF_11, SF_12, the standing default

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                if name == "frailty_check_seconds":
                    self.assertIn("standing default", rows[name]["notes"])
                else:
                    self.assertIn("decode_pow.py power P6_Necro_Frailty", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.pets = squeeze(PETS.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))
        self.minions = squeeze((MODULE / "src/combat/dc_minions.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (auto frailty = Frailty::BasePct(spellId)) return frailty;", self.dispatch)
        self.assertIn("Frailty::Casting(player, spellId);", self.dispatch)
        self.assertIn("Frailty::Ground(player, spellId, center);", self.dispatch)
        self.assertIn("Frailty::RegisterScripts();", self.dispatch)

    def test_the_cast_curses_the_enemies_around_the_place_and_starts_the_check(self):
        self.assertIn('Combat::Enemies(player, spellId, center, Tune("frailty_radius_yards"))', self.code)
        self.assertIn('Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(Skill), "duration_seconds"))', self.code)
        self.assertIn("Curses::Put(player, enemy, spellId, Passive::CurseSeconds(player, seconds));", self.code)
        self.assertIn("StartReaping(player);", self.code)

    def test_the_check_kills_the_cursed_under_the_runes_threshold(self):
        self.assertIn('if (Executes(enemy->GetHealthPct(), Numbers::Num(curse, "life_threshold_pct"))) Unit::Kill(player, enemy);', self.code)
        self.assertIn('std::chrono::milliseconds(Millis(Tune("frailty_check_seconds")))', self.code)
        self.assertIn("if (found == checkers.end() || found->second != stamp) return;", self.code)

    def test_early_grave_takes_its_life_as_the_cast_begins(self):
        self.assertIn('if (player && RuneAt(spellId) == Rune::EarlyGrave) SpendLife(player, Tune("early_grave_life_cost_pct"));', self.code)

    def test_harvest_essence_and_volatile_death_answer_the_death_of_a_cursed_enemy(self):
        self.assertIn('PayEssence(player, curse, Numbers::Num(curse, "gain_resource"));', self.code)
        self.assertIn('Combat::Enemies(player, curse, victim->GetPosition(), Tune("volatile_death_radius_yards"))', self.code)
        self.assertIn('Combat::Strike(player, enemy, curse, Numbers::Num(curse, "damage_pct"));', self.code)

    def test_the_aura_curses_everything_around_the_necromancer_for_a_tick_or_two(self):
        self.assertIn("Devour::AuraRadius(Numbers::Num(spellId, \"radius_yards\"), Numbers::Num(spellId, \"radius_share_pct\"),", self.code)
        self.assertIn("Curses::Put(player, enemy, spellId, tick * 2);", self.code)
        self.assertIn("Aura(player, spellId, tick > 0 ? unsigned(seconds / tick + 1e-9) : 0u);", self.code)

    def test_every_minion_deals_more_to_the_enemies_scent_of_blood_curses(self):
        self.assertIn('return curse && RuneAt(curse) == Rune::ScentOfBlood ? Numbers::Num(curse, "damage_taken_pct") : 0.0;', self.code)
        self.assertEqual(self.pets.count("kind.bonusAgainst = Frailty::MinionBonus;"), 5)
        self.assertIn("kind.bonusAgainst ? kind.bonusAgainst(player, target) : 0.0", self.minions)
        self.assertIn("BoostedPct(kind.auraPct, kind.bonusAgainst ? kind.bonusAgainst(player, enemy) : 0.0)", self.minions)


if __name__ == "__main__":
    unittest.main()
