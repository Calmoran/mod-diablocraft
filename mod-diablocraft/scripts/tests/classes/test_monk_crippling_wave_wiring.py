"""The source-text guards of monk crippling wave: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_crippling_wave.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source
from test_monk_crippling_wave import CODE, MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = CODE.read_text(encoding="utf-8")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])

    def test_the_monk_hands_the_skill_over(self):
        self.assertIn("punch.stage = Wave::Begin(player, spellId);", self.monk)
        self.assertIn("Wave::Cast(player, spellId, targets, punch.stage);", self.monk)
        self.assertIn("Wave::Is(spellId) ? Wave::PerAttack(spellId)", self.monk)
        # Begin's dispatch comes before Fists of Thunder's own row lookup, Cast's before its early return.
        begin = self.monk.index("Wave::Begin(")
        self.assertLess(begin, self.monk.index("FistsOf(spellId);", begin))

    def test_the_cast_path_asks_the_monk_before_and_after_the_hits(self):
        order = [self.combat.index(m) for m in ("Monk::Begin(", "ResolveHit(player, target, punch.pct", "Monk::Cast(")]
        self.assertEqual(order, sorted(order))

    def test_the_debuff_runes_use_the_effects_layer(self):
        self.assertRegex(self.code, r'IsRune\(spellId, "Concussion"\)\)\s+for \(Unit\* enemy : struck\)\s+'
                                    r'Effects::Weaken\(enemy, spellId, Numbers::Num\(spellId, "enemy_damage_pct"\)')
        self.assertRegex(self.code, r'IsRune\(spellId, "Breaking Wave"\)\)\s+for \(Unit\* enemy : struck\)\s+'
                                    r'Effects::Taken\(enemy, spellId, Numbers::Num\(spellId, "damage_taken_pct"\)')
        # and they are applied on every swing: before the third-hit return.
        self.assertLess(self.code.index("Effects::Taken("), self.code.index("if (!IsThird(stage))"))

    def test_the_third_hit_carries_the_daze_and_tsunamis_freeze(self):
        after = self.code[self.code.index("if (!IsThird(stage))"):]
        self.assertIn("DazeMovement", after)
        self.assertIn("DazeAttacks", after)
        self.assertIn('IsRune(spellId, "Tsunami")', after)

    def test_the_wave_is_not_named_in_the_barbarians_file(self):
        self.assertNotIn("Crippling Wave", barbarian_source.abilities())


if __name__ == "__main__":
    unittest.main()
