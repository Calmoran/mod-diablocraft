"""Demon Hunter Vengeance and its five runes (src/classes/demon_hunter/dc_demon_hunter_vengeance.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_vengeance/harness.cpp compiles the real dc_demon_hunter_vengeance.h with
    the sheets' own rune names and numbers: each rune name is its rune; the four side guns, and the two cannons of Side Cannons (the
    file's split-shot multiplier of 1 against 2); a shot's angle across the file's spread; the guns waiting a share of an attack and
    the volley an attack; the nearest enemies for the rockets, round again when there are fewer enemies than rockets; Personal
    Mortar's band of enemies outside melee range; Seethe's share of a second; From the Shadows' freeze cooldown. Ten mutations planted
    in a scratch copy (two runes share a name, the cannons are not a share, the spread ignores the roll, the guns wait longer for a
    faster attacker, the volley is not an attack long, the clock is strict on the moment, the rockets do not go round again, go to the
    farthest first, the band loses an edge, Seethe's tick is a whole second) must each make it fail.
  * **The record is a form.** The shipped render gives Vengeance and its runes the sheet's 90 second cooldown and no cost; the
    cast does no damage of its own.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Vengeance (or the
    rune that states it) the engine can read: 20 seconds, four side guns of 60% and two rockets of 80%, 40% more damage, From the
    Shadows' 120% and 3 second freeze, Dark Heart's 50%, Personal Mortar's two grenades of 150%, Side Cannons' 225% and 3% of the
    maximum Life, Seethe's 10 Hatred a second; every tunable is a row of data/tunables/demonhunter.csv, and the numbers equal the
    decoded Power/X1_DemonHunter_Vengeance.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the attack, the cast, the multipliers seam and the scripts, the engine calls the seam beside the
    other classes', the guns and the volley fire only while the form lasts and never on their own strikes, and the form ends with its
    seconds, its owner's death, the map and the logout.

What it does not prove: anything on a running server. The form, the shots, the rockets, the allies, the grenades, the cannons and
Seethe are docs/test-diablocraft-vawmy.27.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_vengeance.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_vengeance.h"
SOURCES = [HEADER, "src/combat/dc_damage_buckets.h", "tests/demon_hunter_vengeance/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_vengeance.cpp"
SKILL = "Vengeance"
SHELLS = MODULE / "data/generated/spell_shells.sql"
POWER = "Power/X1_DemonHunter_Vengeance.pow"


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
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_vengeance/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("", "projectile_count", "side_guns"), tune("vengeance_split_shot_multiplier"),
                         tune("vengeance_side_cannon_multiplier"), tune("vengeance_split_shot_spread_min_degrees"),
                         tune("vengeance_split_shot_spread_degrees"), tune("vengeance_split_shot_cooldown_attacks"),
                         value("Seethe", "regen_per_second_resource"), tune("vengeance_seethe_tick_seconds"),
                         tune("vengeance_mortar_min_range_yards"), tune("vengeance_mortar_max_range_yards")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 25, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Personal Mortar")\n            return Rune::PersonalMortar;',
                                        'if (name == "Personal Mortar")\n            return Rune::DarkHeart;')),
            ("the cannons are not a share of the guns", (HEADER, "sheetCount * std::max(0.0, cannonMultiplier) / gunMultiplier", "sheetCount")),
            ("the spread ignores the roll", (HEADER, "return minDegrees + deltaDegrees * std::clamp(roll, 0.0, 1.0);", "return minDegrees;")),
            ("a faster attacker waits longer", (HEADER, "return attacksPerSecond > 0 && share > 0 ? share / attacksPerSecond : 0.0;",
                                                "return attacksPerSecond > 0 && share > 0 ? share * attacksPerSecond : 0.0;")),
            ("the volley is not an attack long", (HEADER, "return attacksPerSecond > 0 ? 1.0 / attacksPerSecond : 0.0;",
                                                  "return attacksPerSecond > 0 ? attacksPerSecond : 0.0;")),
            ("ready only after the moment", (HEADER, ">= intervalSeconds * 1000.0", "> intervalSeconds * 1000.0")),
            ("the rockets do not go round again", (HEADER, "picked.push_back(near[shot % near.size()]);", "if (shot < near.size()) picked.push_back(near[shot]);")),
            ("the rockets go to the farthest first", (HEADER, "return distances[a] < distances[b]; });\n        std::vector<std::size_t> picked;",
                                                      "return distances[a] > distances[b]; });\n        std::vector<std::size_t> picked;")),
            ("the band loses an edge", (HEADER, "if (distances[i] >= minYards && distances[i] <= maxYards)", "if (distances[i] > minYards && distances[i] <= maxYards)")),
            ("a tick is the whole second", (HEADER, "return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;",
                                            "return perSecond > 0 && tickSeconds > 0 ? perSecond : 0.0;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Records(unittest.TestCase):
    def test_the_form_has_the_sheets_cooldown_and_no_cost(self):
        render = SHELLS.read_text(encoding="utf-8")
        columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `?spell_dbc`?\s*\(([^)]*)\)", render).group(1).split(",")]
        first_string = columns.index("Name_Lang_enUS")
        ids = {r[1]: int(r[0]) for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
               if r and r[0].isdigit() and r[4] in ("active", "rune")}
        names = [n for n in ids if n == SKILL or n.startswith(SKILL + " - ")]
        self.assertEqual(len(names), 6)
        for name in names:
            with self.subTest(name):
                row = re.search(r"^\(%d,[^\n]*" % ids[name], render, re.M)[0][1:]
                record = dict(zip(columns[:first_string], row.split(",")[:first_string]))
                self.assertEqual(record["RecoveryTime"], str(int(value("", "cooldown_seconds") * 1000)))
                self.assertEqual(record["ManaCost"], "0")


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), ["From the Shadows", "Dark Heart", "Personal Mortar", "Side Cannons", "Seethe"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "duration_seconds"), value("", "damage_bonus_pct")], [90, 20, 40])
        self.assertEqual([value("", "projectile_count", "side_guns"), value("", "damage_pct", "side_guns")], [4, 60])
        self.assertEqual([value("", "projectile_count", "rockets"), value("", "damage_pct", "rockets")], [2, 80])
        self.assertEqual([value("From the Shadows", "damage_pct"), value("From the Shadows", "freeze_duration_seconds")], [120, 3])
        self.assertEqual(value("Dark Heart", "damage_reduction_pct"), 50)
        self.assertEqual([value("Personal Mortar", "projectile_count"), value("Personal Mortar", "damage_pct")], [2, 150])
        self.assertEqual([value("Side Cannons", "damage_pct"), value("Side Cannons", "heal_pct")], [225, 3])
        self.assertEqual(value("Seethe", "regen_per_second_resource"), 10)

    def test_the_tunables(self):
        rows = tunables()
        files_numbers = {
            "vengeance_missile_search_yards": ("60", "SF_5"), "vengeance_split_shot_range_yards": ("80", "SF_10"),
            "vengeance_split_shot_cooldown_attacks": ("0.9", "SF_9"), "vengeance_split_shot_spread_min_degrees": ("-2", "SF_11"),
            "vengeance_split_shot_spread_degrees": ("6", "SF_12"), "vengeance_split_shot_offset_yards": ("2.5", "SF_38"),
            "vengeance_split_shot_multiplier": ("2", "SF_14"), "vengeance_side_cannon_multiplier": ("1", "SF_14"),
            "vengeance_mortar_min_range_yards": ("20", "SF_32"), "vengeance_mortar_max_range_yards": ("60", "SF_33"),
            "vengeance_mortar_radius_yards": ("6", "SF_31"), "vengeance_shadow_ally_range_yards": ("45", "SF_43"),
            "vengeance_shadow_ally_freeze_cooldown_seconds": ("3", "SF_45"),
        }
        for name, (d3, source) in files_numbers.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""))
                self.assertIn(source, rows[name]["notes"])
                self.assertIn(POWER, rows[name]["notes"])
                self.assertNotIn("placeholder", rows[name]["notes"].lower())
        # Two the file does not give: the designer's standing defaults (AGENTS.md "Numbers", 2026-10-22), in his column.
        for name, number in (("vengeance_split_shot_width_yards", "3"), ("vengeance_seethe_tick_seconds", "0.5")):
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), ("", number))
                self.assertIn("standing default", rows[name]["notes"])
                self.assertNotIn("placeholder", rows[name]["notes"].lower())
        self.assertEqual({n for n in rows if n.startswith("vengeance_")}, set(files_numbers) | {"vengeance_split_shot_width_yards", "vengeance_seethe_tick_seconds"})

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("vengeance_")})
        reads = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"(?:, "([a-z_]+)")?', text))
        sheet = {(r["token"], r["qualifier"]) for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual({(token, qualifier) for token, qualifier in reads} - sheet, set())
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "projectile_count", "side_guns"), ("", "damage_pct", "side_guns"), ("", "projectile_count", "rockets"),
                                       ("", "damage_pct", "rockets"), ("", "damage_bonus_pct", ""), ("", "duration_seconds", ""),
                                       ("From the Shadows", "damage_pct", ""), ("From the Shadows", "freeze_duration_seconds", ""),
                                       ("Dark Heart", "damage_reduction_pct", ""), ("Personal Mortar", "projectile_count", ""),
                                       ("Personal Mortar", "damage_pct", ""), ("Side Cannons", "damage_pct", ""),
                                       ("Side Cannons", "heal_pct", ""), ("Seethe", "regen_per_second_resource", "")):
            self.assertIn((rune, token, qualifier), mapped, (rune, token, qualifier))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract(POWER))["sf"]

        def number(n):
            return float(sf[n])

        self.assertAlmostEqual(number(0), value("", "duration_seconds"))
        self.assertAlmostEqual(number(1), value("", "cooldown_seconds"))
        self.assertAlmostEqual(number(19) * 100, value("", "damage_pct", "rockets"))
        self.assertAlmostEqual(number(22) * 100, value("", "damage_pct", "side_guns"))
        self.assertAlmostEqual(number(49) * 100, value("", "damage_bonus_pct"))
        self.assertAlmostEqual(number(44) * 100, value("From the Shadows", "damage_pct"))
        self.assertAlmostEqual(number(42), value("From the Shadows", "freeze_duration_seconds"))
        self.assertAlmostEqual(number(48) * 100, value("Dark Heart", "damage_reduction_pct"))
        self.assertAlmostEqual(number(30) * 100, value("Personal Mortar", "damage_pct"))
        self.assertAlmostEqual(number(37) * 100, value("Side Cannons", "damage_pct"))
        self.assertAlmostEqual(number(36) * 100, value("Side Cannons", "heal_pct"))
        self.assertAlmostEqual(number(39), value("Seethe", "regen_per_second_resource"))
        self.assertAlmostEqual(number(4), value("", "projectile_count", "rockets"))
        self.assertAlmostEqual(number(28), value("Personal Mortar", "projectile_count"))
        for name, n in (("vengeance_missile_search_yards", 5), ("vengeance_split_shot_range_yards", 10), ("vengeance_split_shot_spread_min_degrees", 11),
                        ("vengeance_split_shot_spread_degrees", 12), ("vengeance_split_shot_offset_yards", 38), ("vengeance_mortar_min_range_yards", 32),
                        ("vengeance_mortar_max_range_yards", 33), ("vengeance_shadow_ally_range_yards", 43)):
            self.assertAlmostEqual(number(n), tune(name), msg=name)
        self.assertAlmostEqual(float(sf[9].split("/")[0]), tune("vengeance_split_shot_cooldown_attacks"))
        self.assertAlmostEqual(float(sf[31].split("*")[0]), tune("vengeance_mortar_radius_yards"))  # 6.0 x the Grenadier modifier
        self.assertAlmostEqual(number(42) * 1.0, tune("vengeance_shadow_ally_freeze_cooldown_seconds"))
        self.assertAlmostEqual(float(sf[14].split("?")[1].split(":")[1]), tune("vengeance_split_shot_multiplier"))
        self.assertAlmostEqual(float(sf[14].split("?")[1].split(":")[0]), tune("vengeance_side_cannon_multiplier"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        self.combat = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        for call in ("Vengeance::Attack(player, spellId);", "Vengeance::Cast(player, spellId);", "Vengeance::RegisterScripts();",
                     "Vengeance::Multipliers(player, out);", "if (auto form = Vengeance::BasePct(spellId)) return form;"):
            self.assertEqual(self.dispatch.count(call), 1, call)
        self.assertLess(self.dispatch.index("Vengeance::BasePct(spellId)"), self.dispatch.index("return Caltrops::BasePct(spellId);"))

    def test_the_engine_asks_the_class_beside_the_others(self):
        self.assertEqual(self.combat.count("DemonHunter::Multipliers(player, target, shell.spellId, hit.factors);"), 1)
        self.assertLess(self.combat.index("Necromancer::Multipliers(player, target, shell.spellId, hit.factors);"),
                        self.combat.index("DemonHunter::Multipliers(player, target, shell.spellId, hit.factors);"))

    def test_the_cast_does_no_damage_and_begins_the_form(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        cast = self.code[self.code.index("void Cast("):self.code.index("void Attack(")]
        self.assertIn('Numbers::Num(spellId, "duration_seconds")', cast)
        self.assertIn("form.endsAt = Now() +", cast)
        self.assertIn('Buffs::Stack(player, spellId, Stat::SpecificReduction, Bucket::Flat, Numbers::Num(spellId, "damage_reduction_pct"), 1, seconds);', cast)
        self.assertIn("RuneAt(spellId) == Rune::DarkHeart", cast)

    def test_the_guns_and_the_volley_fire_only_while_it_lasts_and_not_on_their_own_strikes(self):
        attack = self.code[self.code.index("void Attack("):self.code.index("void Multipliers(")]
        self.assertIn("if (firing || !player || Is(spellId)) return;", attack)
        self.assertIn("auto form = Active(player); if (!form) return;", attack)
        self.assertIn("Scope scope(firing);", attack)
        self.assertIn('Ready(form->lastGuns, now, GunCooldownSeconds(Tune("vengeance_split_shot_cooldown_attacks"), attacks))', attack)
        self.assertIn("rune != Rune::SideCannons && Ready(form->lastVolley, now, VolleySeconds(attacks))", attack)
        for call in ("SummonAllies(player, *form);", "LaunchGrenades(player, *form);", "FireRockets(player, *form);"):
            self.assertIn(call, attack)

    def test_the_guns_and_each_runes_second_weapon(self):
        guns = self.code[self.code.index("void FireGuns("):self.code.index("void FireRockets(")]
        self.assertIn("bool const cannons = rune == Rune::SideCannons;", guns)
        self.assertIn('Numbers::Num(form.spellId, "projectile_count", "side_guns")', guns)
        self.assertIn('Combat::Strike(player, enemy, form.spellId, pct) && cannons) Heal(player, form.spellId, player->GetMaxHealth() * Numbers::Num(form.spellId, "heal_pct") / 100.0);', guns)
        allies = self.code[self.code.index("void SummonAllies("):self.code.index("void LaunchGrenades(")]
        self.assertIn("StunFactor(player)", allies)
        self.assertIn("FreezeReady(readyAt, now)", allies)
        grenades = self.code[self.code.index("void LaunchGrenades("):self.code.index("class Forms")]
        self.assertIn("urand(0, uint32(band.size() - 1))", grenades)
        self.assertIn('Tune("vengeance_mortar_radius_yards")', grenades)

    def test_seethe_pays_on_its_ticks_and_the_form_ends_with_its_owner(self):
        update = self.code[self.code.index("void OnPlayerUpdate("):self.code.index("void OnPlayerLogout(")]
        self.assertIn("if (!player->IsAlive() || Now() >= form.endsAt) {", update)
        self.assertIn('SeethePerTick(Numbers::Num(form.spellId, "regen_per_second_resource"), tick)', update)
        self.assertIn("Generate(player, Classes::ClassIdOf(player), form.spellId, points);", update)
        self.assertIn("OnPlayerMapChanged", self.code)
        self.assertIn("OnPlayerLogout", self.code)

    def test_the_form_adds_its_increased_damage_as_a_multiplier(self):
        multipliers = self.code[self.code.index("void Multipliers("):self.code.index("void RegisterScripts(")]
        self.assertIn('AddFactor(out, "Vengeance", Numbers::Num(form->spellId, "damage_bonus_pct"));', multipliers)


if __name__ == "__main__":
    unittest.main()
