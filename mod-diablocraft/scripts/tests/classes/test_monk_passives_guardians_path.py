"""diablocraft-m6v00 (Monk 2.4.2): The Guardian's Path, Sixth Sense, Determination, Relentless Assault, Beacon of Ytar, Alacrity.

What this proves, and how:

  * **The logic that needs no core type.** tests/monk_passives_guardians_path/harness.cpp compiles the real
    dc_monk_passives_guardians_path.h and feeds it the sheets' numbers: the dodge only while dual wielding, the Spirit only with a
    two-hander, Sixth Sense on every element but Physical, Determination per enemy up to its maximum, Relentless Assault on
    any one of blind, frozen or stunned, Beacon of Ytar's contribution, Alacrity added to the sum the attack speed is built
    from and held to the cap. Eleven mutations planted in a scratch copy (at least one per passive) must each make it fail.
  * **The code reads what the sheets state.** Every (passive, token) dc_monk_passives_guardians_path.cpp reads by name is a row of
    monk_passive_values.csv, and the power files agree with the sheet where there is one (TheGuardiansPath SF_0 0.35 and SF_1
    0.15, SixthSense SF_0 0.25, RelentlessAssault SF_0 0.2, BeaconOfYtar SF_0 0.20; Determination and Alacrity have no power
    file), so no sheet row changes.
  * **The wiring.** The Monk's dodge, Spirit payment and damage bonus call the passives; the two attack speed sites of the
    combat code call Monk::AttackSpeed; the script is registered with the others.

What it does not prove: anything on a running server (docs/test-diablocraft-m6v00.md's `.dc stats` and `.dc hit` checks).

    python mod-diablocraft/scripts/tests/classes/test_monk_passives_guardians_path.py
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
SOURCES = ["src/classes/monk/dc_monk_passives_guardians_path.h", "src/combat/dc_damage_buckets.h",
           "tests/monk_passives_guardians_path/harness.cpp"]
CODE = MODULE / "src/classes/monk/dc_monk_passives_guardians_path.cpp"
HEADER = "src/classes/monk/dc_monk_passives_guardians_path.h"
WIZARD_LINE = "Wizard::Multipliers(player, shell.spellId, hit.factors);\n        Monk::Multipliers(player, target, shell.spellId, hit.factors);"
SIX = ["The Guardian's Path", "Sixth Sense", "Determination", "Relentless Assault", "Beacon of Ytar", "Alacrity"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(passive, token):
    rows = [r for r in read(D3 / "monk_passive_values.csv") if (r["skill"], r["rune"], r["token"]) == (passive, "", token)]
    assert len(rows) == 1, (passive, token, len(rows))
    return float(rows[0]["value"])


def attack_speed_cap():
    text = (MODULE / "data/generated/numeric_rules_0001.sql").read_text(encoding="utf-8")
    return float(re.search(r"\('attack_speed_cap',([0-9.]+),", text).group(1))


def in_additive_pool(effects):
    """True if the Monk's additive damage bonus (Monk::DamageBonus) carries one of the two multiplier passives."""
    body = effects[effects.index("double DamageBonus("):effects.index("double TargetBonus(")]
    return bool(re.search(r"Passives242::(DamageBonus|Multipliers)|\"Determination\"|\"Relentless Assault\"", body))


def multipliers_called(combat):
    """True if the hit's multipliers ask the Monk, right after the Wizard's."""
    return WIZARD_LINE in combat


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/monk_passives_guardians_path/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("The Guardian's Path", "dodge_pct"), value("The Guardian's Path", "regen_pct"),
               value("Determination", "damage_bonus_pct"), value("Determination", "max_bonus_pct"),
               value("Relentless Assault", "damage_bonus_pct"), value("Beacon of Ytar", "cooldown_reduction_pct"),
               value("Alacrity", "attack_speed_pct"), attack_speed_cap()]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 32, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        det = "std::clamp(perEnemyPct * double(enemies), 0.0, std::max(0.0, maxPct))"
        rel = "return (blind || frozen || stunned) && pct > 0 ? pct : 0.0;"
        mutations = [
            ("Guardian's Path dodges with one weapon", (HEADER, "return dualWielding && pct > 0 ? pct : 0.0;",
                                                        "return pct > 0 ? pct : 0.0;")),
            ("Guardian's Path generates more with anything", (HEADER, "return twoHanded && pct > 0 ? 1.0 + pct / 100.0 : 1.0;",
                                                              "return pct > 0 ? 1.0 + pct / 100.0 : 1.0;")),
            ("Sixth Sense reduces Physical too", (HEADER, "return !physical;", "return true;")),
            ("Determination has no maximum", (HEADER, det, "perEnemyPct * double(enemies)")),
            ("Determination ignores the enemies", (HEADER, det, "std::min(perEnemyPct, std::max(0.0, maxPct))")),
            ("Relentless Assault needs all three", (HEADER, rel,
                                                    "return (blind && frozen && stunned) && pct > 0 ? pct : 0.0;")),
            ("Relentless Assault forgets blind", (HEADER, rel, "return (frozen || stunned) && pct > 0 ? pct : 0.0;")),
            ("Beacon of Ytar is not held to the range", (HEADER, "return std::clamp(pct, 0.0, 100.0);", "return pct;")),
            ("Alacrity multiplies instead of adding", (HEADER, "(1.0 + (iasPct + bonusPct) / 100.0)",
                                                       "(1.0 + bonusPct / 100.0)")),
            ("Alacrity goes past the cap", (HEADER, "std::max(aps, std::min(cap, sped))", "std::max(aps, sped)")),
            ("Alacrity slows when the speed is over the cap", (HEADER, "std::max(aps, std::min(cap, sped))",
                                                               "std::min(cap, sped)")),
        ]
        # The two bonuses are factors of their own: a build that puts them back in the additive pool, or never asks the Monk
        # for its multipliers, fails the wiring checks below.
        effects = (MODULE / "src/classes/monk/dc_monk_effects.cpp").read_text(encoding="utf-8")
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.assertFalse(in_additive_pool(effects))
        self.assertTrue(in_additive_pool(effects.replace("return ally + (book ? book->Total(Now()) : 0);\n    }\n\n    double TargetBonus",
                                                         "return Passives242::DamageBonus(player, target) + ally + (book ? book->Total(Now()) : 0);\n    }\n\n    double TargetBonus")))
        self.assertTrue(multipliers_called(combat))
        self.assertFalse(multipliers_called(combat.replace("        Monk::Multipliers(player, target, shell.spellId, hit.factors);\n", "")))
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_six_passives_are_on_the_sheets_with_their_numbers(self):
        names = {r["passive_name"] for r in read(D3 / "monk_passives.csv")}
        for passive in SIX:
            self.assertIn(passive, names)
        self.assertEqual((value("The Guardian's Path", "dodge_pct"), value("The Guardian's Path", "regen_pct")), (35, 15))
        self.assertEqual(value("Sixth Sense", "damage_reduction_pct"), 25)
        self.assertEqual([value("Determination", t) for t in ("radius_yards", "damage_bonus_pct", "max_bonus_pct")], [12, 4, 20])
        self.assertEqual(value("Relentless Assault", "damage_bonus_pct"), 20)
        self.assertEqual(value("Beacon of Ytar", "cooldown_reduction_pct"), 20)
        self.assertEqual(value("Alacrity", "attack_speed_pct"), 15)

    def test_the_power_files_and_the_sheet_agree(self):
        # Power/Monk_Passive_TheGuardiansPath.pow (decoded): SF_0 'Dodge Chance Increase' 0.35, SF_1 'Spirit Generation
        # Increase' 0.15. Monk_Passive_SixthSense.pow: SF_0 'Non-Physical Damage Reduction' 0.25.
        # p1_Monk_Passive_RelentlessAssault.pow: SF_0 'Damage Increase if CCed' 0.2. Monk_Passive_BeaconOfYtar.pow: SF_0
        # 'Cooldown Cost Reduction' 0.20. Determination and Alacrity have no power file.
        self.assertEqual(value("The Guardian's Path", "dodge_pct") / 100, 0.35)
        self.assertEqual(value("The Guardian's Path", "regen_pct") / 100, 0.15)
        self.assertEqual(value("Sixth Sense", "damage_reduction_pct") / 100, 0.25)
        self.assertEqual(value("Relentless Assault", "damage_bonus_pct") / 100, 0.2)
        self.assertEqual(value("Beacon of Ytar", "cooldown_reduction_pct") / 100, 0.2)

    def test_every_name_the_code_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        sheet = {(r["skill"], r["token"]) for r in read(D3 / "monk_passive_values.csv")}
        reads = set(re.findall(r'Num\(\s*"([^"]+)",\s*"([a-z_]+)"\s*\)', text))
        self.assertGreaterEqual(len(reads), 7)
        self.assertEqual(reads - sheet, set())
        # Sixth Sense's and Beacon of Ytar's are read by the id the Refresh holds.
        for token, passive in (("damage_reduction_pct", "Sixth Sense"), ("cooldown_reduction_pct", "Beacon of Ytar")):
            self.assertIn(f'"{token}"', text)
            self.assertIn((passive, token), sheet)


if __name__ == "__main__":
    unittest.main()
