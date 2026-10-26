"""The source-text guards of monk mantra of retribution: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_mantra_of_retribution.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import monk_source
from test_monk_mantra_of_retribution import MODULE  # noqa: E402


class Wiring(unittest.TestCase):
    def setUp(self):
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.cast = monk_source.section("Retribution")

    def test_the_monk_hands_the_mantra_to_its_own_file(self):
        self.assertIn("return Retribution::Cast(player, spellId, targets);", self.monk)
        self.assertIn("Retribution::Taken(victim, attacker);", self.monk)
        self.assertIn("Retribution::Touch(player);", self.monk)

    def test_a_hit_taken_is_reported_at_the_three_places_and_not_the_periodic_one(self):
        lines = self.combat.splitlines()
        taken = [i for i, line in enumerate(lines) if "Passives::Taken(" in line]
        self.assertEqual(len(taken), 4)
        followed = [i for i in taken if "Monk::Taken(" in lines[i + 1]]
        self.assertEqual(followed, taken[:3])
        self.assertEqual(self.combat.count("Monk::Taken("), 3)

    def test_a_reflect_does_not_reflect(self):
        self.assertIn("if (reflecting ||", self.cast)
        self.assertIn("reflecting = true;", self.cast)
        self.assertIn("reflecting = false;", self.cast)

    def test_the_passive_follows_the_one_mantra_rule(self):
        self.assertIn("!Mantras::On(monk->GetGUID().GetRawValue(), base)", self.cast)
        self.assertIn("Mantras::Press(flavour, player, spellId, targets);", self.cast)
        self.assertTrue(monk_source.flavour("Retribution")["boosts"])

    def test_against_all_odds_waits_for_alex_s_chance(self):
        at = self.cast.index('DC::Tunables::Has("monk", "mantra_of_retribution_spirit_chance_pct")')
        self.assertLess(at, self.cast.index("Generate(monk,"))


if __name__ == "__main__":
    unittest.main()
