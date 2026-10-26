"""The source-text guards of monk blinding flash: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_blinding_flash.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_blinding_flash import CODE, MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.code = CODE.read_text(encoding="utf-8")

    def test_the_monk_hands_the_skill_over_before_the_empty_target_check(self):
        dispatch = self.monk.index("return BlindingFlash::Cast(player, spellId);")
        self.assertLess(dispatch, self.monk.index("if (!player || !row || targets.empty())"))
        self.assertIn("return BlindingFlash::MissChance(attacker);", self.monk)

    def test_the_miss_is_rolled_after_the_avoid_chances_are_zeroed(self):
        zeroed = self.combat.index("miss_chance = parry_chance = block_chance = 0;")
        miss = self.combat.index("miss_chance = int32((Monk::MissChance(attacker) + Shaman::MissChance(attacker)) * 100);")
        self.assertLess(zeroed, miss)
        self.assertLess(miss - zeroed, 200)

    def test_the_runes_do_what_their_sentence_says(self):
        self.assertIn('IsRune(spellId, "Faith in the Light")', self.code)
        self.assertRegex(self.code, r'IsRune\(spellId, "Replenishing Light"\) && blinded\)\s+Resources::Energize')
        self.assertRegex(self.code, r'Hold\(player, enemy, Slowed, -int\(Numbers::Num\(spellId, "slow_pct"\) \+ 0\.5\),')
        self.assertIn("WeakenAfterMs(seconds)", self.code)


if __name__ == "__main__":
    unittest.main()
