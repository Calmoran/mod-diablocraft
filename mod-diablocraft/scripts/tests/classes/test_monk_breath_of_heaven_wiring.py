"""The source-text guards of monk breath of heaven: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_breath_of_heaven.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source
from test_monk_breath_of_heaven import CODE, MODULE, SKILL  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = CODE.read_text(encoding="utf-8")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")

    def test_the_monk_hands_the_skill_over(self):
        self.assertIn("return Breath::Cast(player, spellId, targets);", self.monk)
        self.assertIn("Breath::Attack(player, generated && *generated > 0);", self.monk)

    def test_the_runes_do_what_their_sentence_says(self):
        self.assertIn('HealAmount(minLife, maxLife, rand_norm(), share, 0.0)', self.code)
        self.assertIn('IsRune(spellId, "Circle of Scorn")', self.code)
        self.assertIn('Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"))', self.code)
        self.assertRegex(self.code, r'Effects::Dealt\(player, spellId, Numbers::Num\(spellId, "damage_bonus_pct"\),\s+'
                                    r'Numbers::Num\(spellId, "duration_seconds"\)\)')
        self.assertIn('IsRune(spellId, "Infused with Light")', self.code)
        self.assertIn('IsRune(spellId, "Zephyr")', self.code)
        self.assertIn('Numbers::Num(spellId, "gain_resource")', self.code)

    def test_the_wave_is_not_named_in_the_barbarians_file(self):
        self.assertNotIn(SKILL, barbarian_source.abilities())


if __name__ == "__main__":
    unittest.main()
