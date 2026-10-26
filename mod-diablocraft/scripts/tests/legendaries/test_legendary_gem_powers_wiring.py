"""The source-text guards of legendary gem powers: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_legendary_gem_powers.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
from test_legendary_gem_powers import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    """Source-text guards: the call is there. They do not run the C++."""

    @classmethod
    def setUpClass(cls):
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.items = items_source.source()
        cls.powers = (SRC / "combat/dc_gem_powers.cpp").read_text(encoding="utf-8")

    def test_items_apply_refreshes_the_gem_list(self):
        self.assertIn("DC::Combat::GemPowers::Refresh(player, item, equipping, *instance);", self.items)

    def test_refresh_counts_then_resolves_and_feeds_the_sheet(self):
        self.assertIn("LegendaryGemItem::Counted(Worn(", self.powers)
        self.assertIn("GemPower::Resolve(active,", self.powers)
        self.assertIn("Stat::LifeRegen", self.powers)
        self.assertIn("Stat::Thorns", self.powers)

    def test_every_player_defence_path_asks_for_the_reductions(self):
        self.assertEqual(2, self.combat.count("GemPowers::IncomingFactor(victim->ToPlayer()"))
        # melee swing, melee-class spell, melee-class periodic tick, and the rift monster hit
        self.assertEqual(3, len(re.findall(r"ApplyPlayerDefence\([^;]*?(?:true|DmgClass == SPELL_DAMAGE_CLASS_MELEE), attacker\);",
                                           self.combat, re.S)))
        self.assertIn("Mitigate(victim, school, damage, nullptr, info->DmgClass == SPELL_DAMAGE_CLASS_MELEE, attacker)", self.combat)

    def test_step_8_carries_the_gem_factor(self):
        self.assertIn("Wizard::Standalone(player, target, shell.spellId) * GemPowers::SkillFactor(player, shell.spellId)",
                      self.combat)

    def test_the_cache_is_registered(self):
        self.assertIn("GemPowers::RegisterScripts();", self.combat)


if __name__ == "__main__":
    unittest.main()
