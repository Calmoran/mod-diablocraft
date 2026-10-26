"""The source-text guards of Crusader Blessed Shield: what the dispatch and the code must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_blessed_shield.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_blessed_shield import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_shield_its_seams(self):
        self.assertEqual(self.crusader.count("BlessedShield::Landed(player, target, spellId);"), 1)
        self.assertIn("if (auto shield = BlessedShield::BasePct(spellId)) return shield;", self.crusader)
        self.assertLess(self.crusader.index("BlessedHammer::BasePct(spellId)"), self.crusader.index("BlessedShield::BasePct(spellId)"))
        self.assertIn('"Blessed Shield"', self.crusader)  # in the skills that need a shield

    def test_the_ricochet_and_the_pierce_are_exclusive_and_come_before_the_rune(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("if (rune == Rune::PiercingShield) Pierce(player, spellId, target, hit); else Ricochet(player, spellId, target, hit);", landed)
        self.assertLess(landed.index("Ricochet(player, spellId, target, hit);"), landed.index("switch (rune)"))
        self.assertIn("if (answering || !player || !target || !Is(spellId)) return;", landed)
        self.assertEqual(landed.count("answering = true;"), 1)
        self.assertEqual(landed.count("answering = false;"), 1)

    def test_the_ricochet_goes_from_each_enemy_hit_to_the_nearest_not_yet_hit(self):
        ricochet = self.code[self.code.index("void Ricochet("):self.code.index("void Pierce(")]
        self.assertIn('unsigned(Numbers::Num(spellId, "target_count"))', ricochet)
        self.assertIn("last->GetExactDist(enemy)", ricochet)
        self.assertIn("NextBounce(distances, struck, radius)", ricochet)
        self.assertIn("last = around[std::size_t(next)];", ricochet)

    def test_each_rune_acts_on_every_enemy_the_shield_hit(self):
        landed = self.code[self.code.index("switch (rune)"):]
        stagger = landed[landed.index("case Rune::StaggeringShield:"):landed.index("case Rune::Combust:")]
        self.assertIn("double const stun = Numbers::Num(spellId, \"stun_duration_seconds\") * ItemPowers::StunFactor(player);", stagger)
        self.assertIn("StunChance(base, reduction, place)", stagger)
        combust = landed[landed.index("case Rune::Combust:"):landed.index("case Rune::DivineAegis:")]
        self.assertIn("BlockShare::OwnStrikes scope;", combust)
        self.assertIn("for (Unit* enemy : hit)", combust)
        aegis = landed[landed.index("case Rune::DivineAegis:"):landed.index("case Rune::ShatteringThrow:")]
        self.assertIn("Stat::Armor, Bucket::Percent", aegis)
        self.assertIn("Stat::LifeRegen, Bucket::Percent", aegis)
        shatter = landed[landed.index("case Rune::ShatteringThrow:"):landed.index("case Rune::PiercingShield:")]
        self.assertIn("BlockShare::OwnStrikes scope;", shatter)
        self.assertIn('Nearest(distances, radius, std::size_t(Numbers::Num(spellId, "spawn_count")))', shatter)
        pierce = landed[landed.index("case Rune::PiercingShield:"):]
        self.assertIn('Abilities::Knockback(player, enemy, Tune("blessed_shield_knockaside_yards"));', pierce)

    def test_the_pierce_asks_for_a_width(self):
        pierce = self.code[self.code.index("void Pierce("):self.code.index("bool Is(")]
        self.assertIn("if (width <= 0) return;", pierce)
        self.assertIn("OnLine(along, across, length, width)", pierce)


if __name__ == "__main__":
    unittest.main()
