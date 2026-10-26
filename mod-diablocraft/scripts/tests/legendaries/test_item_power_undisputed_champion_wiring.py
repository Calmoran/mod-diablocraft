"""The source-text guards of undisputed champion: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_undisputed_champion.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_undisputed_champion import SRC  # noqa: E402


PRIMARIES = SRC / "classes/barbarian/dc_barbarian_primaries.cpp"


def guard(test, text):
    """The source-text guards on dc_barbarian_primaries.cpp, run on `text` so a mutant of it can be refused by the same checks."""
    test.assertIn('#include "../../combat/dc_item_powers.h"', text)
    given = text[text.index("bool Given(Player const* player, D::Row const& row)"):text.index("D::Row const* Effect(")]
    test.assertIn("return player && shell && *shell->rune && ItemPowers::GrantsRune(player, shell->skill, shell->rune);", given)
    effect = text[text.index("D::Row const* Effect("):text.index("double FuryGain(")]
    test.assertIn("if (active.behavior == behavior)\n                return &active;", effect)          # chosen: its own row, once
    test.assertIn('if (std::string(active.skill) != "Frenzy")\n                return nullptr;', effect)
    test.assertIn('if (row.behavior == behavior && std::string(row.skill) == "Frenzy" && Given(player, row))\n                    return &row;', effect)
    fury_gain = text[text.index("double FuryGain("):text.index("void Fury(Player* player, double amount)")]
    test.assertIn('if (std::string(row.skill) == "Frenzy" && row.fury > fury && Given(player, row))\n                        fury = row.fury;', fury_gain)
    # each reader asks the helper and uses the answered row's number
    bonus = text[text.index("double DamageBonus(Player* player)"):text.index("double CritBonus(")]
    test.assertIn("if (auto maniac = Effect(player, *row, B::maniac))\n                bonus += stacks * maniac->magnitude;", bonus)
    test.assertLess(bonus.index("        }\n        // Outside the lock"), bonus.index("Effect(player"))       # the item table has its own lock
    grant = text[text.index("void GrantFrenzy("):text.index("class dc_primary_spell final")]
    test.assertIn("auto vanguard = row ? Effect(player, *row, B::vanguard) : nullptr;\n        double const movement = vanguard ? shown * vanguard->magnitude : 0;", grant)
    test.assertLess(grant.index("        }\n        // The rune the last swing used"), grant.index("Effect(player"))
    begin = text[text.index("void Begin()"):text.index("void Seed(SpellEffIndex)")]
    test.assertIn("auto vanguard = Effect(player, *row, B::vanguard);\n                    movement = vanguard ? frenzyStacks * vanguard->magnitude : 0;", begin)
    test.assertLess(begin.index("casts.emplace(identity, std::move(state));\n                }"), begin.index("Effect(player"))
    landed = text[text.index("void Landed()"):text.index("void Finish()")]
    test.assertIn("auto const sidearm = Effect(player, *row, B::sidearm);\n                if (row->behavior == B::pulverize || (sidearm && roll_chance_f(float(sidearm->chance))))", landed)
    test.assertIn("                    if (sidearm)\n                    {\n                        auto enemies", landed)
    test.assertIn("if (auto smite = Effect(player, *row, B::smite); smite && roll_chance_f(float(smite->chance)))\n                        player->CastSpell(target, D::SMITE, true);", landed)
    provider = text[text.index("bool ProvideFinalSpellDamage("):text.index("class GeometryAndControl")]
    test.assertIn("grant = FuryGain(player, *row);", provider)
    # the old reads of the chosen row alone are gone
    for old in ("row->behavior == B::sidearm", "row->behavior == B::smite", "row->behavior == B::vanguard", "row->behavior == B::maniac", "grant = row->fury;"):
        test.assertNotIn(old, text)
    test.assertEqual(2, text.count("Effect(player, *row, B::vanguard)"))


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real = PRIMARIES.read_text(encoding="utf-8")

    def test_every_frenzy_rune_effect_reads_the_given_rune(self):
        guard(self, self.real)

    def test_the_mutants_fail_the_same_guards(self):
        r = self.real
        mutants = {
            "the_base_skill_is_a_rune": r.replace("shell && *shell->rune && ItemPowers", "shell && ItemPowers"),
            "a_rune_is_given_without_asking": r.replace("Given(player, row))\n                    return &row;", "true)\n                    return &row;"),
            "another_skill_gets_the_runes": r.replace('if (std::string(active.skill) != "Frenzy")\n                return nullptr;', ""),
            "maniac_reads_the_chosen_rune_only": r.replace("if (auto maniac = Effect(player, *row, B::maniac))", "if (auto maniac = row->behavior == B::maniac ? row : nullptr)"),
            "sidearm_reads_the_chosen_rune_only": r.replace("Effect(player, *row, B::sidearm)", "(row->behavior == B::sidearm ? row : nullptr)"),
            "smite_reads_the_chosen_rune_only": r.replace("auto smite = Effect(player, *row, B::smite)", "auto smite = row->behavior == B::smite ? row : nullptr"),
            "vanguard_on_the_swing_reads_the_chosen_rune_only": r.replace("auto vanguard = Effect(player, *row, B::vanguard);\n                    movement",
                                                                          "auto vanguard = row->behavior == B::vanguard ? row : nullptr;\n                    movement"),
            "vanguard_on_a_grant_reads_the_chosen_rune_only": r.replace("auto vanguard = row ? Effect(player, *row, B::vanguard) : nullptr;",
                                                                        "auto vanguard = row && row->behavior == B::vanguard ? row : nullptr;"),
            "berserk_is_not_given": r.replace("grant = FuryGain(player, *row);", "grant = row->fury;"),
            "the_lower_fury_wins": r.replace("row.fury > fury && Given", "row.fury < fury && Given"),
            "the_effect_is_read_in_the_lock": r.replace("        }\n        // Outside the lock: the item power table has its own.\n",
                                                        "        // Outside the lock: the item power table has its own.\n        }\n"),
        }
        for name, mutant in mutants.items():
            self.assertTrue(r != mutant, "the %s mutation no longer applies" % name)
            with self.subTest(name):
                with self.assertRaises((AssertionError, ValueError), msg="mutant %s passed" % name):
                    guard(self, mutant)


if __name__ == "__main__":
    unittest.main()
