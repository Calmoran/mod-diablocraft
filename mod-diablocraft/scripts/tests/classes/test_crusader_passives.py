"""The Crusader's eighteen passives, in unlock order: Heavenly Strength, Fervor, Vigilant, Righteousness, Insurmountable, Fanaticism,
Indestructible, Holy Cause, Wrathful, Divine Fortress, Lord Commander, Hold Your Ground, Long Arm of the Law, Iron Maiden, Renewal,
Finery, Blunt, Towering Shield (src/classes/crusader/dc_crusader_passives.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/crusader_passives/harness.cpp compiles the real dc_crusader_passives.h with the
    sheets' numbers: Fervor is on with a one-handed weapon (shield or not) and with no other grip; Heavenly Strength's reduction
    is paid for a two-handed weapon with a shield and for no other grip; Vigilant reduces every element but Physical; Fanaticism
    names Punish, Slash, Smite and Justice and no other skill, and adds its share to the sum the skill's speed was built from,
    held to the attack speed cap and never below what it was; Righteousness pays its extra Wrath for a primary only;
    Insurmountable pays the sheet's Wrath; the cooldown contribution is held to 0 through 100. Indestructible saves a fatal hit
    once, for its seconds, and not again inside its cooldown; Holy Cause heals for a Holy hit only; Wrathful heals per point of Wrath;
    Divine Fortress' Armor is the Block Chance; Lord Commander names Steed Charge and Bombardment with their own shares, cuts a share
    of the cooldown left and gives Phalanx alone its damage; Hold Your Ground ends dodging. Long Arm of the Law lengthens a Law's active time by its seconds,
    Renewal heals the sheet's Life on a block, Finery gives its percent for each gem, Blunt and Towering Shield name their skills.
    Heavenly Strength's grip is a Crusader with the passive and nobody else (another class, or a Crusader without it, is refused), and
    a two-hander with a shield is a broken grip only once the grip is not allowed.
    Thirty-seven mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_crusader_passives.cpp reads by name is a row of
    crusader_passive_values.csv for its passive, the generated value map says whose record holds it, and the numbers are the
    researched ones: Heavenly Strength 20% less damage, Fervor 15% attack speed and 15% cooldown reduction, Vigilant 2682 Life a
    second and 20% less non-Physical damage, Righteousness 3 Wrath and 30 more, Insurmountable 6 Wrath, Fanaticism 15%, Indestructible
    35% damage, 107284 Life per Kill for 5 seconds once a minute, Holy Cause 10% damage and 1% Life, Wrathful 1341 Life a point,
    Lord Commander 25% and 35% cooldown and 20% Phalanx damage, Hold Your Ground 30% Block Chance, Long Arm of the Law 5 seconds,
    Iron Maiden 50% Thorns, Renewal 16093 Life, Finery 1.5% Strength a gem, Blunt 20%, Towering Shield 20% damage and 30% cooldown. Wrathful's Health Globe share is the one
    row the code does not read (Torment has no such stat).
  * **Unlock levels.** Heavenly Strength and Fervor 10, Vigilant 13, Righteousness 16, Insurmountable and Fanaticism 20, Indestructible
    25, Holy Cause 27, Wrathful and Divine Fortress 30, Lord Commander 35, Hold Your Ground 40.

What it does not prove: anything on a running server. Heavenly Strength's grip needs core patch 0031 (the PlayerScript hook the
Crusader answers, core-patches/tests/test_titan_grip_hook.py): the module does not build against a core without it.

    python mod-diablocraft/scripts/tests/classes/test_crusader_passives.py
"""

import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/crusader/dc_crusader_passives.h"
SOURCES = [HEADER, "src/common/dc_common.h", "tests/crusader_passives/harness.cpp"]
CODE = MODULE / "src/classes/crusader/dc_crusader_passives.cpp"
PASSIVES = ["Heavenly Strength", "Fervor", "Vigilant", "Righteousness", "Insurmountable", "Fanaticism", "Indestructible", "Holy Cause",
            "Wrathful", "Divine Fortress", "Lord Commander", "Hold Your Ground", "Long Arm of the Law", "Iron Maiden", "Renewal", "Finery",
            "Blunt", "Towering Shield"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(passive, token, qualifier=""):
    rows = [r for r in read(D3 / "crusader_passive_values.csv")
            if (r["skill"], r["token"], r["qualifier"]) == (passive, token, qualifier)]
    assert len(rows) == 1, (passive, token, qualifier, len(rows))
    return float(rows[0]["value"])


def skill_seconds():
    rows = [r for r in read(D3 / "crusader_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == ("Laws of Valor", "", "duration_seconds", "")]
    assert len(rows) == 1
    return float(rows[0]["value"])


def attack_speed_cap():
    text = (MODULE / "data/generated/numeric_rules_0001.sql").read_text(encoding="utf-8")
    return float(re.search(r"\('attack_speed_cap',([0-9.]+),", text).group(1))


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/crusader_passives/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Heavenly Strength", "damage_dealt_reduction_pct"), value("Fanaticism", "attack_speed_pct"),
               value("Righteousness", "generated_resource"), value("Insurmountable", "gain_resource"),
               value("Fervor", "cooldown_reduction_pct"), attack_speed_cap(),
               value("Indestructible", "duration_seconds"), value("Indestructible", "internal_cooldown_seconds"),
               value("Holy Cause", "heal_pct"), value("Wrathful", "heal_per_hit_life"),
               value("Lord Commander", "cooldown_reduction_pct", "steed_charge"),
               value("Lord Commander", "cooldown_reduction_pct", "bombardment"),
               value("Long Arm of the Law", "duration_seconds"), value("Renewal", "heal_life"), value("Finery", "primary_stat_pct"),
               value("Towering Shield", "cooldown_reduction_pct"), skill_seconds()]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 45, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        heavenly = "return wield.twoHand && wield.shield && reductionPct > 0 ? reductionPct : 0.0;"
        sped = "double const sped = aps * (1.0 + (iasPct + bonusPct) / 100.0) / (1.0 + iasPct / 100.0);"
        mutations = [
            ("Fervor without a weapon", (HEADER, "return wield.oneHand;", "return true;")),
            ("Fervor with a two-hander", (HEADER, "return wield.oneHand;", "return wield.oneHand || wield.twoHand;")),
            ("Heavenly Strength with no shield", (HEADER, heavenly, "return wield.twoHand && reductionPct > 0 ? reductionPct : 0.0;")),
            ("Heavenly Strength with no two-hander", (HEADER, heavenly, "return wield.shield && reductionPct > 0 ? reductionPct : 0.0;")),
            ("Heavenly Strength always", (HEADER, heavenly, "return reductionPct > 0 ? reductionPct : 0.0;")),
            ("the grip for any class", (HEADER, "return crusader && passiveOn;", "return passiveOn;")),
            ("the grip without the passive", (HEADER, "return crusader && passiveOn;", "return crusader;")),
            ("a broken grip needs no shield", (HEADER, "return wield.twoHand && wield.shield && !gripAllowed;",
                                               "return wield.twoHand && !gripAllowed;")),
            ("a broken grip needs no two-hander", (HEADER, "return wield.twoHand && wield.shield && !gripAllowed;",
                                                   "return wield.shield && !gripAllowed;")),
            ("a broken grip ignores the passive", (HEADER, "return wield.twoHand && wield.shield && !gripAllowed;",
                                                   "return wield.twoHand && wield.shield;")),
            ("Vigilant reduces Physical too", (HEADER, "return element != Element::Physical;", "return true;")),
            ("Fanaticism for every skill", (HEADER, 'return skill == "Punish" || skill == "Slash" || skill == "Smite" || skill == "Justice";',
                                            "return !skill.empty();")),
            ("Fanaticism misses Justice", (HEADER, ' || skill == "Justice";', ";")),
            ("Fanaticism multiplies instead of adding", (HEADER, sped, "double const sped = aps * (1.0 + bonusPct / 100.0);")),
            ("Fanaticism ignores the cap", (HEADER, "return std::max(aps, std::min(cap, sped));", "return std::max(aps, sped);")),
            ("Fanaticism can slow", (HEADER, "return std::max(aps, std::min(cap, sped));", "return std::min(cap, sped);")),
            ("Righteousness pays for every skill", (HEADER, "return primary && extra > 0 ? extra : 0.0;", "return extra > 0 ? extra : 0.0;")),
            ("a block pays nothing", (HEADER, "return gain > 0 ? gain : 0.0;", "return 0.0;")),
            ("Indestructible saves a hit that leaves Life", (HEADER, "if (now < readyAt || damage < health || durationMs == 0)",
                                                             "if (now < readyAt || durationMs == 0)")),
            ("Indestructible ignores its cooldown", (HEADER, "if (now < readyAt || damage < health || durationMs == 0)",
                                                     "if (damage < health || durationMs == 0)")),
            ("Indestructible lasts one millisecond too long", (HEADER, "return now < until;", "return now <= until;")),
            ("Indestructible's cooldown starts when the save ends", (HEADER, "readyAt = now + cooldownMs;", "readyAt = until + cooldownMs;")),
            ("Holy Cause heals for every hit", (HEADER, "return holy && maxLife > 0 && healPct > 0 ?", "return maxLife > 0 && healPct > 0 ?")),
            ("Wrathful heals for the cost twice", (HEADER, "return perPoint > 0 && wrath > 0 ? perPoint * wrath : 0.0;",
                                                   "return perPoint > 0 && wrath > 0 ? perPoint * wrath * 2 : 0.0;")),
            ("Divine Fortress can go negative", (HEADER, "return std::max(0.0, blockChancePct);", "return blockChancePct;")),
            ("Lord Commander cuts Provoke too", (HEADER, 'if (skill == "Bombardment")\n            return "bombardment";',
                                                 'if (skill == "Bombardment" || skill == "Provoke")\n            return "bombardment";')),
            ("a cut is not held to the share", (HEADER, "double const cut = leftMs * std::clamp(pct, 0.0, 100.0) / 100.0;",
                                                "double const cut = leftMs * pct / 100.0;")),
            ("Lord Commander's damage bonus for every skill", (HEADER, 'return skill == "Phalanx";', "return true;")),
            ("Hold Your Ground still dodges", (HEADER, "return holdYourGround ? 0.0 : 1.0;", "return 1.0;")),
            ("Long Arm lengthens an effect of no time", (HEADER, "return seconds > 0 && bonus > 0 ? seconds + bonus : seconds;",
                                                         "return bonus > 0 ? seconds + bonus : seconds;")),
            ("Long Arm ignores the passive's number", (HEADER, "return seconds > 0 && bonus > 0 ? seconds + bonus : seconds;",
                                                       "return seconds;")),
            ("Renewal heals when nothing was given", (HEADER, "return life > 0 ? life : 0.0;", "return life;")),
            ("Finery counts one gem too few", (HEADER, "return perGem > 0 ? perGem * gems : 0.0;", "return perGem > 0 && gems > 0 ? perGem * (gems - 1) : 0.0;")),
            ("Blunt reaches Blessed Shield", (HEADER, 'return skill == "Justice" || skill == "Blessed Hammer";',
                                              'return skill == "Justice" || skill == "Blessed Hammer" || skill == "Blessed Shield";')),
            ("Towering Shield misses Blessed Shield", (HEADER, ' || skill == "Blessed Shield";\n    }\n\n    // Towering Shield: "Reduce', ';\n    }\n\n    // Towering Shield: "Reduce')),
            ("Towering Shield cuts Shield Bash's cooldown", (HEADER, 'return skill == "Shield Glare";', 'return skill == "Shield Glare" || skill == "Shield Bash";')),
            ("the cooldown is not held to 100", (HEADER, "return std::clamp(pct, 0.0, 100.0);", "return pct;")),
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
        self.assertEqual(value("Heavenly Strength", "damage_dealt_reduction_pct"), 20)
        self.assertEqual((value("Fervor", "attack_speed_pct"), value("Fervor", "cooldown_reduction_pct")), (15, 15))
        self.assertEqual((value("Vigilant", "heal_per_second_life"), value("Vigilant", "damage_reduction_pct")), (2682, 20))
        self.assertEqual((value("Righteousness", "generated_resource"), value("Righteousness", "max_pool_resource")), (3, 30))
        self.assertEqual(value("Insurmountable", "gain_resource"), 6)
        self.assertEqual(value("Fanaticism", "attack_speed_pct"), 15)
        self.assertEqual([value("Indestructible", t) for t in ("damage_bonus_pct", "heal_per_hit_life", "duration_seconds",
                                                               "internal_cooldown_seconds")], [35, 107284, 5, 60])
        self.assertEqual((value("Holy Cause", "damage_bonus_pct"), value("Holy Cause", "heal_pct")), (10, 1))
        self.assertEqual((value("Wrathful", "heal_per_hit_life"), value("Wrathful", "healing_bonus_share_pct")), (1341, 1))
        self.assertEqual((value("Lord Commander", "cooldown_reduction_pct", "steed_charge"),
                          value("Lord Commander", "cooldown_reduction_pct", "bombardment"),
                          value("Lord Commander", "damage_bonus_pct")), (25, 35, 20))
        self.assertEqual(value("Hold Your Ground", "block_pct"), 30)
        self.assertEqual(value("Long Arm of the Law", "duration_seconds"), 5)
        self.assertEqual(value("Iron Maiden", "thorns_pct"), 50)
        self.assertEqual(value("Renewal", "heal_life"), 16093)
        self.assertEqual(value("Finery", "primary_stat_pct"), 1.5)
        self.assertEqual(value("Blunt", "damage_bonus_pct"), 20)
        self.assertEqual((value("Towering Shield", "damage_bonus_pct"), value("Towering Shield", "cooldown_reduction_pct")), (20, 30))

    def test_the_unlock_levels(self):
        levels = {r["passive_name"]: int(r["unlock_level"]) for r in read(D3 / "crusader_passives.csv")}
        self.assertEqual([levels[p] for p in PASSIVES], [10, 10, 13, 16, 20, 20, 25, 27, 30, 30, 35, 40, 45, 50, 55, 60, 65, 70])

    def test_every_token_the_code_reads_is_a_sheet_row_the_engine_can_read(self):
        text = CODE.read_text(encoding="utf-8")
        tokens = set(re.findall(r'"([a-z_]+_(?:pct|life|resource|seconds))"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "crusader_passive_values.csv") if r["skill"] in PASSIVES}
        self.assertEqual(tokens - sheet_tokens, set())
        # The one row the code does not read: Wrathful's share of a Health Globe Healing Bonus, a stat Torment does not have.
        self.assertEqual(sheet_tokens - tokens, {"healing_bonus_share_pct"})
        mapped = {(r["skill"], r["token"]) for r in read(MODULE / "data/generated/spell_value_map.csv")}
        for row in read(D3 / "crusader_passive_values.csv"):
            if row["skill"] in PASSIVES:
                with self.subTest(passive=row["skill"], token=row["token"]):
                    self.assertIn((row["skill"], row["token"]), mapped)


if __name__ == "__main__":
    unittest.main()
