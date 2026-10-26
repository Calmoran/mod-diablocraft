"""The source-text guards of halo of karini: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_halo_of_karini.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import wizard_source
from test_item_power_halo_of_karini import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cls.header = (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8")
        cls.wizard = wizard_source.CPP.read_text(encoding="utf-8")

    def test_the_shock_reads_its_yards_and_fires_the_event(self):
        self.assertIn("void StormArmorShock(Player*, Unit*);", self.header)
        shock = self.powers[self.powers.index("void StormArmorShock(Player* player, Unit* target)"):]
        shock = shock[:shock.index("\n    }\n")]
        self.assertIn("player->GetDistance(target)", shock)     # the way DistanceFactor and Power Hungry read it
        self.assertIn('Fire(player, "storm_armor_shock", "", 1.0, target, 0, ', shock)
        fire = self.powers[self.powers.index("void Fire(Player* player, char const* event"):self.powers.index("constexpr std::uint32_t ImmuneKey")]
        self.assertIn("situation.eventYards = yards;", fire)
        self.assertLess(fire.index("situation.eventYards = yards;"), fire.index("fired = ItemPower::Fire("))

    def test_both_electrocutes_of_storm_armor_call_it(self):
        # the armor's own tick (one random enemy in the radius) and Shocking Aspect's shock on a critical hit
        self.assertIn('if (IsSkill(id, "Storm Armor"))\n                    Armors::StormArmorTick(player, id);', self.wizard)
        tick = self.wizard[self.wizard.index("void StormArmorTick(Player* player, uint32 id)"):]
        tick = tick[:tick.index("void FrozenStormTick(")]
        self.assertIn("Combat::Strike(player, shocked, id);", tick)
        self.assertLess(tick.index("Combat::Strike(player, shocked, id);"), tick.index("ItemPowers::StormArmorShock(player, shocked);"))
        aspect = self.wizard[self.wizard.index('IsRune(armor, "Shocking Aspect") && hit.critical'):]
        aspect = aspect[:aspect.index("void ChillingAura(")]
        self.assertIn("Combat::Strike(p, u, armor, Num(armor, \"damage_pct\"));", aspect)
        self.assertIn("ItemPowers::StormArmorShock(p, u);", aspect)


if __name__ == "__main__":
    unittest.main()
