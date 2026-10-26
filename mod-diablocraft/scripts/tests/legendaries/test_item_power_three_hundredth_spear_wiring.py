"""The source-text guards of three hundredth spear: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_three_hundredth_spear.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_three_hundredth_spear import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_hit_and_the_swing_read_the_base_skill_name(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn('std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;', combat)
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")', combat)
        speed = combat[combat.index("double HandAttacksPerSecond("):combat.index("std::pair<double, double> WeaponRange(")]
        self.assertIn('ItemPowers::SkillFactor(player, ability->skill, "attack_speed_pct")', speed)

    def test_weapon_throws_swing_recovery_is_its_hands_attacks_per_second(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cooldown = combat[combat.index("std::uint32_t SkillCooldownMilliseconds("):combat.index("// C1: every skill WITHOUT")]
        self.assertIn("PrimaryData::Find(spellId)", cooldown)
        self.assertIn("HandAttacksPerSecond(player, spellId, offhand)", cooldown)


if __name__ == "__main__":
    unittest.main()
