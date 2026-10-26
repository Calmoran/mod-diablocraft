"""The source-text guards of Crusader Judgment: what the engine and the dispatch must call, and what each rune does.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_judgment.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_judgment import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.combat = squeeze((MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_judgment_its_seams(self):
        self.assertEqual(self.crusader.count("Judgment::Ground(player, spellId, center);"), 1)
        self.assertIn("if (auto judgment = Judgment::BasePct(spellId)) return judgment;", self.crusader)
        self.assertLess(self.crusader.index("Consecration::BasePct(spellId)"), self.crusader.index("Judgment::BasePct(spellId)"))

    def test_the_crit_seam_knows_the_target(self):
        self.assertEqual(self.combat.count("Crusader::CritBonus(player, target, shell.spellId)"), 1)
        self.assertIn("double CritBonus(Player* player, Unit* target, std::uint32_t spellId)", self.crusader)
        self.assertIn("Judgment::CritBonus(player, target)", self.crusader)

    def test_judgment_deals_no_damage(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Ground(")]
        self.assertIn("return 0.0;", base)

    def test_every_enemy_in_the_area_is_held_for_the_immobilize_and_marked(self):
        ground = self.code[self.code.index("void Ground("):self.code.index("double CritBonus(")]
        self.assertIn('Combat::Enemies(player, spellId, center, Numbers::Num(spellId, "radius_yards"))', ground)
        self.assertIn('double const seconds = Numbers::Num(spellId, "immobilize_duration_seconds");', ground)
        self.assertIn("Root(player, enemy, seconds);", ground)
        self.assertIn("judged[{player->GetGUID().GetRawValue(), enemy->GetGUID().GetRawValue()}] = until;", ground)

    def test_each_rune_does_its_one_thing(self):
        ground = self.code[self.code.index("void Ground("):self.code.index("double CritBonus(")]
        mass = ground[ground.index("if (rune == Rune::MassVerdict)"):ground.index("// \"Immobilizing")]
        self.assertIn("enemy->NearTeleportTo(center.GetPositionX(), center.GetPositionY(), z, enemy->GetOrientation());", mass)
        self.assertLess(ground.index("if (rune == Rune::MassVerdict)"), ground.index("Root(player, enemy, seconds);"))
        penitence = ground[ground.index("case Rune::Penitence:"):ground.index("case Rune::Debilitate:")]
        self.assertIn('HealPerTick(Classes::HealAtLevel(Numbers::Num(spellId, "heal_per_second_life"), player->GetLevel()), unsigned(enemies.size()))', penitence)
        self.assertIn('Tune("judgment_penitence_tick_seconds")', penitence)
        self.assertIn('Dot::Ticks(Numbers::Num(spellId, "duration_seconds"), tick)', penitence)
        debilitate = ground[ground.index("case Rune::Debilitate:"):]
        self.assertIn('EnemyEffects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"), Numbers::Num(spellId, "duration_seconds"));', debilitate)

    def test_resolved_reads_the_mark_of_this_crusaders_judged_enemy(self):
        crit = self.code[self.code.index("double CritBonus("):]
        self.assertIn("if (RuneAt(spellId) != Rune::Resolved) return 0.0;", crit)
        self.assertIn("judged.find({player->GetGUID().GetRawValue(), target->GetGUID().GetRawValue()})", crit)
        self.assertIn('CritFor(Rune::Resolved, onJudged, Numbers::Num(spellId, "crit_chance_pct"))', crit)

    def test_penitences_heal_is_bound_by_the_ticks_left_and_not_the_clock(self):
        mend = self.code[self.code.index("void Mend("):self.code.index("bool Is(")]
        self.assertIn("if (!player->IsInWorld() || left == 0) return;", mend)
        self.assertNotIn("Now()", mend)
        self.assertIn("if (left > 1) player->m_Events.AddEventAtOffset", mend)


if __name__ == "__main__":
    unittest.main()
