"""The source-text guards of monk mantra of salvation: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_mantra_of_salvation.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import monk_source
from test_monk_mantra_of_salvation import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = monk_source.section("Salvation")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")

    def test_the_monk_hands_the_skill_over(self):
        self.assertIn("return Salvation::Cast(player, spellId, targets);", self.monk)
        self.assertIn("Salvation::Touch(player);", self.monk)
        self.assertIn("DashingStrike::Dodge(unit) + Salvation::Dodge(unit)", self.monk)

    def test_the_cast_takes_the_slot_and_the_pulse_keeps_to_it(self):
        # the shared press makes it the Mantra in force with its boost window, the shared loop pulses while it is
        # (test_monk_mantras.py checks the loop reads the one state)
        self.assertIn("Mantras::Press(flavour, player, spellId, targets);", self.code)
        self.assertIn("Mantras::StartPulse(flavour, player);", self.code)
        self.assertTrue(monk_source.flavour("Salvation")["boosts"])

    def test_the_active_is_the_skills_not_the_runes(self):
        self.assertIn("std::uint32_t const base = Mantras::BaseId(Skill);", self.code)
        self.assertRegex(self.code, r'Numbers::Num\(base, "duration_seconds"\)')
        self.assertRegex(self.code, r'Numbers::Num\(base, "resistance_pct", "active"\)')


if __name__ == "__main__":
    unittest.main()
