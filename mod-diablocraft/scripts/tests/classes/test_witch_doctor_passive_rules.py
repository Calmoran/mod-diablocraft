"""Witch Doctor passives of the second and third group (src/classes/witch_doctor/dc_witch_doctor_passive_rules.h and the files named for
what they do: damage, mana, survival and pet passives).

What this proves, and how:

  * **The logic that needs no core type.** tests/witch_doctor_passive_rules/harness.cpp compiles the real
    dc_witch_doctor_passive_rules.h with the sheets' numbers: Pierce the Veil's extra cost; Spirit Vessel's fatal blow, cooldown and
    window; Rush of Essence's running streams and points a second; Vision Quest's share of the
    class's regeneration; Fierce Loyalty's speed. Mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every passive number the code reads is a row of witch_doctor_passive_values.csv under the
    passive's name; the skills Rush of Essence and Vision Quest name are the ones their tooltips name; every tunable is a row of
    data/tunables/witchdoctor.csv; the numbers equal the decoded Power/Witchdoctor_Passive_*.pow (skipped where the game archives are
    not on this machine).
  * **The wiring.** The dispatch answers the seams (Multipliers, Reduce, RegisterScripts) and the engine calls them; each passive rides
    the hook it needs: the multiplier, the cast, the hit, the damage taken, the update script.

What it does not prove: anything on a running server. The passives are docs/test-diablocraft-vxrcu.32.md's and .33's, live. What
Zombie Handler, Midnight Feast and Fetish Sycophants give the pets is the pets' piece's (tests/witch_doctor_pets).

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_passive_rules.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_passive_rules.h"
SOURCES = [HEADER, "tests/witch_doctor_passive_rules/harness.cpp"]
WD = MODULE / "src/classes/witch_doctor"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(passive, token, qualifier=""):
    rows = [r for r in read(D3 / "witch_doctor_passive_values.csv") if (r["skill"], r["token"], r["qualifier"]) == (passive, token, qualifier)]
    assert len(rows) == 1, (passive, token, qualifier, len(rows))
    return float(rows[0]["value"])


def text_of(passive):
    return next(r["full_text"] for r in read(D3 / "witch_doctor_passives.csv") if r["passive_name"] == passive)


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "witchdoctor.csv")}


def code(name):
    return re.sub(r"\s+", " ", (WD / name).read_text(encoding="utf-8"))


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
    binary = harness_env.build([MODULE / "tests/witch_doctor_passive_rules/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Pierce the Veil", "cost_increase_pct"), value("Spirit Vessel", "duration_seconds"),
               value("Spirit Vessel", "internal_cooldown_seconds"), value("Rush of Essence", "gain_resource"),
               value("Rush of Essence", "duration_seconds"), value("Vision Quest", "regen_pct"), 50.0,
               value("Tribal Rites", "cooldown_reduction_pct"), value("Grave Injustice", "heal_pct"),
               value("Grave Injustice", "cooldown_reduction_seconds"), value("Grave Injustice", "radius_yards"),
               float(tunables()["creeping_death_seconds"]["d3_value"]), float(tunables()["swampland_resistance_per_level"]["d3_value"]),
               float(tunables()["swampland_most_enemies"]["d3_value"]), value("Fierce Loyalty", "movement_speed_pct", "base"),
               value("Fierce Loyalty", "movement_speed_pct", "out_of_combat"),
               value("Confidence Ritual", "radius_yards"), float(tunables()["confidence_ritual_reach_yards"]["d3_value"]), 10.0]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 30, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the extra cost is the whole cost", (HEADER, "return cost > 0 && pct > 0 ? cost * pct / 100.0 : 0.0;", "return cost > 0 && pct > 0 ? cost : 0.0;")),
            ("a free skill costs extra", (HEADER, "return cost > 0 && pct > 0 ?", "return pct > 0 ?")),
            ("a skill off the list is on it", (HEADER, "return std::find(list.begin(), list.end(), name) != list.end();", "return true;")),
            ("a blow one short is fatal", (HEADER, "return health > 0 && damage >= health;", "return health > 0 && damage + 1 >= health;")),
            ("a blow just under is not fatal", (HEADER, "return health > 0 && damage >= health;", "return health > 0 && damage > health;")),
            ("no Life left is fatal", (HEADER, "return health > 0 && damage >= health;", "return damage >= health;")),
            ("the vessel never rests", (HEADER, "return !lastMs || nowMs >= *lastMs + cooldownMs;", "return true;")),
            ("the vessel never comes back", (HEADER, "return !lastMs || nowMs >= *lastMs + cooldownMs;", "return !lastMs;")),
            ("the window never closes", (HEADER, "return nowMs < startMs + lastsMs;", "return true;")),
            ("the window closes at once", (HEADER, "return nowMs < startMs + lastsMs;", "return false;")),
            ("an ended stream still runs", (HEADER, "return end > nowMs;", "return end >= nowMs;")),
            ("an ended stream is kept", (HEADER, "[nowMs](std::uint64_t end) { return end <= nowMs; }),", "[nowMs](std::uint64_t end) { return end < nowMs; }),")),
            ("a stream pays its whole gain a second", (HEADER, "return seconds > 0 ? gain / seconds : 0.0;", "return seconds > 0 ? gain : 0.0;")),
            ("the quest adds the whole regeneration", (HEADER, "return classRegenPerSecond > 0 && pct > 0 ? classRegenPerSecond * pct / 100.0 : 0.0;",
                                                       "return classRegenPerSecond > 0 && pct > 0 ? classRegenPerSecond : 0.0;")),
            ("a cooldown loses it all", (HEADER, "return std::uint32_t(leftMs * std::clamp(pct, 0.0, 100.0) / 100.0);", "return leftMs;")),
            ("a cooldown loses more than all", (HEADER, "std::clamp(pct, 0.0, 100.0)", "pct")),
            ("a cooldown loses nothing", (HEADER, "return std::uint32_t(leftMs * std::clamp(pct, 0.0, 100.0) / 100.0);", "return 0u;")),
            ("a cooldown goes below nothing", (HEADER, "return leftMs > cut ? leftMs - cut : 0u;", "return leftMs - cut;")),
            ("a second off is a millisecond", (HEADER, "std::uint32_t(std::max(0.0, seconds) * 1000.0 + 0.5)", "std::uint32_t(std::max(0.0, seconds) + 0.5)")),
            ("the share is the whole maximum", (HEADER, "return maximum > 0 && pct > 0 ? maximum * pct / 100.0 : 0.0;", "return maximum > 0 && pct > 0 ? maximum : 0.0;")),
            ("a debuff is shortened", (HEADER, "return on ? std::max(baseSeconds, passiveSeconds) : baseSeconds;", "return on ? passiveSeconds : baseSeconds;")),
            ("a debuff lasts without the passive", (HEADER, "return on ? std::max(baseSeconds, passiveSeconds) : baseSeconds;", "return std::max(baseSeconds, passiveSeconds);")),
            ("the radius is beyond its edge", (HEADER, "return distance <= radius + std::max(0.0, extra);", "return distance < radius + std::max(0.0, extra);")),
            ("nothing widens the radius", (HEADER, "return distance <= radius + std::max(0.0, extra);", "return distance <= radius;")),
            ("a negative widening narrows it", (HEADER, "return distance <= radius + std::max(0.0, extra);", "return distance <= radius + extra;")),
            ("the enemies are not counted", (HEADER, "return level * perLevel * std::min(enemies, most);", "return level * perLevel;")),
            ("no limit on the enemies counted", (HEADER, "return level * perLevel * std::min(enemies, most);", "return level * perLevel * enemies;")),
            ("the level is ignored", (HEADER, "return level * perLevel * std::min(enemies, most);", "return 70 * perLevel * std::min(enemies, most);")),
            ("Fierce Loyalty runs with no pet", (HEADER, "return !petOut ? 0.0 : petIdle ? outOfCombat : base;", "return petIdle ? outOfCombat : base;")),
            ("Fierce Loyalty ignores an idle pet", (HEADER, "return !petOut ? 0.0 : petIdle ? outOfCombat : base;", "return !petOut ? 0.0 : base;")),
            ("Fierce Loyalty is always the greater", (HEADER, "return !petOut ? 0.0 : petIdle ? outOfCombat : base;", "return !petOut ? 0.0 : outOfCombat;")),
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
    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("Zombie Handler", "pet_life_pct"), value("Zombie Handler", "pet_count")], [20, 1])
        self.assertEqual([value("Pierce the Veil", "damage_bonus_pct"), value("Pierce the Veil", "cost_increase_pct")], [20, 30])
        self.assertEqual([value("Spirit Vessel", "duration_seconds"), value("Spirit Vessel", "heal_pct"),
                          value("Spirit Vessel", "internal_cooldown_seconds")], [2, 50, 60])
        self.assertEqual([value("Fetish Sycophants", "proc_chance_pct"), value("Fetish Sycophants", "duration_seconds")], [15, 60])
        self.assertEqual([value("Rush of Essence", "gain_resource"), value("Rush of Essence", "duration_seconds")], [100, 10])
        self.assertEqual([value("Vision Quest", "regen_pct"), value("Vision Quest", "duration_seconds")], [40, 5])
        self.assertEqual([value("Fierce Loyalty", "movement_speed_pct", "base"), value("Fierce Loyalty", "movement_speed_pct", "out_of_combat"),
                          value("Fierce Loyalty", "pet_count")], [15, 30, 1])
        self.assertEqual([value("Grave Injustice", "heal_pct"), value("Grave Injustice", "cooldown_reduction_seconds"),
                          value("Grave Injustice", "radius_yards")], [1, 1, 20])
        self.assertEqual(value("Tribal Rites", "cooldown_reduction_pct"), 25)
        self.assertEqual([value("Swampland Attunement", "resistance_points"), value("Swampland Attunement", "radius_yards")], [120, 20])
        self.assertEqual([value("Midnight Feast", "damage_bonus_pct"), value("Midnight Feast", "pet_count")], [50, 1])
        self.assertEqual([value("Confidence Ritual", "damage_bonus_pct"), value("Confidence Ritual", "radius_yards")], [25, 20])

    def test_the_skills_the_tooltips_name_are_the_ones_the_code_lists(self):
        mana = code("dc_witch_doctor_mana_passives.cpp")
        rush = re.search(r"SpiritSpells = \{(.*?)\};", mana).group(1)
        quest = re.search(r"QuestSkills = \{(.*?)\};", mana).group(1)
        spirit = [part.strip() for part in text_of("Rush of Essence").split("Spirit spells are:")[1].split("Unlocked")[0].split("|") if part.strip()]
        self.assertEqual(re.findall(r'"([^"]+)"', rush), spirit)
        named = text_of("Vision Quest").split("with ")[1].split(",")
        named = [n.replace("or ", "").split(" Your")[0].strip() for n in named]
        self.assertEqual(re.findall(r'"([^"]+)"', quest), [n for n in named if n][:4])

    def test_tribal_rites_names_the_skills_its_tooltip_names(self):
        skills = code("dc_witch_doctor_skill_passives.cpp")
        listed = re.findall(r'"([^"]+)"', re.search(r"TribalSkills = \{(.*?)\};", skills).group(1))
        named = [part.strip() for part in text_of("Tribal Rites").split("following skills by {cooldown_reduction_pct}:")[1].split("Unlocked")[0].split("|") if part.strip()]
        self.assertEqual(listed, named)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source, power in (("rush_of_essence_max_streams", "100", "SF_2", "RushOfEssence"),
                                        ("fetish_sycophants_max", "15", "SF_4", "FetishSycophants")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn(f"Power/Witchdoctor_Passive_{power}.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower())

    def test_the_third_groups_tunables(self):
        rows = tunables()
        for name, d3, source, power in (("confidence_ritual_reach_yards", "2", "SF_2", "X1_WitchDoctor_Passive_ConfidenceRitual"),
                                        ("swampland_most_enemies", "25", "SF_2", "Witchdoctor_Passive_PhysicalAttunement"),
                                        ("swampland_check_seconds", "0.5", "SF_3", "Witchdoctor_Passive_PhysicalAttunement"),
                                        ("fierce_loyalty_check_seconds", "0.5", "SF_1", "Witchdoctor_Passive_FierceLoyalty"),
                                        ("fierce_loyalty_hold_seconds", "2", "SF_3", "Witchdoctor_Passive_FierceLoyalty"),
                                        ("creeping_death_seconds", "120", "SF_0", "Witchdoctor_Passive_CreepingDeath")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn(f"Power/{power}.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower())
        per = rows["swampland_resistance_per_level"]
        self.assertAlmostEqual(float(per["d3_value"]) * 70, value("Swampland Attunement", "resistance_points"), places=6)
        self.assertIn("12/7", per["notes"])

    def test_every_name_the_code_reads_exists(self):
        names = set()
        for name in ("dc_witch_doctor_damage_passives.cpp", "dc_witch_doctor_mana_passives.cpp", "dc_witch_doctor_survival_passives.cpp",
                     "dc_witch_doctor_pet_passives.cpp", "dc_witch_doctor_skill_passives.cpp"):
            text = (WD / name).read_text(encoding="utf-8")
            names |= set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text))
            for passive, token in re.findall(r'Num\(\s*"([A-Za-z\' ]+)",\s*"([a-z_]+)"', text):
                rows = {(r["skill"], r["token"]) for r in read(D3 / "witch_doctor_passive_values.csv")}
                self.assertIn((passive, token), rows, (passive, token))
        for name in names:
            self.assertIn(name, tunables(), name)

    def test_the_passives_read_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")

        def sf(power):
            return decode_pow.parse_power(decode_pow.extract(f"Power/Witchdoctor_Passive_{power}.pow"))["sf"]

        number = lambda table, n: float(str(table[n]).strip())  # noqa: E731
        handler = sf("ZombieHandler")
        self.assertAlmostEqual(number(handler, 0) * 100, value("Zombie Handler", "pet_life_pct"))
        veil = sf("PierceTheVeil")
        self.assertAlmostEqual(number(veil, 0) * 100, value("Pierce the Veil", "damage_bonus_pct"))
        self.assertAlmostEqual(number(veil, 1) * 100, value("Pierce the Veil", "cost_increase_pct"))
        vessel = sf("SpiritVessel")
        self.assertAlmostEqual(number(vessel, 1), value("Spirit Vessel", "duration_seconds"))
        self.assertAlmostEqual(number(vessel, 2) * 100, value("Spirit Vessel", "heal_pct"))
        self.assertAlmostEqual(number(vessel, 3), value("Spirit Vessel", "internal_cooldown_seconds"))
        fetish = sf("FetishSycophants")
        self.assertAlmostEqual(number(fetish, 0) * 100, value("Fetish Sycophants", "proc_chance_pct"))
        self.assertAlmostEqual(number(fetish, 1), value("Fetish Sycophants", "duration_seconds"))
        self.assertAlmostEqual(number(fetish, 4), float(tunables()["fetish_sycophants_max"]["d3_value"]))
        rush = sf("RushOfEssence")
        self.assertAlmostEqual(number(rush, 0), value("Rush of Essence", "gain_resource"))
        self.assertAlmostEqual(number(rush, 1), value("Rush of Essence", "duration_seconds"))
        self.assertAlmostEqual(number(rush, 2), float(tunables()["rush_of_essence_max_streams"]["d3_value"]))
        loyalty = sf("FierceLoyalty")
        self.assertAlmostEqual(number(loyalty, 4) * 100, value("Fierce Loyalty", "movement_speed_pct", "base"))
        self.assertAlmostEqual(number(loyalty, 2) * 100 + number(loyalty, 4) * 100, value("Fierce Loyalty", "movement_speed_pct", "out_of_combat"))
        self.assertAlmostEqual(number(loyalty, 1), float(tunables()["fierce_loyalty_check_seconds"]["d3_value"]))
        self.assertAlmostEqual(number(loyalty, 3), float(tunables()["fierce_loyalty_hold_seconds"]["d3_value"]))
        grave = sf("GraveInjustice")
        self.assertAlmostEqual(number(grave, 0), value("Grave Injustice", "radius_yards"))
        self.assertAlmostEqual(number(grave, 1) * 100, value("Grave Injustice", "heal_pct"))
        self.assertAlmostEqual(number(grave, 2), value("Grave Injustice", "cooldown_reduction_seconds"))
        tribal = sf("TribalRites")
        self.assertEqual(str(tribal[0]).replace(" ", ""), "(sLevel>0)?0.25:0")
        self.assertAlmostEqual(0.25 * 100, value("Tribal Rites", "cooldown_reduction_pct"))
        self.assertAlmostEqual(number(sf("CreepingDeath"), 0) / 1000.0, float(tunables()["creeping_death_seconds"]["d3_value"]))
        swamp = sf("PhysicalAttunement")
        self.assertAlmostEqual(number(swamp, 0), value("Swampland Attunement", "radius_yards"))
        self.assertEqual(str(swamp[1]).replace(" ", ""), "Effective_Level*12/7")
        self.assertAlmostEqual(70 * 12 / 7, value("Swampland Attunement", "resistance_points"))
        self.assertAlmostEqual(number(swamp, 2), float(tunables()["swampland_most_enemies"]["d3_value"]))
        self.assertAlmostEqual(number(swamp, 3), float(tunables()["swampland_check_seconds"]["d3_value"]))
        feast = sf("MidnightFeast")
        self.assertAlmostEqual(number(feast, 0) * 100, value("Midnight Feast", "damage_bonus_pct"))
        confidence = decode_pow.parse_power(decode_pow.extract("Power/X1_WitchDoctor_Passive_ConfidenceRitual.pow"))["sf"]
        self.assertAlmostEqual(number(confidence, 0) * 100, value("Confidence Ritual", "damage_bonus_pct"))
        self.assertAlmostEqual(number(confidence, 1), value("Confidence Ritual", "radius_yards"))
        self.assertAlmostEqual(number(confidence, 2), float(tunables()["confidence_ritual_reach_yards"]["d3_value"]))
        quest = sf("VisionQuest")
        self.assertAlmostEqual(number(quest, 4) * 100, value("Vision Quest", "regen_pct"))
        self.assertAlmostEqual(number(quest, 3), value("Vision Quest", "duration_seconds"))


# The one Reduce of the Witch Doctor on the Mitigate line: the passives', Big Bad Voodoo's, the dogs' and Spirit Vessel's reducers each
# applied once. A line written twice (a second Reduce, a merge that kept both) would reduce the damage twice.
REDUCE_LINE = "return Passive::Survival::Reduce(victim, ZombieDogs::Reduce(victim, BigBadVoodoo::Reduce(victim, Passive::Reduce(victim, damage))));"


def reduce_line_once(test, dispatch):
    test.assertEqual(dispatch.count(REDUCE_LINE), 1, "the dispatch's Reduce line is written exactly once")


class Wiring(unittest.TestCase):
    def test_a_reduce_line_written_twice_is_caught(self):
        dispatch = code("dc_witch_doctor.cpp")
        with self.assertRaises(AssertionError):
            reduce_line_once(self, dispatch.replace(REDUCE_LINE, REDUCE_LINE + " " + REDUCE_LINE))
        with self.assertRaises(AssertionError):
            reduce_line_once(self, dispatch.replace(REDUCE_LINE, ""))

    def test_the_dispatch_answers_the_seams_and_the_engine_calls_them(self):
        dispatch = code("dc_witch_doctor.cpp")
        for call in ("Passive::Damage::Multipliers(player, target, spellId, out);",
                     "Passive::Survival::Register();", "Passive::Damage::Cast(player, spellId);", "Passive::ManaOverTime::Cast(player, spellId);",
                     "Passive::ManaOverTime::Landed(player, target, spellId);"):
            self.assertEqual(dispatch.count(call), 1, call)
        reduce_line_once(self, dispatch)
        engine = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))
        self.assertEqual(engine.count("WitchDoctor::Multipliers(player, target, shell.spellId, hit.factors);"), 1)
        self.assertLess(engine.index("Necromancer::Multipliers(player, target, shell.spellId, hit.factors);"),
                        engine.index("WitchDoctor::Multipliers(player, target, shell.spellId, hit.factors);"))
        self.assertIn("result = Necromancer::Reduce(victim, result); result = WitchDoctor::Reduce(victim, result);", engine)
        self.assertIn("DemonHunter::RegisterScripts(); WitchDoctor::RegisterScripts();", engine)

    def test_pierce_the_veil_is_a_multiplier_and_a_cost(self):
        damage = code("dc_witch_doctor_damage_passives.cpp")
        self.assertIn('AddFactor(out, "Pierce the Veil", Num("Pierce the Veil", "damage_bonus_pct"));', damage)
        self.assertIn("if (!Shells::FindAbility(spellId)) return;", damage)
        self.assertIn('if (On(player, "Pierce the Veil")) AddFactor(out, "Pierce the Veil", Num("Pierce the Veil", "damage_bonus_pct"));', damage)
        self.assertIn('Rules::ExtraCost(double(info->ManaCost), Num("Pierce the Veil", "cost_increase_pct"))', damage)
        self.assertIn("info->PowerType != POWER_MANA", damage)
        self.assertIn("Resources::SpendUnits(player, Resources::Mana,", damage)

    def test_the_mana_passives_ride_the_cast_and_the_hit_on_the_sheets_regeneration(self):
        mana = code("dc_witch_doctor_mana_passives.cpp")
        self.assertIn("Stat::ManaRegen", mana)
        self.assertIn("Rules::Listed(SpiritSpells, row->skill)", mana)
        self.assertIn('On(player, "Rush of Essence")', mana)
        self.assertIn("Rules::Listed(QuestSkills, row->skill)", mana)
        self.assertIn('On(player, "Vision Quest")', mana)
        self.assertIn('ends.size() >= std::size_t(Tune("rush_of_essence_max_streams"))', mana)
        self.assertIn('running * Rules::PerSecond(Num("Rush of Essence", "gain_resource"), Num("Rush of Essence", "duration_seconds"))', mana)
        self.assertIn('Rules::RegenBonus(Resources::Mana.regenPerSecond, Num("Vision Quest", "regen_pct"))', mana)
        self.assertIn("QuestLapse(player)", mana)

    def test_the_survival_passives(self):
        survival = code("dc_witch_doctor_survival_passives.cpp")
        self.assertIn('Stats::AddContribution(guid, {Source::Passives, Stat::LifePercent, id, Num("Zombie Handler", "pet_life_pct"), Bucket::Flat});', survival)
        self.assertIn("if (vessel.last && Rules::Open(vessel.opened, now, lasts)) return 0.0;", survival)
        self.assertIn('!Rules::Fatal(damage, double(player->GetHealth())) || !Rules::Ready(vessel.last, now, Millis(Num("Spirit Vessel", "internal_cooldown_seconds")))', survival)
        self.assertIn('Heal(player, Id("Spirit Vessel"), double(player->GetMaxHealth()) * Num("Spirit Vessel", "heal_pct") / 100.0);', survival)
        self.assertIn("PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT", survival)

    def test_confidence_ritual_is_a_multiplier_by_distance(self):
        damage = code("dc_witch_doctor_damage_passives.cpp")
        self.assertIn('Rules::Near(player->GetExactDist(target), Num("Confidence Ritual", "radius_yards"), Tune("confidence_ritual_reach_yards"))', damage)
        self.assertIn('AddFactor(out, "Confidence Ritual", Num("Confidence Ritual", "damage_bonus_pct"));', damage)

    def test_the_third_groups_survival_passives(self):
        survival = code("dc_witch_doctor_survival_passives.cpp")
        self.assertIn('Rules::ResistPoints( player->GetLevel(), Tune("swampland_resistance_per_level"),', survival)
        self.assertIn('Tune("swampland_most_enemies")', survival)
        self.assertIn("Stat::SingleResistance", survival)
        for element in ("Physical", "Poison", "Fire", "Cold"):
            self.assertIn(f"Element::{element}", survival)
        self.assertIn('Num(passive, "radius_yards") + (sheet ? (*sheet)[Stat::GoldPickupRange] : 0.0)', survival)
        self.assertIn("PLAYERHOOK_ON_CREATURE_KILL", survival)
        self.assertIn("Heal(player, id, Rules::Share(double(player->GetMaxHealth()), pct));", survival)
        self.assertIn("Resources::Energize(player, Resources::Mana, id, Rules::Share(Resources::Max(player, Resources::Mana), pct));", survival)
        self.assertIn('Rules::CooledBy(left, Num("Grave Injustice", "cooldown_reduction_seconds"))', survival)
        self.assertIn("for (Classes::Slot const& slot : Classes::Bar(player))", survival)

    def test_the_skill_passives_and_the_piranhas_ask_creeping_death(self):
        skills = code("dc_witch_doctor_skill_passives.cpp")
        self.assertIn('Rules::Lasting(On(player, "Creeping Death"), baseSeconds, Tune("creeping_death_seconds"))', skills)
        self.assertIn("PLAYERHOOK_ON_SPELL_CAST", skills)
        self.assertIn('Rules::CooldownCut(left, Num("Tribal Rites", "cooldown_reduction_pct"))', skills)
        self.assertIn("Combat::SendSkillCooldown(player, info->Id, left - cut);", skills)
        piranhas = code("dc_witch_doctor_piranhas.cpp")
        self.assertIn('Passive::Skills::Lasting(owner, Tune("piranhas_debuff_seconds"))', piranhas)
        dispatch = code("dc_witch_doctor.cpp")
        self.assertIn("Passive::Pets::Register(); Passive::Skills::Register();", dispatch)

    def test_fierce_loyalty_looks_at_the_minions_the_pets_piece_keeps(self):
        pets = code("dc_witch_doctor_pet_passives.cpp")
        self.assertIn('for (std::string_view group : WitchDoctor::Pets::PetGroups)', pets)
        self.assertIn("Minions::Standing(player, group)", pets)
        self.assertIn("Rules::FierceSpeed(", pets)
        self.assertIn('Num("Fierce Loyalty", "movement_speed_pct", "base"), Num("Fierce Loyalty", "movement_speed_pct", "out_of_combat")', pets)
        self.assertIn("!pets.empty(), std::any_of(pets.begin(), pets.end(), [](Creature* pet) { return !pet->IsInCombat(); })", pets)
        self.assertIn("Stat::MovementSpeed, id, wanted, Bucket::Uncapped", pets)


if __name__ == "__main__":
    unittest.main()
