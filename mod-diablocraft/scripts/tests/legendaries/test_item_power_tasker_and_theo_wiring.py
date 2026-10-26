"""The source-text guards of tasker and theo: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_tasker_and_theo.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import wizard_source
from test_item_power_tasker_and_theo import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cls.header = (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8")
        cls.ancients = (SRC / "classes/barbarian/dc_barbarian_call_of_the_ancients.cpp").read_text(encoding="utf-8")
        cls.wizard = wizard_source.CPP.read_text(encoding="utf-8")

    def test_the_reader_is_the_players_stat(self):
        self.assertIn("double PetSpeedFactor(Player const*);", self.header)
        self.assertIn('double PetSpeedFactor(Player const* player)\n    {\n        return PlayerFactor(player, "pet_attack_speed_pct");\n    }', self.powers)

    def test_the_ancients_and_the_hydra_swing_faster(self):
        update = self.ancients[self.ancients.index("void UpdateAI(uint32 diff) override"):]
        self.assertIn('double aps = Combat::AttacksPerSecond(p) * Combat::ItemPowers::SkillFactor(p, "Call of the Ancients", "summon_attack_speed_pct") *\n'
                      '                             Combat::ItemPowers::PetSpeedFactor(p);', update)
        self.assertLess(update.index("PetSpeedFactor(p)"), update.index("swing >= 1000 / aps"))
        hydra = self.wizard[self.wizard.index("class HydraAI final"):self.wizard.index("} // namespace DC::Combat::Wizard::Hydra")]
        self.assertIn("double const aps = Combat::AttacksPerSecond(player, source) * Combat::ItemPowers::PetSpeedFactor(player);", hydra)
        self.assertLess(hydra.index("PetSpeedFactor(player)"), hydra.index("double const frames"))

    def test_the_familiar_and_the_images_do_not(self):
        self.assertEqual(1, self.wizard.count("PetSpeedFactor"))                     # the Hydra's, nothing else in the Wizard's files
        self.assertEqual(1, self.ancients.count("PetSpeedFactor"))
        familiar = self.wizard[self.wizard.index("uint32 const familiar = BuffOf(player, \"Familiar\");"):
                                 self.wizard.index("} // namespace DC::Combat::Wizard::Familiar")]
        self.assertIn("Combat::AttacksPerSecond(player, familiar)", familiar)
        self.assertNotIn("PetSpeedFactor", familiar)


if __name__ == "__main__":
    unittest.main()
