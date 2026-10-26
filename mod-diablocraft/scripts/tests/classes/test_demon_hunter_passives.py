"""The Demon Hunter's nineteen passives: Thrill of the Hunt, Tactical Advantage, Blood Vengeance, Steady Aim, Cull the Weak and
Night Stalker; Brooding, Hot Pursuit, Archery, Numbing Traps, Perfectionist and Custom Engineering; Grenadier, Sharpshooter,
Ballistics, Leech, Ambush, Awareness and Single Out
(src/classes/demon_hunter/dc_demon_hunter_passives.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_passives/harness.cpp compiles the real dc_demon_hunter_passives.h with the
    sheets' numbers: a Hatred spender is no Primary and costs Hatred (in the record or paid by the module); Tactical Advantage answers
    the three skills its tooltip names (the sheet's text is read here) and no other; Night Stalker adds its 4 to a Primary's
    generation and nothing to anything else; Steady Aim is clear with no enemy within its 10 yards, the edge counted as within, and
    lasts its seconds; Cull the Weak gives its 20% against the slowed only. Ten mutations planted in a scratch copy (a Primary a
    spender, both costs needed, a fourth skill for Tactical Advantage, Night Stalker adding to a non-Primary or to nothing, the
    edge of Steady Aim's radius outside it, any enemy clearing it, its seconds read as hundredths, Cull the Weak ignoring the slow or
    a negative percent) must each make it fail.
  * **The records and the sheets.** The six passives are passive records the engine reads; every token the .cpp reads is a row of
    demon_hunter_passive_values.csv: Thrill of the Hunt's 80% slow for 2 seconds, Tactical Advantage's 60% for 2 seconds, Blood
    Vengeance's 25 more Hatred and 30 Hatred and 3 Discipline for a globe, Steady Aim's 10 yards and 20%, Cull the Weak's 20%, Night
    Stalker's 4; every tunable is a row of data/tunables/demonhunter.csv, and the numbers equal the decoded power files (skipped
    where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the hit, the cast, the generation, the scripts and the multipliers seam, which the engine
    asks with the target and the spell; Evasive Fire's backflip calls Tactical Advantage; Blood Vengeance's pool is a contribution
    to the primary resource's maximum; the globe pay is a seam that waits for the health globes.

What it does not prove: anything on a running server. The slow, the speed, the pool, the damage bonuses and the generation are
docs/test-diablocraft-vawmy.34.md's, live. Blood Vengeance's globe pay waits for the health globes (not built).

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_passives.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as spells  # noqa: E402
import harness_env  # noqa: E402
import test_item_power_cindercoat as cindercoat  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/demon_hunter/dc_demon_hunter_passives.h"
SOURCES = [HEADER, "src/combat/dc_damage_buckets.h", "tests/demon_hunter_passives/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_passives.cpp"
PASSIVES = ["Thrill of the Hunt", "Tactical Advantage", "Blood Vengeance", "Steady Aim", "Cull the Weak", "Night Stalker", "Brooding", "Hot Pursuit",
            "Archery", "Numbing Traps", "Perfectionist", "Custom Engineering", "Grenadier", "Sharpshooter", "Ballistics",
            "Leech (Demon Hunter)", "Ambush", "Awareness", "Single Out"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(passive, token, qualifier=""):
    rows = [r for r in read(D3 / "demon_hunter_passive_values.csv")
            if (r["passive_name"] if "passive_name" in r else r["skill"], r["token"], r["qualifier"]) == (passive, token, qualifier)]
    assert len(rows) == 1, (passive, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "demonhunter.csv")}


def healing(level):
    return float(next(r for r in read(D3 / "healing_table.csv") if int(r["level"]) == level)["value"])


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def primary_generation():
    """The Hatred a Primary generates, from the skills' sheet."""
    rows = [r for r in read(D3 / "demon_hunter_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == ("Hungering Arrow", "", "generated_resource", "")]
    assert len(rows) == 1
    return float(rows[0]["value"])


def tactical_advantage_skills():
    """The skills the passive's tooltip names, other than the backflip: the catalogue's skills found in its text."""
    text = next(r["full_text"] for r in read(D3 / "demon_hunter_passives.csv") if r["passive_name"] == "Tactical Advantage")
    sentence = text.split("|")[0]
    names = [r["skill_name"] for r in read(D3 / "demon_hunter_skills.csv")]
    return [n for n in names if n in sentence and n != "Evasive Fire"]


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
    binary = harness_env.build([MODULE / "tests/demon_hunter_passives/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Night Stalker", "generated_resource"), primary_generation(), value("Steady Aim", "radius_yards"), tune("steady_aim_duration_seconds"),
               value("Cull the Weak", "damage_bonus_pct"), value("Brooding", "max_stacks_count"), value("Brooding", "duration_seconds"),
               value("Custom Engineering", "duration_bonus_pct"), value("Custom Engineering", "max_count", "sentry"),
               value("Custom Engineering", "max_count", "spike_trap"),
               value("Ballistics", "damage_bonus_pct"), value("Ballistics", "proc_chance_pct"), value("Ambush", "life_threshold_pct"),
               value("Ambush", "damage_bonus_pct"), value("Awareness", "heal_pct"), value("Awareness", "duration_seconds"),
               value("Single Out", "radius_yards"), tune("grenadier_radius_increase_pct"), tune("sharpshooter_reset_delay_seconds"),
               value("Sharpshooter", "crit_chance_pct"), tune("leech_life_on_hit_healing_share"),
               value("Grenadier", "damage_bonus_pct")] + tactical_advantage_skills()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 60, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a Primary is a spender", (HEADER, "return !primary && (hatredCost || moduleStart);", "return hatredCost || moduleStart;")),
            ("both costs are needed", (HEADER, "return !primary && (hatredCost || moduleStart);", "return !primary && (hatredCost && moduleStart);")),
            ("a fourth skill answers", (HEADER, 'skill == "Vault" ||', 'skill == "Vault" || skill == "Caltrops" ||')),
            ("Night Stalker adds to a non-Primary", (HEADER, "return primary && generated > 0 ? generated + std::max(0.0, bonus) : generated;",
                                                    "return generated > 0 ? generated + std::max(0.0, bonus) : generated;")),
            ("Night Stalker adds to nothing", (HEADER, "return primary && generated > 0 ?", "return primary ?")),
            ("the edge is outside the radius", (HEADER, "return yards <= radius;", "return yards < radius;")),
            ("any enemy clears it", (HEADER, "return std::none_of(distances.begin(), distances.end(), [radius]", "return std::any_of(distances.begin(), distances.end(), [radius]")),
            ("the seconds are hundredths", (HEADER, "seconds * 1000.0 + 0.5", "seconds * 100.0 + 0.5")),
            ("Cull the Weak ignores the slow", (HEADER, "return slowedOrChilled && pct > 0 ? pct : 0.0;", "return pct > 0 ? pct : 0.0;")),
            ("Cull the Weak takes a negative percent", (HEADER, "return slowedOrChilled && pct > 0 ? pct : 0.0;", "return slowedOrChilled ? pct : 0.0;")),
            ("Brooding gains a stack every update", (HEADER, "while (state.stillMs >= 1000.0)", "while (state.stillMs >= 100.0)")),
            ("Brooding has no most", (HEADER, "state.stacks = std::min(state.stacks + 1, most);", "state.stacks = state.stacks + 1;")),
            ("a move drops Brooding at once", (HEADER, "if (state.movingMs >= resetSeconds * 1000.0)", "if (state.movingMs >= 0.0)")),
            ("standing still does not cancel the reset", (HEADER, "state.movingMs = 0;\n        state.stillMs += diffMs;", "state.stillMs += diffMs;")),
            ("a crossbow is a hand crossbow in two hands", (HEADER, "return oneHanded ? Weapon::HandCrossbow : Weapon::Crossbow;", "return Weapon::HandCrossbow;")),
            ("a second hand crossbow needs only one", (HEADER, "bonus.second = hands >= 2;", "bonus.second = hands >= 1;")),
            ("a hand crossbow in the off hand gives nothing", (HEADER, "bonus.hand = hands >= 1;", "bonus.hand = main == Weapon::HandCrossbow;")),
            ("Custom Engineering lengthens every skill", (HEADER, "return on && CustomEngineeringSkill(skill) ? 1.0", "return on ? 1.0")),
            ("a grenade is any skill", (HEADER, 'return skill == "Grenade" ||', "return true ||")),
            ("Demolition's grenades are no grenades", (HEADER, '(skill == "Strafe" && rune == "Demolition")', "false")),
            ("Anathema's grenades are no grenades", (HEADER, '(skill == "Rain of Vengeance" && rune == "Anathema")', "false")),
            ("Cluster Arrow's explosion is not wider", (HEADER, 'return GrenadeSkill(skill, rune) || skill == "Cluster Arrow" || skill == "Spike Trap";', 'return GrenadeSkill(skill, rune) || skill == "Spike Trap";')),
            ("the Spike Trap's blast is not wider", (HEADER, 'return GrenadeSkill(skill, rune) || skill == "Cluster Arrow" || skill == "Spike Trap";', 'return GrenadeSkill(skill, rune) || skill == "Cluster Arrow";')),
            ("the Spike Trap's damage is a grenade's", (HEADER, '|| (skill == "Rain of Vengeance" && rune == "Anathema");', '|| (skill == "Rain of Vengeance" && rune == "Anathema") || skill == "Spike Trap";')),
            ("all of Cluster Arrow is a grenade", (HEADER, '(skill == "Rain of Vengeance" && rune == "Anathema");', '(skill == "Rain of Vengeance" && rune == "Anathema") || skill == "Cluster Arrow";')),
            ("the grenades do not do more", (HEADER, "inline double GrenadierFactorOf(bool on, double bonusPct)\n    {\n        return on ?", "inline double GrenadierFactorOf(bool on, double bonusPct)\n    {\n        return false ?")),
            ("the explosion is not wider", (HEADER, "return on && grenade ? 1.0 + std::max(0.0, radiusPct) / 100.0 : 1.0;", "return 1.0;")),
            ("the ring includes the engine's own", (HEADER, "if (distances[i] > base && distances[i] <= grown)", "if (distances[i] <= grown)")),
            ("a critical hit takes the stacks at once", (HEADER, "state.resetAtMs = nowMs + std::uint64_t(delaySeconds > 0 ? delaySeconds * 1000.0 + 0.5 : 0.0);", "state.resetAtMs = nowMs; state.stacks = 0;")),
            ("the stacks never go", (HEADER, "return state.resetAtMs && nowMs >= state.resetAtMs ? 0.0 : state.stacks * perStack;", "return state.stacks * perStack;")),
            ("the rocket bonus is added to nothing", (HEADER, "inline double RocketFactorOf(bool on, double bonusPct)\n    {\n        return on ? 1.0 + std::max(0.0, bonusPct) / 100.0 : 1.0;", "inline double RocketFactorOf(bool on, double bonusPct)\n    {\n        return on ? std::max(0.0, bonusPct) / 100.0 : 1.0;")),
            ("the rocket always procs", (HEADER, "return chancePct > 0 && roll * 100.0 < chancePct;", "return chancePct > 0;")),
            ("Leech forgets the Life per Kill", (HEADER, "return healingShare * healingAtLevel + killSharePct / 100.0 * lifePerKill;", "return healingShare * healingAtLevel;")),
            ("Ambush takes the threshold itself", (HEADER, "return lifePct > thresholdPct && pct > 0 ? pct : 0.0;", "return lifePct >= thresholdPct && pct > 0 ? pct : 0.0;")),
            ("Awareness saves a blow that is not fatal", (HEADER, "return ready && damage >= health;", "return ready;")),
            ("Awareness saves with no cooldown", (HEADER, "return ready && damage >= health;", "return damage >= health;")),
            ("Awareness heals each tick the whole percent", (HEADER, "maxLife * healPct / 100.0 * std::min(tickSeconds, seconds) / seconds", "maxLife * healPct / 100.0")),
            ("an enemy at the edge is alone", (HEADER, "return apart <= yards;", "return apart < yards;")),
            ("Custom Engineering lowers a larger number", (HEADER, "return on ? std::max(base, unsigned(std::max(0.0, total))) : base;", "return on ? unsigned(std::max(0.0, total)) : base;")),
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
    def test_the_six_passives_are_records_the_engine_reads(self):
        kinds = {r[1]: r[4] for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
                 if r and r[0].isdigit()}
        for name in PASSIVES:
            self.assertEqual(kinds.get(name), "passive", name)

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("Thrill of the Hunt", "slow_pct"), value("Thrill of the Hunt", "slow_duration_seconds")], [80, 2])
        self.assertEqual([value("Tactical Advantage", "movement_speed_pct"), value("Tactical Advantage", "duration_seconds")], [60, 2])
        self.assertEqual([value("Blood Vengeance", "max_pool_resource"), value("Blood Vengeance", "gain_resource", "hatred"),
                          value("Blood Vengeance", "gain_resource", "discipline")], [25, 30, 3])
        self.assertEqual([value("Steady Aim", "radius_yards"), value("Steady Aim", "damage_bonus_pct")], [10, 20])
        self.assertEqual(value("Cull the Weak", "damage_bonus_pct"), 20)
        self.assertEqual(value("Night Stalker", "generated_resource"), 4)
        self.assertEqual([value("Brooding", "life_regen_pct"), value("Brooding", "max_stacks_count"), value("Brooding", "duration_seconds")], [3, 3, 5])
        self.assertEqual([value("Hot Pursuit", "movement_speed_pct"), value("Hot Pursuit", "duration_seconds")], [20, 4])
        self.assertEqual([value("Archery", t) for t in ("damage_bonus_pct", "crit_damage_pct", "crit_chance_pct", "regen_per_second_resource")], [8, 50, 5, 1])
        self.assertEqual([value("Numbing Traps", "enemy_damage_pct"), value("Numbing Traps", "duration_seconds")], [25, 5])
        self.assertEqual([value("Perfectionist", "cost_reduction_pct"), value("Perfectionist", "resistance_pct")], [10, 10])
        self.assertEqual([value("Custom Engineering", "duration_bonus_pct"), value("Custom Engineering", "max_count", "sentry"),
                          value("Custom Engineering", "max_count", "spike_trap")], [100, 3, 5])
        self.assertEqual([value("Grenadier", "damage_bonus_pct"), value("Grenadier", "radius_bonus_pct"), value("Grenadier", "damage_pct")], [10, 20, 1000])
        self.assertEqual([value("Sharpshooter", "crit_chance_pct"), value("Sharpshooter", "duration_seconds")], [4, 1])
        self.assertEqual([value("Ballistics", "damage_bonus_pct"), value("Ballistics", "proc_chance_pct"), value("Ballistics", "damage_pct")], [100, 20, 150])
        self.assertEqual([value("Leech (Demon Hunter)", "heal_per_hit_life"), value("Leech (Demon Hunter)", "life_per_kill_share_pct")], [18507, 75])
        self.assertEqual(round(tune("leech_life_on_hit_healing_share") * healing(70)), 18507)
        self.assertEqual([value("Ambush", "damage_bonus_pct"), value("Ambush", "life_threshold_pct")], [40, 75])
        self.assertEqual([value("Awareness", "duration_seconds"), value("Awareness", "heal_pct"), value("Awareness", "internal_cooldown_seconds")], [2, 50, 60])
        self.assertEqual([value("Single Out", "crit_chance_pct"), value("Single Out", "radius_yards")], [25, 20])

    def test_tactical_advantage_names_vault_shadow_power_and_smoke_screen(self):
        self.assertEqual(sorted(tactical_advantage_skills()), ["Shadow Power", "Smoke Screen", "Vault"])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("steady_aim_check_seconds", "0.5", "SF_3"), ("steady_aim_duration_seconds", "0.7", "SF_2")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Passive_SteadyAim.pow", rows[name]["notes"])
        brooding = rows["brooding_check_seconds"]
        self.assertEqual((brooding["d3_value"], brooding["value"]), ("0.1", ""))
        self.assertIn("SF_4", brooding["notes"])
        for name, d3, source, power in (("grenadier_radius_increase_pct", "9.6", "SF_7", "DemonHunter_Passive_Grenadier"),
                                        ("sharpshooter_tick_seconds", "1", "SF_1", "DemonHunter_Passive_Sharpshooter"),
                                        ("sharpshooter_reset_delay_seconds", "1", "SF_2", "DemonHunter_Passive_Sharpshooter"),
                                        ("ballistics_rocket_range_yards", "50", "SF_3", "DemonHunter_Passive_Ballistics"),
                                        ("leech_life_on_hit_healing_share", "0.0345", "SF_0", "X1_DemonHunter_Passive_Leech"),
                                        ("single_out_check_seconds", "1", "SF_3", "X1_DemonHunter_Passive_SingleOut"),
                                        ("single_out_search_yards", "60", "SF_2", "X1_DemonHunter_Passive_SingleOut")):
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""))
                self.assertIn(source, rows[name]["notes"])
                self.assertIn(f"Power/{power}.pow", rows[name]["notes"])
        awareness = rows["awareness_regen_tick_seconds"]
        self.assertEqual((awareness["d3_value"], awareness["value"]), ("", "0.5"))
        self.assertIn("standing default", awareness["notes"])
        self.assertNotIn("placeholder", awareness["notes"].lower())
        # No power file gives the Hatred tick of a second hand crossbow: the designer's standing default for a damage over time, read as the
        # Architect's heal-over-time ruling reads it (AGENTS.md "Numbers", 2026-10-22).
        archery = rows["archery_hatred_tick_seconds"]
        self.assertEqual((archery["d3_value"], archery["value"]), ("", "0.5"))
        self.assertIn("standing default", archery["notes"])
        self.assertNotIn("placeholder", archery["notes"].lower())
        # No power file gives the refresh: the designer's standing default for a trigger check (AGENTS.md "Numbers", 2026-10-22).
        refresh = rows["passive_refresh_seconds"]
        self.assertEqual((refresh["d3_value"], refresh["value"]), ("", "0.25"))
        self.assertIn("standing default", refresh["notes"])
        self.assertNotIn("placeholder", refresh["notes"].lower())

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {"grenadier_death_radius_yards", "grenadier_death_knockback_yards", "steady_aim_check_seconds", "steady_aim_duration_seconds", "passive_refresh_seconds",
                                                                                    "brooding_check_seconds", "archery_hatred_tick_seconds", "grenadier_radius_increase_pct",
                                                                                    "sharpshooter_tick_seconds", "sharpshooter_reset_delay_seconds", "ballistics_rocket_range_yards",
                                                                                    "leech_life_on_hit_healing_share", "awareness_regen_tick_seconds", "single_out_check_seconds",
                                                                                    "single_out_search_yards"})
        reads = set(re.findall(r'Num\("([A-Za-z ]+)", "([a-z_]+)"(?:, "([a-z]+)")?\)', text))
        sheet = {(r["passive_name"] if "passive_name" in r else r["skill"], r["token"], r["qualifier"]) for r in read(D3 / "demon_hunter_passive_values.csv")}
        self.assertEqual({(a, b, c or "") for a, b, c in reads} - sheet, set())
        mapped = {(r["skill"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")}
        for key in sheet:
            if key[0] in PASSIVES:
                self.assertIn(key, mapped, key)

    def test_the_passives_read_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")

        def sf(name):
            path = f"Power/{name.replace('X1_', 'X1_DemonHunter_Passive_')}.pow" if name.startswith("X1_") else f"Power/DemonHunter_Passive_{name}.pow"
            return decode_pow.parse_power(decode_pow.extract(path))["sf"]

        thrill, tactical, vengeance, steady, cull, night = (sf(n) for n in ("ThrillOfTheHunt", "TacticalAdvantage", "Vengeance", "SteadyAim", "CullTheWeak", "NightStalker"))
        self.assertAlmostEqual(float(thrill[0]) * 100, value("Thrill of the Hunt", "slow_pct"))
        self.assertAlmostEqual(float(thrill[1]), value("Thrill of the Hunt", "slow_duration_seconds"))
        self.assertAlmostEqual(float(tactical[0]) * 100, value("Tactical Advantage", "movement_speed_pct"))
        self.assertAlmostEqual(float(tactical[1]), value("Tactical Advantage", "duration_seconds"))
        self.assertEqual(vengeance[0].split("*")[0].strip(), str(int(value("Blood Vengeance", "gain_resource", "hatred"))))
        self.assertEqual(vengeance[1].split("*")[0].strip(), str(int(value("Blood Vengeance", "gain_resource", "discipline"))))
        self.assertEqual(vengeance[2].split("*")[0].strip(), str(int(value("Blood Vengeance", "max_pool_resource"))))
        self.assertAlmostEqual(float(steady[0]) * 100, value("Steady Aim", "damage_bonus_pct"))
        self.assertAlmostEqual(float(steady[1]), value("Steady Aim", "radius_yards"))
        self.assertAlmostEqual(float(steady[3]), tune("steady_aim_check_seconds"))
        self.assertAlmostEqual(float(steady[3]) + 0.2, tune("steady_aim_duration_seconds"))
        self.assertAlmostEqual(float(cull[0].split("?")[1].split(":")[0]) * 100, value("Cull the Weak", "damage_bonus_pct"))
        self.assertAlmostEqual(float(night[0]), value("Night Stalker", "generated_resource"))
        grenadier, sharpshooter, ballistics, ambush, awareness, single = (
            sf(n) for n in ("Grenadier", "Sharpshooter", "Ballistics", "X1_Ambush", "X1_Awareness", "X1_SingleOut"))
        leech = decode_pow.parse_power(decode_pow.extract("Power/X1_DemonHunter_Passive_Leech.pow"))["sf"]
        self.assertAlmostEqual(float(grenadier[8].split("?")[1].split(":")[0]) * 100, value("Grenadier", "damage_bonus_pct"))
        self.assertAlmostEqual(float(grenadier[7].split("?")[1].split(":")[0]) * 100, tune("grenadier_radius_increase_pct"))
        self.assertAlmostEqual(float(grenadier[2]) * 100, value("Grenadier", "radius_bonus_pct"))
        self.assertAlmostEqual(float(grenadier[10]) * 100, value("Grenadier", "damage_pct"))
        self.assertAlmostEqual(float(sharpshooter[0].split("*")[0]) * 100, value("Sharpshooter", "crit_chance_pct"))
        self.assertAlmostEqual(float(sharpshooter[1]), tune("sharpshooter_tick_seconds"))
        self.assertAlmostEqual(float(sharpshooter[2]), tune("sharpshooter_reset_delay_seconds"))
        self.assertAlmostEqual(float(sharpshooter[2]), value("Sharpshooter", "duration_seconds"))
        self.assertAlmostEqual(float(ballistics[0].split("?")[1].split(":")[0]) * 100, value("Ballistics", "damage_bonus_pct"))
        self.assertAlmostEqual(float(ballistics[1].split("?")[1].split(":")[0]) * 100, value("Ballistics", "damage_pct"))
        self.assertAlmostEqual(float(ballistics[2].split("?")[1].split(":")[0]) * 100, value("Ballistics", "proc_chance_pct"))
        self.assertAlmostEqual(float(ballistics[3]), tune("ballistics_rocket_range_yards"))
        self.assertAlmostEqual(float(leech[0].split("*")[0]), tune("leech_life_on_hit_healing_share"))
        self.assertAlmostEqual(float(leech[1]) * 100, value("Leech (Demon Hunter)", "life_per_kill_share_pct"))
        self.assertAlmostEqual(float(ambush[0]) * 100, value("Ambush", "damage_bonus_pct"))
        self.assertAlmostEqual(float(ambush[1]) * 100, value("Ambush", "life_threshold_pct"))
        self.assertAlmostEqual(float(awareness[0]), value("Awareness", "duration_seconds"))
        self.assertAlmostEqual(float(awareness[1]) * float(awareness[0]) * 100, value("Awareness", "heal_pct"))
        self.assertAlmostEqual(float(awareness[2]), value("Awareness", "internal_cooldown_seconds"))
        self.assertAlmostEqual(float(single[0]) * 100, value("Single Out", "crit_chance_pct"))
        self.assertAlmostEqual(float(single[1]), value("Single Out", "radius_yards"))
        self.assertAlmostEqual(float(single[2]), tune("single_out_search_yards"))
        self.assertAlmostEqual(float(single[3]), tune("single_out_check_seconds"))
        brooding, hot, archery, numbing, perfect, engineering = (sf(n) for n in ("Brooding", "HotPursuit", "Archery", "NumbingTraps", "Perfectionist", "CustomEngineering"))
        self.assertAlmostEqual(float(brooding[0]) * 100, value("Brooding", "life_regen_pct"))
        self.assertAlmostEqual(float(brooding[1]), value("Brooding", "max_stacks_count"))
        self.assertAlmostEqual(float(brooding[2]), value("Brooding", "duration_seconds"))
        self.assertAlmostEqual(float(brooding[4]), tune("brooding_check_seconds"))
        self.assertAlmostEqual(float(hot[0].split("?")[1].split(":")[0]) * 100, value("Hot Pursuit", "movement_speed_pct"))
        self.assertAlmostEqual(float(hot[1]), value("Hot Pursuit", "duration_seconds"))
        self.assertAlmostEqual(float(archery[0]) * 100, value("Archery", "damage_bonus_pct"))
        self.assertAlmostEqual(float(archery[1]) * 100, value("Archery", "crit_damage_pct"))
        self.assertAlmostEqual(float(archery[2]) * 100, value("Archery", "crit_chance_pct"))
        self.assertAlmostEqual(float(archery[3]), value("Archery", "regen_per_second_resource"))
        self.assertAlmostEqual(float(numbing[0]) * 100, value("Numbing Traps", "enemy_damage_pct"))
        self.assertAlmostEqual(float(numbing[1]), value("Numbing Traps", "duration_seconds"))
        self.assertAlmostEqual(float(perfect[0]) * 100, value("Perfectionist", "cost_reduction_pct"))
        self.assertAlmostEqual(float(perfect[1]) * 100, value("Perfectionist", "resistance_pct"))
        self.assertAlmostEqual(float(engineering[0].split("?")[1].split(":")[0].replace("(", "").split("+")[0]) * 200, value("Custom Engineering", "duration_bonus_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        self.combat = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))
        self.flip = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter_evasive_fire.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        for call in ("Passive::Landed(player, target, spellId, critical);", "Passive::Cast(player, spellId);", "Passive::RegisterScripts();",
                     "Passive::Multipliers(player, target, spellId, out);", "Passive::Generated(player, spellId, *generated)"):
            self.assertEqual(self.dispatch.count(call), 1, call)
        self.assertIn("void Multipliers(Player* player, Unit* target, std::uint32_t spellId, Factors& out)", self.dispatch)

    def test_the_engine_asks_with_the_target_and_the_spell(self):
        self.assertEqual(self.combat.count("DemonHunter::Multipliers(player, target, shell.spellId, hit.factors);"), 1)

    def test_evasive_fires_backflip_calls_tactical_advantage(self):
        self.assertIn("Abilities::Pull(player, to); Passive::Backflipped(player);", self.flip)

    def test_thrill_of_the_hunt_slows_after_a_spender(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Cast(")]
        self.assertIn('On(player, "Thrill of the Hunt") && SpendsHatredNow(spellId)', landed)
        self.assertIn('Slow(player, target, Num("Thrill of the Hunt", "slow_pct"), Num("Thrill of the Hunt", "slow_duration_seconds"));', landed)
        spends = self.code[self.code.index("bool SpendsHatredNow("):self.code.index("// The weapon kind in a slot")]
        self.assertIn("info->PowerType == POWER_ENERGY && info->ManaCost > 0", spends)
        self.assertIn('Numbers::Get(spellId, "cost_resource", "initial")', spends)

    def test_tactical_advantage_gives_its_speed_for_its_seconds(self):
        self.assertIn('Buffs::Stack(player, Id("Tactical Advantage"), Stat::MovementSpeed, Bucket::Uncapped, Num("Tactical Advantage", "movement_speed_pct"), 1, Num("Tactical Advantage", "duration_seconds"));', self.code)

    def test_blood_vengeance_is_a_larger_primary_pool_and_a_globe_seam(self):
        sync = self.code[self.code.index("void Sync("):self.code.index("// Steady Aim: \"As long")]
        self.assertIn('Hold(player, Stat::MaxFury, Bucket::Flat, "Blood Vengeance", On(player, "Blood Vengeance") ? Num("Blood Vengeance", "max_pool_resource") : 0.0)', sync)
        globe = self.code[self.code.index("void GlobePicked("):self.code.index("void Multipliers(")]
        self.assertIn('Num("Blood Vengeance", "gain_resource", "hatred")', globe)
        self.assertIn('Num("Blood Vengeance", "gain_resource", "discipline")', globe)
        self.assertIn("Resources::Hatred", globe)
        self.assertIn("Resources::Discipline", globe)

    def test_the_two_damage_bonuses_are_factors_of_their_own(self):
        multipliers = self.code[self.code.index("void Multipliers("):self.code.index("void RegisterScripts(")]
        self.assertIn('AddFactor(out, "Steady Aim", Num("Steady Aim", "damage_bonus_pct"));', multipliers)
        self.assertIn('target->HasAuraType(SPELL_AURA_MOD_DECREASE_SPEED)', multipliers)
        self.assertIn('AddFactor(out, "Cull the Weak", pct);', multipliers)

    def test_steady_aim_checks_on_its_own_interval_and_holds_its_duration(self):
        check = self.code[self.code.index("void CheckSteadyAim("):self.code.index("class Update")]
        self.assertIn('Combat::Enemies(player, Id("Steady Aim"), player->GetPosition(), Num("Steady Aim", "radius_yards"))', check)
        self.assertIn('Until(Now(), Tune("steady_aim_duration_seconds"))', check)
        self.assertIn('Due(steadyClock[guid], diff, Tune("steady_aim_check_seconds") * 1000.0)', self.code)

    def test_the_sheet_only_passives_are_contributions_the_script_keeps(self):
        sync = self.code[self.code.index("void Sync("):self.code.index("// Steady Aim: \"As long")]
        for line in ('"Perfectionist", perfect ? Num("Perfectionist", "resistance_pct") : 0.0)', 'Hold(player, Stat::Armor, Bucket::Percent, "Perfectionist"',
                     'Hold(player, Stat::AllResistance, Bucket::Percent, "Perfectionist"',
                     'Hold(player, Stat::CritDamage, Bucket::Flat, "Archery", bow.crossbow ? Num("Archery", "crit_damage_pct") : 0.0)',
                     'Hold(player, Stat::CritChance, Bucket::Flat, "Archery", bow.hand ? Num("Archery", "crit_chance_pct") : 0.0)'):
            self.assertIn(line, sync)
        self.assertIn("Sync(player)", self.code[self.code.index("void OnPlayerUpdate("):])

    def test_brooding_steps_on_its_own_clock_and_holds_a_regeneration(self):
        step = self.code[self.code.index("void StepBrooding("):self.code.index("class Update")]
        self.assertIn("BroodingStep(state, player->isMoving(), diff,", step)
        self.assertIn('Hold(player, Stat::LifeRegen, Bucket::Percent, "Brooding", stacks * Num("Brooding", "life_regen_pct"))', step)
        self.assertIn('Due(broodingClock[guid], diff, Tune("brooding_check_seconds") * 1000.0)', self.code)

    def test_hot_pursuit_and_numbing_traps_ride_the_hit(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Slowed(")]
        self.assertIn('Buffs::Stack(player, Id("Hot Pursuit"), Stat::MovementSpeed, Bucket::Uncapped, Num("Hot Pursuit", "movement_speed_pct"), 1, Num("Hot Pursuit", "duration_seconds"));', landed)
        self.assertIn("NumbingTrapsSkill(row->skill)) Numb(player, target);", landed)
        self.assertIn('EnemyEffects::Weaken(enemy, Id("Numbing Traps"), Num("Numbing Traps", "enemy_damage_pct"), Num("Numbing Traps", "duration_seconds"));', self.code)

    def test_the_classes_slow_weakens_the_enemy_it_slows(self):
        effects = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter_effects.cpp").read_text(encoding="utf-8"))
        slow = effects[effects.index("void Slow("):effects.index("void Stun(")]
        self.assertIn("Hold(player, target, SlowHold, seconds, -static_cast<int>(std::lround(pct))); Passive::Slowed(player, target);", slow)

    def test_archery_gives_the_bow_its_damage_and_a_second_hand_crossbow_its_hatred(self):
        self.assertIn('if (On(player, "Archery") && ArcheryHeld(player).bow) AddFactor(out, "Archery", Num("Archery", "damage_bonus_pct"));', self.code)
        self.assertIn('tick && On(player, "Archery") && ArcheryHeld(player).second', self.code)
        self.assertIn('Num("Archery", "regen_per_second_resource") * Tune("archery_hatred_tick_seconds")', self.code)
        weapon = self.code[self.code.index("Weapon WeaponIn("):self.code.index("Archery ArcheryHeld(")]
        self.assertIn("INVTYPE_WEAPON ||", weapon)
        self.assertIn("WeaponOf(worn->SubClass, oneHanded)", weapon)

    def test_perfectionist_is_a_real_cut_on_every_discipline_skill_not_a_refund(self):
        code = re.sub(r"\s+", " ", self.code)
        cut = code[code.index("void PerfectionistCut("):code.index("// The sheet contributions of the passives that only change the sheet")]
        self.assertIn("perfect == (perfecting.count(guid) > 0)", cut)
        self.assertIn('for (std::string_view skill : DisciplineSkills) CostCut::Stand(player, skill, Id("Perfectionist"), perfect ? Num("Perfectionist", "cost_reduction_pct") : 0.0);', cut)
        self.assertIn("PerfectionistCut(player, perfect);", code)
        self.assertIn('#include "../../combat/dc_cost_cut.h"', self.code)
        for gone in ("PaidBack", "CastHook", "GetPowerCost", "dc_demon_hunter_passives_cast"):
            self.assertFalse(gone in self.code or gone in (MODULE / HEADER).read_text(encoding="utf-8"), gone)
        listed = re.search(r"DisciplineSkills\[\] = \{([^}]*)\}", self.code)[1]
        skills = re.findall(r'"([^"]+)"', listed)
        sheet = [r["skill_name"] for r in read(D3 / "demon_hunter_skills.csv") if r["resource"] == "discipline" and r["resource_cost"]]
        self.assertEqual(sorted(sheet), sorted(skills))                                   # every skill that costs Discipline, no other
        for skill in skills:
            self.assertIn(skill, spells.CLASS_COST_CUT_SKILLS)                            # each has the hidden cost aura the cut lowers

    def test_each_discipline_skill_has_its_own_cost_aura_reaching_its_records_alone(self):
        records, manifest = cindercoat.records(), cindercoat.manifest()
        family = cindercoat.FAMILIES["Demon Hunter"]
        for skill in re.findall(r'"([^"]+)"', re.search(r"DisciplineSkills\[\] = \{([^}]*)\}", self.code)[1]):
            with self.subTest(skill=skill):
                aura = next(i for i, r in manifest.items() if r["kind"] == "skill_cost_modifier" and r["name"] == "%s cost reduction" % skill)
                mask = cindercoat.words(records[aura], "EffectSpellClassMaskA_%d")
                self.assertEqual(1, bin(mask[0]).count("1"))
                self.assertEqual((0, 0), mask[1:])
                reached = {i for i, r in records.items() if cindercoat.affected(r, family, mask)}
                self.assertEqual({skill}, {records[i]["Name_Lang_enUS"].split(" - ")[0] for i in reached})
                self.assertIn('{"%s", %d},' % (skill, aura), cindercoat.HEADER.read_text(encoding="utf-8"))

    def test_custom_engineering_answers_the_skills_that_ask(self):
        self.assertIn('DurationFactorOf(On(player, "Custom Engineering"), skill, Num("Custom Engineering", "duration_bonus_pct"))', self.code)
        self.assertIn('MostStandingOf(On(player, "Custom Engineering"), base, Num("Custom Engineering", "max_count", kind))', self.code)

    def test_caltrops_asks_for_its_longer_seconds(self):
        caltrops = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter_caltrops.cpp").read_text(encoding="utf-8"))
        self.assertIn('trap.left = Numbers::Num(trap.spellId, "duration_seconds") * Passive::DurationFactor(player, "Caltrops") * 1000.0;', caltrops)

    def test_sharpshooter_stacks_on_its_tick_and_resets_after_a_critical_hit(self):
        self.assertIn('Due(sharpClock[guid], diff, Tune("sharpshooter_tick_seconds") * 1000.0)', self.code)
        self.assertIn("state = SharpTick(state, Now());", self.code)
        landed = self.code[self.code.index("void Landed("):self.code.index("void Slowed(")]
        self.assertIn('if (critical && On(player, "Sharpshooter")) {', landed)
        self.assertIn('state = SharpCrit(state, Now(), Tune("sharpshooter_reset_delay_seconds"));', landed)
        self.assertIn('Hold(player, Stat::CritChance, Bucket::Flat, "Sharpshooter", worth)', self.code)
        self.assertIn('worth = SharpWorth(state, Now(), Num("Sharpshooter", "crit_chance_pct"));', self.code)

    def test_ballistics_raises_the_rockets_and_fires_one_on_an_attack(self):
        attack = self.code[self.code.index("void Attack("):self.code.index("double RocketFactor(")]
        self.assertIn('Procs(frand(0.0f, 1.0f), Num("Ballistics", "proc_chance_pct"))', attack)
        self.assertIn('Combat::Strike(player, nearest, Id("Ballistics"), Num("Ballistics", "damage_pct"));', attack)
        self.assertIn('RocketFactorOf(On(player, "Ballistics"), Num("Ballistics", "damage_bonus_pct"))', self.code)
        self.assertEqual(self.dispatch.count("Passive::Attack(player, spellId);"), 1)
        vengeance = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter_vengeance.cpp").read_text(encoding="utf-8"))
        rapid = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter_rapid_fire.cpp").read_text(encoding="utf-8"))
        self.assertIn('Numbers::Num(form.spellId, "damage_pct", "rockets") * Passive::RocketFactor(player)', vengeance)
        self.assertIn('Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(player)', rapid)

    def test_leech_ambush_and_grenadier_ride_the_sheet_and_the_hit(self):
        self.assertIn('LeechLifePerHit(Tune("leech_life_on_hit_healing_share"), Healing::At(player->GetLevel()), Num("Leech (Demon Hunter)", "life_per_kill_share_pct"), LifePerKill(player))', self.code)
        self.assertIn('Hold(player, Stat::LifePerHit, Bucket::Flat, "Leech (Demon Hunter)"', self.code)
        multipliers = self.code[self.code.index("void Multipliers("):self.code.index("void Attack(")]
        self.assertIn('AmbushPct(target->GetHealthPct(), Num("Ambush", "life_threshold_pct"), Num("Ambush", "damage_bonus_pct"))', multipliers)
        self.assertIn('AddFactor(out, "Ambush", pct);', multipliers)
        self.assertIn('On(player, "Grenadier") && IsGrenade(spellId)', multipliers)
        self.assertIn('AddFactor(out, "Grenadier", Num("Grenadier", "damage_bonus_pct"));', multipliers)

    def test_grenadiers_larger_explosion_reaches_every_grenade(self):
        self.assertIn("Passive::Ground(player, spellId, center);", self.dispatch)
        ground = self.code[self.code.index("void Ground("):self.code.index("double CritBonus(")]
        self.assertIn('std::string_view(row->skill) != "Grenade" || std::string_view(row->rune) == "Cluster Grenades"', ground)
        self.assertIn("Ring(distances, base, grown)", ground)
        for path, anchor in (("dc_demon_hunter_vengeance.cpp", 'Passive::GrenadeRadius(player, form.spellId, Tune("vengeance_mortar_radius_yards"))'),
                             ("dc_demon_hunter_rapid_fire.cpp", 'Passive::GrenadeRadius(player, spellId, Numbers::Num(spellId, "radius_yards"))'),
                             ("dc_demon_hunter_grenade.cpp", 'Passive::GrenadeRadius(player, spellId, Numbers::Num(spellId, "radius_yards"))'),
                             ("dc_demon_hunter_grenade.cpp", 'Passive::GrenadeRadius(player, spellId, Tune("grenade_cloud_radius_yards"))')):
            text = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter" / path).read_text(encoding="utf-8"))
            self.assertIn(anchor, text, (path, anchor))

    def test_grenadier_and_ballistics_reach_every_skill_whose_power_file_names_them(self):
        # The power files' own list (the Reviewer's return of vawmy.36): every Demon Hunter skill whose Power/*.pow reads the passive.
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        found = {"Grenadier": set(), "Ballistics": set()}
        for skill in sorted({r["skill_name"] for r in read(D3 / "demon_hunter_skills.csv")}):
            pascal = "".join(word.capitalize() for word in re.split(r"\W+", skill) if word)
            for name in (f"DemonHunter_{pascal}", f"DemonHunter_{pascal}s", f"X1_DemonHunter_{pascal}"):
                try:
                    data = decode_pow.extract(f"Power/{name}.pow")
                except BaseException:
                    continue
                if not data:
                    continue
                for formula in decode_pow.parse_power(data)["sf"].values():
                    for passive in found:
                        if f"DemonHunter_Passive_{passive}." in str(formula):
                            found[passive].add(skill)
                break
        wired_grenadier = {"Grenade", "Rapid Fire", "Vengeance", "Strafe", "Rain of Vengeance", "Cluster Arrow", "Spike Trap"}
        wired_ballistics = {"Rapid Fire", "Vengeance", "Cluster Arrow", "Multishot", "Strafe", "Sentry"}
        self.assertEqual(found["Grenadier"], wired_grenadier)
        self.assertEqual(found["Ballistics"], wired_ballistics)

    def test_each_skill_the_power_files_name_asks_the_seams(self):
        def source(name):
            return re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter" / name).read_text(encoding="utf-8"))

        # Spike Trap's SF_1 'Grenade Damage Radius' = 9 * Grenadier's radius multiplier: the trap's blast, which every rune lays, grows by
        # the passive's radius share; the passive's damage is not in the file (the trap is not a grenade skill as a whole).
        trap = source("dc_demon_hunter_spike_trap.cpp")
        lay = trap[trap.index("void Lay("):trap.index("} // namespace")]
        squeezed = lay.replace(" ", "")
        self.assertIn("setup.spec.radiusYards=Passive::GrenadeRadius(player,spellId,BlastRadius(rune,Numbers::Num(spellId,\"radius_yards\"),", squeezed)
        cluster = source("dc_demon_hunter_cluster_arrow.cpp")
        explode = cluster[cluster.index("void Explode("):cluster.index("void Grenades(")]
        self.assertIn('Passive::GrenadeRadius(player, spellId, Tune("cluster_arrow_grenade_radius_yards"))', explode)
        self.assertIn("Combat::Strike(player, enemy, spellId, pct * Passive::GrenadierFactor(player));", explode)
        rockets = cluster[cluster.index("void Rockets("):cluster.index("void Bombs(")]
        self.assertIn('Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(player))', rockets)
        multishot = source("dc_demon_hunter_multishot.cpp")
        self.assertIn('spellId, Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(player));', multishot[multishot.index("void Rocket("):])
        strafe = source("dc_demon_hunter_strafe.cpp")
        shot = strafe[strafe.index("if (RuneAt(spellId) == Rune::Demolition)"):strafe.index("Combat::Connected(player, spellId, 1);")]
        self.assertIn('Passive::GrenadeRadius(player, spellId, Numbers::Num(spellId, "radius_yards"))', shot)
        rocket = strafe[strafe.index("void Rocket("):strafe.index("void KeepSlow(")]
        self.assertIn('RapidFire::ShotPct(Numbers::Num(spellId, "damage_pct"), Tune("strafe_rockets_per_attack")) * Passive::RocketFactor(player)', rocket)
        rain = source("dc_demon_hunter_rain_of_vengeance.cpp")
        grenades = rain[rain.index("void Grenades("):rain.index("// Flying Strike")]
        self.assertIn('Passive::GrenadeRadius(player, spellId, Tune("rain_of_vengeance_grenade_radius_yards"))', grenades)
        sentry = source("dc_demon_hunter_sentry.cpp")
        spitfire = sentry[sentry.index("void Rocket("):sentry.index("void Chill(")]
        self.assertIn('Combat::Strike(owner, enemy, spellId, Numbers::Num(spellId, "damage_pct") * Passive::RocketFactor(owner))', spitfire)
        for name in ("cluster_arrow", "multishot", "strafe", "rain_of_vengeance", "sentry"):
            self.assertIn('#include "dc_demon_hunter_passives.h"', (MODULE / f"src/classes/demon_hunter/dc_demon_hunter_{name}.cpp").read_text(encoding="utf-8"), name)
        # Cluster Arrow's damage factor is asked inside its grenades only: the record-wide answer (Multipliers) would reach its impact and rockets too.
        header = (MODULE / HEADER).read_text(encoding="utf-8")
        self.assertNotIn('"Cluster Arrow" && rune', header[header.index("inline bool GrenadeSkill("):header.index("inline bool GrenadeRadiusSkill(")])
        self.assertIn('GrenadeRadiusSkill(row->skill, row->rune)', self.code[self.code.index("double GrenadeRadius("):self.code.index("void Ground(")])
        self.assertIn("RocketFactorOf(", self.code)
        self.assertIn('GrenadierFactorOf(On(player, "Grenadier"), Num("Grenadier", "damage_bonus_pct"))', self.code)

    def test_awareness_saves_a_fatal_blow_once_in_its_cooldown(self):
        fatal = self.code[self.code.index("void Fatal("):self.code.index("void RegisterScripts(")]
        self.assertIn('Saves(player->GetHealth(), damage, !player->HasSpellCooldown(id))', fatal)
        self.assertIn('player->AddSpellCooldown(id, 0, std::uint32_t(Num("Awareness", "internal_cooldown_seconds") * 1000.0), true);', fatal)
        self.assertIn("damage = 0;", fatal)
        self.assertIn("Vanish(player, seconds);", fatal)
        self.assertIn('AwarenessPerTick(player->GetMaxHealth(), Num("Awareness", "heal_pct"), seconds, tick)', fatal)
        self.assertIn("Passive::Fatal(player, damage);", self.dispatch)
        hooks = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat_hooks.cpp").read_text(encoding="utf-8"))
        self.assertEqual(hooks.count("Crusader::Fatal(player, damage); DemonHunter::Fatal(player, damage);"), 1)

    def test_single_out_adds_its_chance_against_an_enemy_found_alone(self):
        self.assertIn("return Vault::CritBonus(spellId) + Multishot::CritBonus(target) + Passive::CritBonus(player, target);", self.dispatch)
        self.assertEqual(self.combat.count("DemonHunter::CritBonus(player, target, shell.spellId)"), 1)
        look = self.code[self.code.index("void LookForSingles("):self.code.index("class Update")]
        self.assertIn('Tune("single_out_search_yards")', look)
        self.assertIn('Isolated(others, Num("Single Out", "radius_yards"))', look)
        bonus = self.code[self.code.index("double CritBonus("):self.code.index("void Fatal(")]
        self.assertIn('singled.find(player->GetGUID().GetRawValue())', bonus)
        self.assertIn('Num("Single Out", "crit_chance_pct")', bonus)

    def test_night_stalker_adds_to_the_sheets_generation(self):
        self.assertIn('GeneratedWith(IsPrimary(spellId), generated, Num("Night Stalker", "generated_resource"))', self.code)


class GrenadiersDeath(unittest.TestCase):
    """Grenadier's giant grenade hits as Fire: it strikes with a record of its own, because the passive's record is Physical and a
    passive's shell deals no hit."""

    SHELLS = MODULE / "data/generated/spell_shells.sql"

    def blast(self):
        rows = [r for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
                if r and r[1] == "Grenadier - giant grenade"]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_the_record_is_a_fire_helper_in_the_demon_hunters_block(self):
        spell_id, _name, element, _base, kind = self.blast()
        self.assertEqual((element, kind), ("fire", "strike_helper"))
        self.assertTrue(85900 <= int(spell_id) <= 85999, spell_id)
        helpers = {r[0]: r for r in csv.reader((MODULE / "data/generated/spell_helper_ids.csv").read_text(encoding="utf-8").splitlines()) if r}
        self.assertEqual(helpers["Grenadier - giant grenade"][1:], [spell_id, "demon_hunter"])

    def test_the_render_gives_it_the_fire_school(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_class_records import split_values
        render = self.SHELLS.read_text(encoding="utf-8")
        columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `?spell_dbc`?\s*\(([^)]*)\)", render).group(1).split(",")]
        line = re.search(r"^\(%s,.*\)[,;]$" % self.blast()[0], render, re.M)[0]
        record = dict(zip(columns, split_values(line[1:-2])))
        self.assertEqual(int(record["SchoolMask"]), 4)  # SPELL_SCHOOL_MASK_FIRE
        migrations = [p for p in (MODULE / "data/sql/db-world/updates").glob("combat_*.sql") if p.read_bytes() == self.SHELLS.read_bytes()]
        self.assertEqual(len(migrations), 1, [p.name for p in migrations])

    def test_the_module_can_find_the_record_and_the_engine_loads_it(self):
        header = (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertIn('{%s, "Grenadier - giant grenade", 0},' % self.blast()[0], header)
        self.assertIn('inline constexpr char const* StrikeHelpers[] = {\n    "Grenadier - giant grenade",', header)
        engine = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))
        loader = engine[engine.index("for (char const* name : Shells::StrikeHelpers)"):engine.index("// Pylons P2: Conduit's strike")]
        self.assertIn("Shells::HelperFor(name)", loader)
        self.assertIn("shell.element = ElementOfSchool(info->SchoolMask);", loader)
        self.assertIn("loaded[shell.spellId] = shell;", loader)
        passives = (MODULE / "src/classes/demon_hunter/dc_demon_hunter_passives.h").read_text(encoding="utf-8")
        self.assertIn('GrenadierBlast = "Grenadier - giant grenade"', passives)
        generator = (MODULE / "scripts/generate/classes/generate_spells.py").read_text(encoding="utf-8")
        self.assertIn('GRENADIER_BLAST = "Grenadier - giant grenade"', generator)
        self.assertIn('helper_for(GRENADIER_BLAST, "fire", "strike_helper")', generator)

    def test_the_grenade_falls_where_the_demon_hunter_does_and_hits_as_the_file_says(self):
        code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        drop = code[code.index("void DropGrenade("):code.index("// Tactical Advantage:")]
        self.assertIn("Shells::HelperFor(GrenadierBlast)", drop)
        self.assertIn('Tune("grenadier_death_radius_yards") * RadiusFactor(true, true, Tune("grenadier_radius_increase_pct"))', drop)
        self.assertIn('Combat::Strike(player, enemy, blast, Num("Grenadier", "damage_pct"));', drop)
        self.assertIn('Abilities::Knockback(player, enemy, Tune("grenadier_death_knockback_yards"));', drop)
        self.assertLess(drop.index("Combat::Strike"), drop.index("Abilities::Knockback"))
        fatal = code[code.index("void Fatal("):code.index("void RegisterScripts(")]
        self.assertIn('if (On(player, "Grenadier") && damage >= player->GetHealth()) DropGrenade(player);', fatal)
        # A blow Awareness saved is no death: the grenade follows only when the save did not take it.
        self.assertLess(fatal.index("return;"), fatal.index("DropGrenade(player)"))

    def test_the_giant_grenade_gets_the_grenade_damage_bonus(self):
        code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        multipliers = code[code.index("void Multipliers("):code.index("void Attack(")]
        self.assertIn("IsGrenade(spellId)", multipliers)
        self.assertIn("if (spellId == Shells::HelperFor(GrenadierBlast)) return true;", code)
        self.assertIn('AddFactor(out, "Grenadier", Num("Grenadier", "damage_bonus_pct"))', multipliers)

    def test_the_numbers_are_the_power_files(self):
        rows = tunables()
        for name, d3, source in (("grenadier_death_radius_yards", "15", "SF_3"), ("grenadier_death_knockback_yards", "50", "SF_4")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Passive_Grenadier.pow", rows[name]["notes"])
        self.assertEqual(value("Grenadier", "damage_pct"), 1000)
        import decode_pow
        if decode_pow.available():
            sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Passive_Grenadier.pow"))["sf"]
            self.assertEqual(sf[3].split("*")[0].strip(), "15")
            self.assertAlmostEqual(float(sf[4]), 50.0)
            self.assertAlmostEqual(float(sf[10]) * 100, value("Grenadier", "damage_pct"))


if __name__ == "__main__":
    unittest.main()
