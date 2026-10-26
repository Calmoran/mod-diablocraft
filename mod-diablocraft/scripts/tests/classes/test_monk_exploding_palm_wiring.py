"""The source-text guards of monk exploding palm: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_exploding_palm.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_exploding_palm import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.cast = (MODULE / "src/classes/monk/dc_monk_exploding_palm.cpp").read_text(encoding="utf-8")

    def test_the_monk_hands_exploding_palm_to_its_own_file(self):
        self.assertIn("return ExplodingPalm::BasePct(spellId);", self.monk)
        self.assertIn("return ExplodingPalm::Cast(player, spellId, targets);", self.monk)
        self.assertIn("ExplodingPalm::RegisterScripts();", self.monk)

    def test_the_death_script_is_registered_beside_the_wizards(self):
        self.assertIn("Wizard::RegisterScripts();\n        Monk::RegisterScripts();", self.combat)
        self.assertIn("UNITHOOK_ON_UNIT_DEATH", self.cast)

    def test_the_cast_deals_nothing_itself(self):
        self.assertIn("return 0.0;", self.cast)

    def test_the_explosion_is_a_burn_for_essence_burn_and_a_hit_for_the_rest(self):
        explode = self.cast[self.cast.index("void Explode("):]
        self.assertLess(explode.index('"Essence Burn"'), explode.index("StrikeArea("))
        self.assertIn('"Impending Doom"', explode)
        self.assertIn('"Strong Spirit"', explode)


if __name__ == "__main__":
    unittest.main()
