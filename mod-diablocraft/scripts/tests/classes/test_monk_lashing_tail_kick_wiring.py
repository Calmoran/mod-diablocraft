"""The source-text guards of monk lashing tail kick: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_lashing_tail_kick.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source
from test_monk_lashing_tail_kick import CODE, MODULE, SKILL  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = CODE.read_text(encoding="utf-8")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")

    def test_the_monk_hands_the_skill_over(self):
        self.assertIn("return Kick::BasePct(spellId);", self.monk)
        self.assertIn("return Kick::Cast(player, spellId, targets);", self.monk)

    def test_the_runes_do_what_their_sentence_says(self):
        self.assertIn('bool const around = IsRune(spellId, "Vulture Claw Kick") || IsRune(spellId, "Sweeping Armada");', self.code)
        self.assertRegex(self.code, r'IsRune\(spellId, "Hand of Ytar"\)\)\s+for \(Unit\* enemy : struck\)\s+'
                                    r'Hold\(player, enemy, Slowed, SlowAmount\(Numbers::Num\(spellId, "slow_pct"\)\),\s+'
                                    r'Numbers::Num\(spellId, "slow_duration_seconds"\)\)')
        self.assertRegex(self.code, r'IsRune\(spellId, "Scorpion Sting"\)\)\s+for \(Unit\* enemy : struck\)\s+'
                                    r'Hold\(player, enemy, Stunned, 0, Numbers::Num\(spellId, "stun_duration_seconds"\) \* ItemPowers::StunFactor\(player\)\)')   # Dovu Energy Trap (diablocraft-dxqyr)
        self.assertIn('Numbers::Get(spellId, "damage_pct", "hit")', self.code)
        self.assertIn('Numbers::Num(spellId, "damage_pct", "dot")', self.code)

    def test_every_struck_enemy_is_thrown_by_the_stock_record(self):
        self.assertRegex(self.code, r"for \(Unit\* enemy : struck\)\s+if \(Knocks\(true, enemy->IsAlive\(\)\)\)\s+"
                                    r"player->CastSpell\(enemy, Shells::PylonSpeedThrow, true\);")
        self.assertLess(self.code.index("Shells::PylonSpeedThrow"), self.code.index("Burn(player, enemy, spellId)"))

    def test_without_its_blank_tunables_the_burn_and_the_column_are_not_built(self):
        self.assertIn('DC::Tunables::Has("monk", "lashing_tail_kick_dot_tick_seconds")', self.code)
        self.assertIn('DC::Tunables::Has("monk", "lashing_tail_kick_column_width_yards")', self.code)

    def test_the_kick_is_not_named_in_the_barbarians_file(self):
        self.assertNotIn(SKILL, barbarian_source.abilities())


if __name__ == "__main__":
    unittest.main()
