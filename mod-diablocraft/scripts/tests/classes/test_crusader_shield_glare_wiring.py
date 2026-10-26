"""The source-text guards of Crusader Shield Glare: what the dispatch must call, and what each rune does.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_shield_glare.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_shield_glare import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_glare_its_seams(self):
        self.assertEqual(self.crusader.count("ShieldGlare::Cast(player, spellId, targets);"), 1)
        self.assertIn("if (auto glare = ShieldGlare::BasePct(spellId)) return glare;", self.crusader)
        self.assertLess(self.crusader.index("FistOfTheHeavens::BasePct(spellId)"), self.crusader.index("ShieldGlare::BasePct(spellId)"))

    def test_the_glare_needs_a_shield_and_deals_no_damage_of_its_own(self):
        self.assertRegex(self.crusader, r'NeedShield = \{[^}]*"Shield Glare"')
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_blind_reaches_the_arc_and_every_blinded_enemy(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('Tune("shield_glare_arc_degrees")', cast)
        self.assertIn("Combat::Enemies(player, spellId, player->GetPosition(), reach)", cast)
        self.assertIn("player->HasInArc(arc, enemy)", cast)
        self.assertIn('Blind(player, enemy, Numbers::Num(spellId, "blind_duration_seconds"));', cast)
        self.assertLess(cast.index("Blind(player, enemy"), cast.index("switch (RuneAt(spellId))"))

    def test_each_rune_does_its_one_thing_to_the_blinded(self):
        cast = self.code[self.code.index("switch (RuneAt(spellId))"):]
        verdict = cast[cast.index("case Rune::DivineVerdict:"):cast.index("case Rune::EmblazonedShield:")]
        self.assertIn('EnemyEffects::Taken(enemy, spellId, Numbers::Num(spellId, "damage_taken_pct"), Numbers::Num(spellId, "duration_seconds"));', verdict)
        emblazoned = cast[cast.index("case Rune::EmblazonedShield:"):cast.index("case Rune::ZealousGlare:")]
        self.assertIn('Low(enemy->GetHealthPct(), Numbers::Num(spellId, "life_threshold_pct"))', emblazoned)
        self.assertIn('roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct")))', emblazoned)
        self.assertIn('Numbers::Num(spellId, "radius_yards")', emblazoned)
        self.assertIn('Combat::Strike(player, near, spellId, Numbers::Own(spellId, "damage_pct"));', emblazoned)
        zealous = cast[cast.index("case Rune::ZealousGlare:"):cast.index("case Rune::Subdue:")]
        self.assertIn('GainWrath(player, spellId, WrathFor(Numbers::Num(spellId, "gain_resource"), unsigned(blinded.size())));', zealous)
        subdue = cast[cast.index("case Rune::Subdue:"):]
        self.assertIn('Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "slow_duration_seconds"));', subdue)

    def test_uncertainty_charms_through_the_shared_charm_and_takes_the_blind_off(self):
        cast = self.code[self.code.index("switch (RuneAt(spellId))"):]
        uncertainty = cast[cast.index("case Rune::Uncertainty:"):cast.index("case Rune::EmblazonedShield:")]
        self.assertIn('CharmEffect::Rolls(rand_chance(), Numbers::Num(spellId, "proc_chance_pct"))', uncertainty)
        self.assertIn('CharmEffect::Apply(player, enemy, spellId, Numbers::Num(spellId, "charm_duration_seconds"))', uncertainty)
        self.assertIn("Unblind(player, enemy);", uncertainty)
        # every enemy the roll takes is charmed: one call for each, with no limit and no early exit, and each charm has a
        # holder of its own in CharmEffect::Apply (test_charm_effect), so none frees another
        self.assertIn("for (Unit* enemy : blinded)", uncertainty)
        self.assertEqual(uncertainty.count("break;"), 1)  # the case's own
        self.assertNotIn("return", uncertainty)
        self.assertNotIn("charmed >", uncertainty)
        # the charm comes after the blind, so the blind it takes off is the one just put
        self.assertLess(self.code.index("Blind(player, enemy"), self.code.index("case Rune::Uncertainty:"))
        self.assertIn("void Unblind(Player* player, Unit* target)", self.crusader)


if __name__ == "__main__":
    unittest.main()
