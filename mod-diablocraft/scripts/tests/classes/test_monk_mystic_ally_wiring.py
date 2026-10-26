"""The source-text guards of monk mystic ally: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_mystic_ally.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_mystic_ally import GLUE, MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def test_the_monk_hands_mystic_ally_over(self):
        monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        for function, call in (("std::optional<double> BasePct(std::uint32_t spellId)\n    {",
                                "if (MysticAlly::Is(spellId))\n            return MysticAlly::BasePct(spellId);"),
                               ("void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Punch const& punch)\n    {",
                                "if (MysticAlly::Is(spellId))\n            return MysticAlly::Cast(player, spellId);"),
                               ("void Landed(Player* player, Unit* target, std::uint32_t spellId)\n    {",
                                "MysticAlly::Landed(player, target, spellId);")):
            at = monk.index(function) + len(function)
            # the dispatch order among the skills is not this test's (earlier skills' lines come first): the call is in
            # this function's body
            self.assertIn(call, monk[at:monk.index("\n    }\n", at)], function)
        self.assertIn("MysticAlly::RegisterScripts();", monk)

    def test_fire_allys_bonus_is_in_the_damage_sum(self):
        effects = (MODULE / "src/classes/monk/dc_monk_effects.cpp").read_text(encoding="utf-8")
        self.assertIn("double const ally = MysticAlly::DamageBonus(player);", effects)
        self.assertIn("return ally + (book ? book->Total(Now()) : 0);", effects)

    def test_the_scripts_are_registered_once_beside_the_wizards(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.assertEqual(combat.count("Monk::RegisterScripts();"), 1)
        self.assertIn("Wizard::RegisterScripts();\n        Monk::RegisterScripts();", combat)
        self.assertIn('CreatureScript("dc_monk_ally")', GLUE.read_text(encoding="utf-8"))

    def test_every_hit_of_the_ally_is_the_monks_formula(self):
        glue = GLUE.read_text(encoding="utf-8")
        self.assertNotIn("DealSpellDamage", glue)
        self.assertNotIn("DoMeleeAttackIfReady", glue)  # the creature's own melee would add damage of its own
        self.assertGreaterEqual(glue.count("Combat::Strike"), 3)


if __name__ == "__main__":
    unittest.main()
