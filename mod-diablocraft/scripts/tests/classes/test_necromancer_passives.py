"""The Necromancer's passives, all twenty (src/classes/necromancer/dc_necromancer_passives*.{h,cpp}): Life from Death, Fueled by Death,
Stand Alone, Bone Prison, Swift Harvesting, Commander of the Risen Dead; Extended Servitude, Rigor Mortis, Overwhelming Essence, Dark Reaping,
Spreading Malediction, Eternal Torment, Final Service; Grisly Tribute, Draw Life, Serration, Aberrant Animator, Blood for Blood, Blood Is
Power, Rathma's Shield.

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_passives/harness.cpp compiles the real dc_necromancer_passives_math.h with the
    sheet's numbers and skill names: Stand Alone takes its share off for each minion and never goes below nothing; Bone Prison and Swift
    Harvesting name exactly the skills of their tooltips; a roll under a chance procs; Swift Harvesting joins the speed bonuses already in and
    keeps to the cap; Commander takes the share off the cooldown (its cost cut is the cost cut piece's); Life from Death spawns no more than its
    cap in a window. Planted mutations must each turn it red.
  * **The numbers.** The sheet rows (necromancer_passive_values.csv) agree with the power files (decode_pow.py power
    P6_Necro_Passive_StandAlone: SF_0 1.0, SF_1 0.1, SF_2 0.5; ..._BonePrison: SF_0 3, SF_1 0.30; ..._CommanderoftheDead: SF_0 0.3, SF_1 0.3;
    ..._HealthGlobesFromCorpseConsumption: SF_0 0.2, SF_1 10, SF_2 5); Life from Death's three numbers and Stand Alone's tick are tunables.
  * **It is wired.** The dispatch answers Landed, AttackSpeed and RegisterScripts; the combat engine asks the Necromancer for the speed of a skill.

What it does not prove: anything on a running server. Life from Death's globe is not built (the health globes are their own bead).

    python mod-diablocraft/scripts/tests/classes/test_necromancer_passives.py
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

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
FOLDER = MODULE / "src/classes/necromancer"
MATH = "src/classes/necromancer/dc_necromancer_passives_math.h"
HARNESS = MODULE / "tests/necromancer_passives/harness.cpp"
CODE = FOLDER / "dc_necromancer_passives.cpp"
PASSIVES = ("Life from Death", "Fueled by Death", "Stand Alone", "Bone Prison", "Swift Harvesting", "Commander of the Risen Dead",
            "Extended Servitude", "Rigor Mortis", "Overwhelming Essence", "Dark Reaping", "Spreading Malediction", "Eternal Torment",
            "Final Service", "Grisly Tribute", "Draw Life", "Serration", "Aberrant Animator", "Blood for Blood", "Blood Is Power",
            "Rathma's Shield")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(passive, token, qualifier=""):
    rows = [r for r in read(D3 / "necromancer_passive_values.csv")
            if (r["skill"], r["token"], r["qualifier"]) == (passive, token, qualifier)]
    assert len(rows) == 1, (passive, token, qualifier, len(rows))
    return float(rows[0]["value"])


def text(passive):
    return next(r["full_text"] for r in read(D3 / "necromancer_passives.csv") if r["passive_name"] == passive)


def skills_named(passive, marker):
    """The skills a tooltip names after `marker` ('Bone Spear, Bone Spikes, and Bone Spirit have ...')."""
    sentence = re.search(marker + r"([^.]*?) (?:have|by)", text(passive))
    return re.split(r", (?:and )?|, | and ", sentence[1].strip())


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}


def tune(name):
    return float(tunables()[name]["d3_value"])


def squeeze(text_):
    return re.sub(r"\s+", " ", text_)


def scratch_tree(mutate=None):
    files = {MATH[len("src/"):]: (MODULE / MATH).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        key = MATH[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {MATH}")
        files[key] = files[key].replace(old, new)
    return files


def prison_skills():
    return [s.strip() for s in re.split(r",| and ", re.search(r"^(.*?) have", text("Bone Prison"))[1]) if s.strip()]


def swift_skills():
    return [s.strip() for s in re.split(r",| and ", re.search(r"attack speed of (.*?) by", text("Swift Harvesting"))[1]) if s.strip()]


def servants():
    return [s.strip() for s in re.split(r",| and ", re.search(r"duration of your (.*?) minions", text("Extended Servitude"))[1]) if s.strip()]


def curse_skills():
    return [r["skill_name"] for r in read(D3 / "necromancer_skills.csv") if r["category"] == "Curses"]


def scythe_types():
    return sorted({r["type"] for r in read(D3 / "base_items.csv") if r["usable_by"] == "necromancer" and "Scythe" in r["type"]})


def serration_skills():
    return [s.strip() for s in re.split(r",| and ", re.search(r"^(.*?) deal", text("Serration"))[1]) if s.strip()]


def rathma_skills():
    return [s.strip() for s in re.split(r",| or ", re.search(r"after using (.*?)\.", text("Rathma's Shield"))[1]) if s.strip()]


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Stand Alone", "armor_pct", "base"), value("Stand Alone", "armor_pct", "per_minion"),
               value("Bone Prison", "proc_chance_pct"), value("Swift Harvesting", "attack_speed_pct"),
               value("Commander of the Risen Dead", "cooldown_reduction_pct"), tune("life_from_death_chance_pct"),
               tune("life_from_death_window_seconds"), tune("life_from_death_max_globes")]
    numbers += [value("Extended Servitude", "duration_bonus_pct"), value("Spreading Malediction", "damage_bonus_pct"),
                tune("eternal_torment_forever_seconds"), value("Dark Reaping", "gain_pct"), value("Final Service", "duration_seconds"),
                value("Final Service", "heal_pct"), value("Final Service", "internal_cooldown_seconds")]
    first, second = [str(n) for n in numbers[:8]], [str(n) for n in numbers[8:]]
    third = [value("Grisly Tribute", "life_per_hit_share_pct"), value("Draw Life", "life_regen_pct"), value("Serration", "damage_bonus_pct"),
             value("Serration", "distance_yards"), value("Serration", "max_bonus_pct"), value("Aberrant Animator", "thorns_share_pct"),
             value("Blood for Blood", "max_stacks_count"), value("Blood Is Power", "life_lost_threshold_pct"),
             value("Rathma's Shield", "duration_seconds"), value("Rathma's Shield", "internal_cooldown_seconds")]
    return harness_env.run([str(binary)] + first + prison_skills() + swift_skills() + second + servants() + curse_skills() + scythe_types() +
                           [str(n) for n in third] + serration_skills() + rathma_skills(), capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 80, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a minion takes nothing off", ("basePct - perMinionPct * minions", "basePct")),
            ("a minion takes double", ("basePct - perMinionPct * minions", "basePct - 2 * perMinionPct * minions")),
            ("the armor goes negative", ("return std::max(0.0, basePct - perMinionPct * minions);", "return basePct - perMinionPct * minions;")),
            ("Bone Prison traps another skill", ('skill == "Bone Spear" || skill == "Bone Spikes" || skill == "Bone Spirit"',
                                                 'skill == "Bone Spear" || skill == "Bone Spikes" || skill == "Grim Scythe"')),
            ("Swift Harvesting quickens another skill", ('skill == "Bone Spikes" || skill == "Siphon Blood" || skill == "Grim Scythe"',
                                                         'skill == "Bone Spikes" || skill == "Siphon Blood" || skill == "Bone Spear"')),
            ("the roll equal to the chance procs", ("return roll < chancePct;", "return roll <= chancePct;")),
            ("the speed bonus multiplies", ("aps * (1.0 + (iasPct + bonusPct) / 100.0) / (1.0 + iasPct / 100.0)",
                                            "aps * (1.0 + bonusPct / 100.0) * (1.0 + iasPct / 100.0)")),
            ("the speed cap is ignored", ("return std::max(aps, std::min(cap, sped));", "return std::max(aps, sped);")),
            ("a speed over the cap is cut", ("return std::max(aps, std::min(cap, sped));", "return std::min(cap, sped);")),
            ("the whole cooldown goes", ("leftMs * std::clamp(pct, 0.0, 100.0) / 100.0", "leftMs")),
            ("more than the cooldown goes", ("std::clamp(pct, 0.0, 100.0)", "std::max(pct, 0.0)")),
            ("the window never ends", ("now >= start + windowMs", "false")),
            ("the window ends early", ("now >= start + windowMs", "now + 1 >= start + windowMs")),
            ("the cap is one more", ("if (spawned >= max)", "if (spawned > max)")),
            ("the cap is ignored", ("if (spawned >= max)\n                return false;", "if (false)\n                return false;")),
            ("Extended Servitude lengthens another minion", ('skill == "Skeletal Mage" || skill == "Revive"', 'skill == "Skeletal Mage" || skill == "Command Golem"')),
            ("a minion lasts only the share", ("return 1.0 + std::max(0.0, bonusPct) / 100.0;", "return std::max(0.0, bonusPct) / 100.0;")),
            ("a negative share shortens a minion", ("return 1.0 + std::max(0.0, bonusPct) / 100.0;", "return 1.0 + bonusPct / 100.0;")),
            ("Rigor Mortis is any record", ("return (schoolMask & 32u) != 0;", "return schoolMask != 0;")),
            ("Rigor Mortis is the wrong school", ("return (schoolMask & 32u) != 0;", "return (schoolMask & 64u) != 0;")),
            ("the bonus ignores the enemies", ("std::max(0.0, perEnemyPct) * cursed", "std::max(0.0, perEnemyPct)")),
            ("a negative share gives a penalty", ("std::max(0.0, perEnemyPct) * cursed", "perEnemyPct * cursed")),
            ("the curse ends with the passive on", ("return eternal && seconds > 0 ? std::max(seconds, forever) : seconds;", "return seconds;")),
            ("the curse lasts forever with the passive off", ("return eternal && seconds > 0 ? std::max(seconds, forever) : seconds;", "return seconds > 0 ? std::max(seconds, forever) : seconds;")),
            ("a curse of none lasts forever", ("return eternal && seconds > 0 ? std::max(seconds, forever) : seconds;", "return eternal ? std::max(seconds, forever) : seconds;")),
            ("a longer curse is cut", ("std::max(seconds, forever)", "forever")),
            ("Eternal Torment cuts another skill", ('{"Decrepify", "Leech", "Frailty"}', '{"Decrepify", "Leech", "Bone Spear"}')),
            ("only the one-handed scythe counts", ('type == "Scythe" || type == "Two-Handed Scythe"', 'type == "Scythe"')),
            ("any weapon counts as a scythe", ('type == "Scythe" || type == "Two-Handed Scythe"', 'type.size() > 0')),
            ("Dark Reaping gains the whole maximum", ("maximum * gainPct / 100.0 : 0.0", "maximum : 0.0")),
            ("a negative share drains", ("return maximum > 0 && gainPct > 0 ?", "return maximum > 0 ?")),
            ("a blow short of the Life saves", ("damage < health)", "damage < health / 2)")),
            ("the save works in the wait", ("if (now < readyAt ||", "if (")),
            ("the window never ends", ("return now < until;\n        }\n\n        // A blow", "return until > 0;\n        }\n\n        // A blow")),
            ("the window is one tick short", ("return now < until;\n        }\n\n        // A blow", "return now + 1 < until;\n        }\n\n        // A blow")),
            ("the wait starts when the window ends", ("damage < health)\n                return false;\n            until = now + durationMs;\n            readyAt = now + cooldownMs;", "damage < health)\n                return false;\n            until = now + durationMs;\n            readyAt = until + cooldownMs;")),
            ("the heal ignores the minions", ("maxLife * healPct / 100.0 * minions", "maxLife * healPct / 100.0")),
            ("the heal is the whole Life", ("maxLife * healPct / 100.0 * minions", "maxLife * minions")),
            ("the tribute is the whole Life on Hit", ("lifePerHit * sharePct / 100.0 : 0.0", "lifePerHit : 0.0")),
            ("a negative share drains with the tribute", ("return lifePerHit > 0 && sharePct > 0 ?", "return lifePerHit > 0 ?")),
            ("Draw Life ignores the enemies", ("std::max(0.0, perEnemyPct) * enemies;", "std::max(0.0, perEnemyPct);")),
            ("Draw Life drains for a negative share", ("std::max(0.0, perEnemyPct) * enemies;", "perEnemyPct * enemies;")),
            ("Serration counts a part of a step", ("std::floor(yards / stepYards) * perStepPct", "(yards / stepYards) * perStepPct")),
            ("Serration has no maximum", ("std::min(std::max(0.0, maxPct), std::floor(yards / stepYards) * perStepPct)", "std::floor(yards / stepYards) * perStepPct")),
            ("Serration counts the step twice", ("std::floor(yards / stepYards) * perStepPct", "std::floor(yards / stepYards + 1) * perStepPct")),
            ("Serration works a step short of nothing", ("if (yards <= 0 || perStepPct <= 0 || stepYards <= 0)", "if (yards <= 0 || perStepPct <= 0)")),
            ("Serration lengthens another skill", ('skill == "Bone Spikes" || skill == "Bone Spear" || skill == "Bone Spirit"', 'skill == "Bone Spikes" || skill == "Bone Spear" || skill == "Death Nova"')),
            ("the minion has all the Thorns", ("thorns * sharePct / 100.0 : 0.0", "thorns : 0.0")),
            ("a negative share gives Thorns", ("return thorns > 0 && sharePct > 0 ?", "return thorns > 0 ?")),
            ("the stacks have no most", ("stacks = std::min(stacks + 1, max);", "stacks = stacks + 1;")),
            ("a stack pays nothing", ("--stacks;\n            return true;", "return true;")),
            ("a stack is not spent without one", ("if (!stacks)\n                return false;", "if (false)\n                return false;")),
            ("a threshold is any loss", ("while (lost >= threshold)", "while (lost > 0)")),
            ("the carry is lost", ("lost -= threshold;", "lost = 0;")),
            ("the threshold is half", ("double const threshold = maxLife * thresholdPct / 100.0;", "double const threshold = maxLife * thresholdPct / 200.0;")),
            ("a gain counts", ("if (amount <= 0 || threshold <= 0)", "if (threshold <= 0)")),
            ("Rathma's Shield opens for another skill", ('skill == "Land of the Dead" || skill == "Army of the Dead" || skill == "Simulacrum"',
                                                         'skill == "Land of the Dead" || skill == "Army of the Dead" || skill == "Blood Rush"')),
            ("the shield has no wait", ("if (now < readyAt)\n                return false;\n            until = now + durationMs;\n            readyAt = now + cooldownMs;",
                                        "until = now + durationMs;\n            readyAt = now + cooldownMs;")),
            ("the shield never ends", ("return now < until;\n        }\n\n        // A skill is used", "return until > 0;\n        }\n\n        // A skill is used")),
            ("the shield stays closed in no wait", ("if (now < readyAt)\n                return false;\n            until = now + durationMs;", "if (now <= readyAt)\n                return false;\n            until = now + durationMs;")),
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
    def test_the_sheet_numbers_agree_with_the_power_files(self):
        self.assertEqual((value("Stand Alone", "armor_pct", "base"), value("Stand Alone", "armor_pct", "per_minion")), (100, 10))  # SF_0, SF_1
        self.assertEqual((value("Bone Prison", "proc_chance_pct"), value("Bone Prison", "duration_seconds")), (30, 3))  # SF_1, SF_0
        self.assertEqual(value("Commander of the Risen Dead", "cooldown_reduction_pct"), 30)  # SF_0 and SF_1
        self.assertEqual([value("Fueled by Death", t) for t in ("movement_speed_pct", "duration_seconds", "max_stacks_count")], [3, 5, 10])
        self.assertEqual(value("Swift Harvesting", "attack_speed_pct"), 15)

    def test_the_second_seven_sheet_numbers_agree_with_the_power_files(self):
        self.assertEqual(value("Extended Servitude", "duration_bonus_pct"), 25)
        self.assertEqual((value("Rigor Mortis", "slow_pct"), value("Rigor Mortis", "attack_speed_pct", "enemy"), value("Rigor Mortis", "duration_seconds")),
                         (30, 30, 5))  # SF_0 0.3, SF_2 0.3, SF_1 5
        self.assertEqual(value("Overwhelming Essence", "max_pool_resource"), 40)  # SF_0
        self.assertEqual(value("Dark Reaping", "gain_pct"), 2)  # SF_0 0.02
        self.assertEqual(value("Spreading Malediction", "damage_bonus_pct"), 1)
        self.assertEqual(value("Eternal Torment", "cost_reduction_pct"), 50)  # SF_0 0.5
        self.assertEqual([value("Final Service", t) for t in ("duration_seconds", "heal_pct", "internal_cooldown_seconds")], [4, 10, 60])

    def test_the_last_seven_sheet_numbers_agree_with_the_power_files(self):
        self.assertEqual(value("Grisly Tribute", "life_per_hit_share_pct"), 10)  # SF_0 0.1
        self.assertEqual([value("Serration", t) for t in ("damage_bonus_pct", "distance_yards", "max_bonus_pct")], [1, 1.5, 20])  # SF_0, SF_1, SF_2
        self.assertEqual(value("Aberrant Animator", "thorns_share_pct"), 200)  # SF_0 2
        self.assertEqual((value("Blood Is Power", "life_lost_threshold_pct"), value("Blood Is Power", "cooldown_reduction_pct")), (100, 20))  # SF_0, SF_1
        self.assertEqual(value("Rathma's Shield", "duration_seconds"), 4)  # SF_0
        self.assertEqual((value("Draw Life", "life_regen_pct"), value("Draw Life", "radius_yards"), value("Blood for Blood", "max_stacks_count")), (10, 20, 10))

    def test_the_last_seven_skills_the_rules_name_are_the_tooltips(self):
        self.assertEqual(serration_skills(), ["Bone Spikes", "Bone Spear", "Bone Spirit"])
        self.assertEqual(rathma_skills(), ["Land of the Dead", "Army of the Dead", "Simulacrum"])

    def test_the_skills_and_types_the_rules_name_are_the_sheets(self):
        self.assertEqual(servants(), ["Skeletal Mage", "Revive"])
        self.assertEqual(curse_skills(), ["Decrepify", "Leech", "Frailty"])
        self.assertEqual(scythe_types(), ["Scythe", "Two-Handed Scythe"])

    def test_the_skills_the_rules_name_are_the_tooltips(self):
        self.assertEqual(prison_skills(), ["Bone Spear", "Bone Spikes", "Bone Spirit"])
        self.assertEqual(swift_skills(), ["Bone Spikes", "Siphon Blood", "Grim Scythe"])
        header = (MODULE / MATH).read_text(encoding="utf-8")
        for fn, skills in (("BonePrisonSkill", prison_skills()), ("SwiftHarvestingSkill", swift_skills())):
            body = re.search(fn + r"\(std::string_view skill\)\s*\{\s*return (.*?);", header, re.S)[1]
            self.assertEqual(sorted(re.findall(r'"([^"]+)"', body)), sorted(skills), fn)

    def test_every_name_the_code_reads_exists(self):
        sheet = {(r["skill"], r["token"], r["qualifier"]) for r in read(D3 / "necromancer_passive_values.csv")}
        code = CODE.read_text(encoding="utf-8")
        used = set(re.findall(r'Num\("([^"]+)", "([a-z_]+)"(?:, "([a-z_]+)")?\)', code))
        for passive, token, qualifier in used:
            with self.subTest(passive=passive, token=token):
                self.assertIn((passive, token, qualifier), sheet)
                self.assertIn(passive, PASSIVES)
        mapped = {(r["skill"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")}
        for key in used:
            with self.subTest(mapped=key):
                self.assertIn(key, mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"eternal_torment_forever_seconds": ("86400", "EternalTorment"),  # the stand-in for forever
               "life_from_death_chance_pct": ("20", "HealthGlobesFromCorpseConsumption"),  # SF_0 0.2
               "life_from_death_max_globes": ("10", "HealthGlobesFromCorpseConsumption"),  # SF_1
               "life_from_death_window_seconds": ("5", "HealthGlobesFromCorpseConsumption"),  # SF_2
               "stand_alone_tick_seconds": ("0.5", "StandAlone")}  # SF_2

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, (number, power) in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                self.assertIn("decode_pow.py power P6_Necro_Passive_" + power, rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', CODE.read_text(encoding="utf-8"))), set(self.NUMBERS))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))
        self.combat = squeeze((MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("Passive::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("return Passive::AttackSpeed(player, spellId, base);", self.dispatch)
        self.assertIn("Passive::Register();", self.dispatch)

    def test_the_engine_asks_the_necromancer_for_the_speed_of_a_skill(self):
        self.assertIn("Necromancer::AttackSpeed(player, spellId, Crusader::AttackSpeed(", self.combat)
        self.assertEqual(self.combat.count("Necromancer::AttackSpeed(player, spellId, Crusader::AttackSpeed("), 2)

    def test_a_corpse_consumed_gives_speed_and_rolls_for_a_globe(self):
        self.assertIn("Corpses::OnConsumed(Consumed);", self.code)
        self.assertIn('Buffs::Stack(player, Id("Fueled by Death"), Stat::MovementSpeed, Bucket::Flat,', self.code)
        self.assertIn('unsigned(taken.size()));', self.code)
        self.assertIn('Procs(frand(0.0f, 100.0f), Tune("life_from_death_chance_pct"))', self.code)
        self.assertIn(".Allow(", self.code)

    def test_stand_alone_follows_the_minions(self):
        self.assertIn('Num("Stand Alone", "armor_pct", "base"), Num("Stand Alone", "armor_pct", "per_minion"), Minions::Count(player))', self.code)
        self.assertIn('Buffs::Set(player, Id("Stand Alone"), Stat::Armor, Bucket::Percent, pct);', self.code)

    def test_bone_prison_stuns_with_the_stun_powers(self):
        self.assertIn('Stun(player, target, Num("Bone Prison", "duration_seconds") * ItemPowers::StunFactor(player));', self.code)

    def test_swift_harvesting_joins_the_speed_bonuses_and_keeps_the_cap(self):
        self.assertIn('SwiftHarvestingAps(base, (*sheet)[Stat::AttackSpeed], Num("Swift Harvesting", "attack_speed_pct"),', self.code)
        self.assertIn('DC::NumericData::Rule("attack_speed_cap")', self.code)

    def test_extended_servitude_lengthens_the_mages_and_the_revived(self):
        pets = squeeze((FOLDER / "dc_necromancer_pets.cpp").read_text(encoding="utf-8"))
        self.assertIn("Passive::DurationFactor(owner, MageSkill)", pets)
        self.assertIn('Numbers::Num(record, "duration_seconds") * Passive::DurationFactor(owner, ReviveSkill)', pets)
        self.assertIn('ServitudeSkill(skill) && On(player, "Extended Servitude")', self.code)

    def test_rigor_mortis_slows_and_wearies_on_a_poison_hit(self):
        self.assertIn("PoisonMask(info->GetSchoolMask()) && On(player, \"Rigor Mortis\")", self.code)
        self.assertIn('Slow(player, target, Num("Rigor Mortis", "slow_pct"), Num("Rigor Mortis", "duration_seconds"));', self.code)
        self.assertIn('Weary(player, target, Num("Rigor Mortis", "attack_speed_pct", "enemy"), Num("Rigor Mortis", "duration_seconds"));', self.code)

    def test_overwhelming_essence_is_on_the_sheet_while_the_passive_is(self):
        self.assertIn('Stats::AddContribution(guid, {Source::Passives, Stat::MaxFury, id, Num("Overwhelming Essence", "max_pool_resource"), Bucket::Flat});', self.code)
        self.assertIn('Stats::RemoveContribution(guid, Source::Passives, Stat::MaxFury, id);', self.code)
        self.assertIn("Maximum(player);", self.code)

    def test_dark_reaping_gives_a_share_of_the_essence_and_the_life_for_a_kill_with_a_scythe(self):
        self.assertIn("if (!On(killer, \"Dark Reaping\") || !UsesScythe(killer)) return;", self.code)
        self.assertIn('Resources::Energize(killer, Essence, Id("Dark Reaping"), ReapGain(Resources::Max(killer, Essence), pct), false);', self.code)
        self.assertIn('Heal(killer, Id("Dark Reaping"), ReapGain(killer->GetMaxHealth(), pct));', self.code)
        self.assertIn('WorldDatabase.Query("SELECT entry,type FROM dc_base_item")', self.code)
        self.assertIn("EQUIPMENT_SLOT_MAINHAND", self.code)

    def test_spreading_malediction_rides_the_hit_with_the_enemies_cursed(self):
        self.assertIn('MaledictionPct(Num("Spreading Malediction", "damage_bonus_pct"), Curses::Cursed(player))', self.code)
        self.assertIn("Passive::Multipliers(player, target, spellId, out);", self.dispatch)

    def test_eternal_torment_cuts_the_cost_and_the_curses_last_forever(self):
        self.assertIn('for (std::string_view curse : CurseSkills) CostCut::Stand(player, curse, Id("Eternal Torment"), torment ? Num("Eternal Torment", "cost_reduction_pct") : 0.0);', self.code)
        self.assertIn('return CurseSeconds(On(player, "Eternal Torment"), seconds, Tune("eternal_torment_forever_seconds"));', self.code)
        for name in ("decrepify", "leech", "frailty"):
            curse = squeeze((FOLDER / f"dc_necromancer_{name}.cpp").read_text(encoding="utf-8"))
            self.assertIn("Passive::CurseSeconds(", curse, name)

    def test_final_service_sustains_on_a_lethal_blow_and_heals_for_the_minions(self):
        self.assertIn("return Simulacrum::Reduce(victim, Passive::Reduce(victim, BoneArmor::Reduce(victim, CorpseRevive::Reduce(victim, damage))));", self.dispatch)
        self.assertIn("if (found != sustains.end() && found->second.Active(now)) return 0.0;", self.code)
        self.assertIn('Heal(player, id, ServiceHeal(player->GetMaxHealth(), Numbers::Num(id, "heal_pct"), Minions::Count(player)));', self.code)

    def test_grisly_tribute_heals_for_a_share_of_the_life_on_hit_when_a_minion_strikes(self):
        self.assertIn("Minions::OnStruck(", self.code)
        self.assertIn('TributeHeal((*sheet)[Stat::LifePerHit], Num("Grisly Tribute", "life_per_hit_share_pct"))', self.code)
        minions = squeeze((MODULE / "src/combat/dc_minions.cpp").read_text(encoding="utf-8"))
        self.assertEqual(minions.count("Struck(player, target);"), 1)
        self.assertIn("Struck(player, enemy);", minions)

    def test_draw_life_follows_the_enemies_around(self):
        self.assertIn('Combat::Enemies(player, id, player->GetPosition(), Num("Draw Life", "radius_yards"))', self.code)
        self.assertIn("Buffs::Set(player, id, Stat::LifeRegen, Bucket::Percent, pct);", self.code)
        self.assertIn("DrawLife(player);", self.code)

    def test_serration_reads_the_distance_to_the_enemy_hit(self):
        self.assertIn("player->GetExactDist(target), Num(\"Serration\", \"damage_bonus_pct\"),", self.code)
        self.assertIn('Num("Serration", "distance_yards"), Num("Serration", "max_bonus_pct")', self.code)
        self.assertIn("Necromancer::Multipliers(player, target, shell.spellId, hit.factors);", self.combat)
        self.assertIn("Passive::Multipliers(player, target, spellId, out);", self.dispatch)

    def test_aberrant_animator_returns_a_share_of_the_thorns_when_a_minion_is_struck(self):
        self.assertIn('minion->GetScriptName() != "dc_minion"', self.code)
        self.assertIn('MinionThorns((*sheet)[Stat::Thorns], Num("Aberrant Animator", "thorns_share_pct"))', self.code)
        self.assertIn("Stats::ThornsHit(owner, attacker, thorns);", self.code)

    def test_blood_for_blood_pays_a_life_cost_with_a_stack(self):
        self.assertIn("freeCosts[player->GetGUID().GetRawValue()].Gain(unsigned(Num(\"Blood for Blood\", \"max_stacks_count\")));", self.code)
        effects = squeeze((FOLDER / "dc_necromancer_effects.cpp").read_text(encoding="utf-8"))
        self.assertIn("if (Passive::LifeLocked(player) || Passive::WaivesLifeCost(player)) return;", effects)
        self.assertIn("Passive::LifeLost(player, cost);", effects)

    def test_blood_is_power_shortens_each_cooling_ability_once_per_use(self):
        self.assertIn("lostLife[player->GetGUID().GetRawValue()].Add(amount, player->GetMaxHealth(),", self.code)
        self.assertIn("if (!shortened[guid].insert(slot.spellId).second) continue;", self.code)
        self.assertIn("found->second.erase(info->Id);", self.code)
        self.assertIn("Combat::SendSkillCooldown(player, slot.spellId, left - cut);", self.code)
        self.assertIn("LifeLost(player, std::min(taken, double(player->GetHealth())));", self.code)

    def test_rathmas_shield_opens_before_the_cost_and_stops_every_loss_of_life(self):
        self.assertIn("Passive::Casting(player, spellId);", self.dispatch)
        self.assertLess(self.dispatch.index("Passive::Casting(player, spellId);"), self.dispatch.index("BoneSpear::Casting(player, spellId);"))
        self.assertIn("if (LifeLocked(player)) return 0.0;", self.code)
        self.assertIn("wards[player->GetGUID().GetRawValue()].Open(Now(),", self.code)

    def test_commander_cuts_the_golems_cooldown(self):
        self.assertIn('if (row->skill == std::string_view("Command Golem"))', self.code)
        self.assertIn("Combat::SendSkillCooldown(player, info->Id, left - cut);", self.code)

    COMMANDER = 'CostCut::Stand(player, "Command Skeletons", Id("Commander of the Risen Dead"), commander ? Num("Commander of the Risen Dead", "cooldown_reduction_pct") : 0.0);'
    TORMENT = 'CostCut::Stand(player, curse, Id("Eternal Torment"), torment ? Num("Eternal Torment", "cost_reduction_pct") : 0.0);'

    @classmethod
    def cut_failures(cls, code):
        """What is wrong with the two Essence cuts in `code` (the squeezed passives file): they stand through the cost cut piece, only a change moves them, the
        update keeps them in step and nothing is paid back."""
        wrong = []
        for why, ok in (
                ("Commander cuts Command Skeletons by its own number", cls.COMMANDER in code),
                ("Eternal Torment cuts the curses by its own number", cls.TORMENT in code and "for (std::string_view curse : CurseSkills)" in code),
                ("only a change moves a cut", "changedCommander = held.first != commander; changedTorment = held.second != torment;" in code
                 and "if (changedCommander) CostCut::Stand" in code and "if (changedTorment) for (std::string_view curse" in code),
                ("the update keeps the cuts in step", "Maximum(player); CostCuts(player);" in code),
                ("a player's state goes at logout", "cutting.erase(player->GetGUID().GetRawValue());" in code),
                ("nothing is paid back", not any(word in code for word in ("CostBack", "PaidBack", "Energize(player, Essence, info->Id")))):
            if not ok:
                wrong.append(why)
        return wrong

    def test_the_essence_cuts_are_real_cuts_in_place_before_the_cast_and_nothing_is_paid_back(self):
        self.assertEqual([], self.cut_failures(self.code))
        self.assertIn('#include "../../combat/dc_cost_cut.h"', (FOLDER / "dc_necromancer_passives.cpp").read_text(encoding="utf-8"))
        for skill in ("Command Skeletons", "Decrepify", "Leech", "Frailty"):
            self.assertIn(skill, spells.CLASS_COST_CUT_SKILLS)       # each has the hidden cost aura the cut lowers

    def test_the_cuts_wiring_fails_its_mutants(self):
        mutants = {
            "commander_cuts_nothing": (self.COMMANDER, ""),
            "commander_cuts_by_the_wrong_number": ('"cooldown_reduction_pct") : 0.0);', '"cooldown_reduction_pct") : 100.0);'),
            "torment_cuts_nothing": (self.TORMENT, ""),
            "torment_cuts_one_curse": ("for (std::string_view curse : CurseSkills)", "for (std::string_view curse : {CurseSkills[0]})"),
            "a_cut_never_moves": ("if (changedCommander) CostCut::Stand", "if (false) CostCut::Stand"),
            "the_update_never_looks": ("Maximum(player); CostCuts(player);", "Maximum(player);"),
            "the_state_stays": ("cutting.erase(player->GetGUID().GetRawValue());", ""),
            "paid_back_again": ("CostCut::Stand(player, curse,", "Resources::Energize(player, Essence, info->Id, 1.0); CostCut::Stand(player, curse,"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, self.code.count(old), name + " does not apply")
                self.assertNotEqual([], self.cut_failures(self.code.replace(old, new, 1)), name + " survived")

if __name__ == "__main__":
    unittest.main()
