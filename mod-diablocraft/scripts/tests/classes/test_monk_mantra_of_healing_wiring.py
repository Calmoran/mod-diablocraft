"""The source-text guards of monk mantra of healing: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_mantra_of_healing.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import monk_source
from test_monk_mantra_of_healing import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.code = monk_source.section("Healing")

    def test_the_monk_hands_the_skill_over_and_starts_the_pulse(self):
        self.assertIn("return Healing::Cast(player, spellId, targets);", self.monk)
        self.assertIn("Healing::Touch(player);", self.monk)
        self.assertIn("Healing::Landed(player, spellId);", self.monk)

    def test_the_absorb_is_the_stock_shield_and_the_heal_is_holy(self):
        self.assertIn("constexpr std::uint32_t Shield = 17;", self.code)
        self.assertIn("SPELL_SCHOOL_MASK_HOLY", self.code)

    def test_the_runes_do_what_their_sentence_says(self):
        self.assertIn('IsRune(Skill, runeId, "Heavenly Body")', self.code)
        self.assertIn('IsRune(Skill, runeId, "Time of Need")', self.code)
        self.assertIn('IsRune(Skill, runeId, "Circular Breathing")', self.code)
        self.assertIn('IsRune(Skill, runeId, "Boon of Inspiration")', self.code)
        self.assertIn("Stat::LifePercent", self.code)
        self.assertIn("Stat::SpecificReduction", self.code)

    def test_the_globe_bonus_has_no_stat_yet(self):
        self.assertRegex(self.code, r'"healing_bonus_share_pct"\), 0\.0\)')


if __name__ == "__main__":
    unittest.main()
