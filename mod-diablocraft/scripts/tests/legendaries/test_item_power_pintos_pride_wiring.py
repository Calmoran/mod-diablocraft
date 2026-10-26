"""The source-text guards of pintos pride: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_pintos_pride.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import test_item_power_jangs_envelopment as jang
from test_item_power_pintos_pride import SKILL  # noqa: E402


SRC = jang.SRC


class Hooks(unittest.TestCase):
    def test_every_wave_of_light_shell_names_the_skill(self):
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        for rune in ("", "Wall of Light", "Explosive Light", "Pillar of the Ancients", "Empowered Wave", "Shattering Light"):
            self.assertRegex(shells, r'\{\d+, "%s", "%s", ' % (SKILL, rune))

    def test_the_skill_factor_reads_the_shells_skill(self):
        combat = (SRC / "combat/dc_combat.cpp").read_text(encoding="utf-8")
        self.assertIn("std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;", combat)
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct") * ItemPowers::DealtFactor(player)', combat)

    def test_wave_of_light_strikes_report_the_hit(self):
        """Wave of Light damages through Combat::Strike; Strike reports a non-periodic strike as a hit (Passives::Hit -> ItemPowers::Hit)."""
        wave = (SRC / "classes/monk/dc_monk_wave_of_light.cpp").read_text(encoding="utf-8")
        self.assertEqual(4, wave.count("Combat::Strike(player, enemy, spellId"))
        combat = (SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")
        strike = combat[combat.index("bool Strike(Player* player, Unit* target, std::uint32_t spellId, std::optional<double> pct, bool periodic)"):]
        strike = strike[:strike.index("\n    }\n")]
        self.assertRegex(strike, r"if \(!periodic\)\s*\{[^}]*Passives::Hit\(player, target, spellId, hit\.school\);")
        self.assertIn("ItemPowers::Hit(p, target, spellId);", (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
