"""The source-text guards of Crusader Bombardment: what the dispatch must call, how the spheres fall, and what each rune does at
an impact.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_bombardment.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_bombardment import CODE, MODULE  # noqa: E402

CRUSADER = MODULE / "src/classes/crusader"


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((CRUSADER / "dc_crusader.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_skill_its_seams(self):
        self.assertEqual(self.crusader.count("Bombardment::Ground(player, spellId, center);"), 1)
        self.assertIn("if (auto bombardment = Bombardment::BasePct(spellId)) return bombardment;", self.crusader)
        self.assertIn("Judgment::CritBonus(player, target) + Bombardment::CritBonus(spellId);", self.crusader)

    def test_the_cast_deals_no_hit_of_its_own(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("double CritBonus(")]
        self.assertIn("return 0.0;", base)

    def test_annihilate_adds_its_chance_from_the_sheet(self):
        crit = self.code[self.code.index("double CritBonus("):self.code.index("void Ground(")]
        self.assertIn('CritBonusPct(RuneAt(spellId), Numbers::Num(spellId, "crit_chance_pct"))', crit)

    def test_the_numbers_of_the_barrage_come_from_the_skill_and_the_big_ball_from_its_rune(self):
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn('Impacts(rune, unsigned(Numbers::Num(base, "spawn_count")))', ground)
        self.assertIn('PctEach(rune, Numbers::Num(base, "damage_pct"), Numbers::Num(spellId, "damage_pct"), plan->left)', ground)
        self.assertIn('ImpactRadius(rune, Numbers::Num(base, "radius_yards"), Numbers::Num(spellId, "radius_yards"))', ground)
        self.assertIn('Tune("bombardment_spawn_wait_seconds")', ground)
        self.assertIn('Tune("bombardment_first_delay_seconds")', ground)

    def test_targeted_picks_the_nearest_enemy_and_follows_it(self):
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn("center.GetExactDist(enemy) < center.GetExactDist(nearest)", ground)
        where = self.code[self.code.index("Position Where("):self.code.index("void Spawn(")]
        targeted = where[where.index("Rune::Targeted"):where.index("Rune::ImpactfulBombardment")]
        self.assertIn("ObjectAccessor::GetUnit(*player, plan.first)", targeted)
        self.assertIn("return plan.firstAt;", targeted)
        self.assertIn("if (plan.rune == Rune::ImpactfulBombardment) return plan.center;", where)
        self.assertIn("Pick(near.size(), Roll())", where)

    def test_a_sphere_leaves_falls_after_the_delay_and_the_next_waits(self):
        spawn = self.code[self.code.index("void Spawn("):self.code.index("bool Is(")]
        self.assertIn("if (!player->IsInWorld() || !player->IsAlive() || plan->left == 0) return;", spawn)
        self.assertIn('Millis(Tune("bombardment_impact_delay_seconds"))', spawn)
        self.assertIn("if (--plan->left > 0)", spawn)
        self.assertIn("Millis(Wait(plan->minWait, plan->extraWait, Roll()))", spawn)
        self.assertNotIn("Now()", spawn)

    def test_an_impact_strikes_the_area_adds_the_barrel_and_scatters_the_mines(self):
        impact = self.code[self.code.index("void Impact("):self.code.index("Position Where(")]
        self.assertIn("Combat::StrikeArea(player, plan->spellId, at, plan->radius, plan->pctEach)", impact)
        self.assertIn("if (plan->rune == Rune::BarrelsOfSpikes) Barrel(player, plan->spellId, enemy);", impact)
        self.assertIn("Combat::Connected(player, plan->spellId, unsigned(hit.size()));", impact)
        self.assertIn("if (plan->rune == Rune::MineField) Scatter(player, plan->spellId, at);", impact)
        barrel = self.code[self.code.index("void Barrel("):self.code.index("void Impact(")]
        self.assertIn('hit.skillName = "Thorns";', barrel)
        self.assertIn('BarrelBonus(Rune::BarrelsOfSpikes, (*sheet)[Stat::Thorns], Numbers::Num(spellId, "thorns_share_pct"))', barrel)
        self.assertIn("hit.crit = 1.0;", barrel)

    def test_a_mine_waits_for_an_enemy_goes_off_once_and_ends_with_its_time(self):
        mine = self.code[self.code.index("void Mine("):self.code.index("void Scatter(")]
        self.assertIn("Now() >= until", mine)
        self.assertIn("MineGoesOff(nearest, radius)", mine)
        self.assertIn('Combat::StrikeArea(player, spellId, at, radius, Numbers::Num(spellId, "damage_pct"))', mine)
        goes = mine[mine.index("if (MineGoesOff(nearest, radius))"):mine.index("player->m_Events.AddEventAtOffset")]
        self.assertIn("return;", goes)
        scatter = self.code[self.code.index("void Scatter("):self.code.index("void Barrel(")]
        self.assertIn('unsigned(Numbers::Num(spellId, "spawn_count"))', scatter)
        self.assertIn('Tune("bombardment_mine_seconds")', scatter)
        self.assertIn("MineDistance(Tune(\"bombardment_mine_min_yards\"), Tune(\"bombardment_mine_max_yards\"), Roll())", scatter)
        self.assertIn('std::max(MineCheckFloorSeconds, Tune("bombardment_mine_check_seconds"))', scatter)


if __name__ == "__main__":
    unittest.main()
