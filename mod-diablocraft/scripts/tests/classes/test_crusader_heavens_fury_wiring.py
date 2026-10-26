"""The source-text guards of Crusader Heaven's Fury: what the dispatch must call, how each rune's ground is laid, and the
hold of a place.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_heavens_fury.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_heavens_fury import CODE, MODULE  # noqa: E402

CRUSADER = MODULE / "src/classes/crusader"


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((CRUSADER / "dc_crusader.cpp").read_text(encoding="utf-8"))
        self.hold = squeeze((CRUSADER / "dc_crusader_hold.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_skill_its_seams(self):
        self.assertEqual(self.crusader.count("HeavensFury::Ground(player, spellId, center);"), 1)
        self.assertIn("if (auto fury = HeavensFury::BasePct(spellId)) return fury;", self.crusader)

    def test_the_cast_deals_no_hit_of_its_own(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Ground(")]
        self.assertIn("return 0.0;", base)

    def test_a_ray_is_a_zone_of_ticks_paying_the_whole_total(self):
        ray = self.code[self.code.index("void Ray("):self.code.index("double Footprint(")]
        self.assertIn('Tune("heavens_fury_tick_seconds")', ray)
        self.assertIn("Zone::Lay(player, spellId, where, radius, PctPerTick(totalPct, seconds, tick), seconds, tick);", ray)

    def test_the_skills_ray_uses_the_skills_own_numbers_for_the_runes_that_keep_it(self):
        ground = self.code[self.code.index("void Ground("):]
        keep = ground[ground.index("if (KeepsBaseRay(rune))"):ground.index("switch (rune)")]
        self.assertIn("Ray(player, spellId, center, Footprint(base), Numbers::Num(base, \"damage_pct\"),", keep)
        self.assertIn('Numbers::Num(base, "dot_duration_seconds")', keep)

    def test_each_rune_lays_its_own(self):
        ground = self.code[self.code.index("void Ground("):]
        ascendancy = ground[ground.index("case Rune::Ascendancy:"):ground.index("case Rune::BlessedGround:")]
        self.assertIn('Ray(player, spellId, center, footprint, Numbers::Num(spellId, "damage_pct"),', ascendancy)
        blessed = ground[ground.index("case Rune::BlessedGround:"):ground.index("case Rune::SplitFury:")]
        self.assertIn('Ray(player, spellId, center, footprint, Numbers::Num(spellId, "damage_pct"),', blessed)
        split = ground[ground.index("case Rune::SplitFury:"):ground.index("case Rune::ThouShaltNotPass:")]
        self.assertIn('unsigned(Numbers::Num(spellId, "spawn_count"))', split)
        self.assertIn('Tune("heavens_fury_split_beam_radius_yards")', split)
        self.assertIn("RingYards(footprint, beam)", split)
        self.assertIn("BeamHeading(i, count, start)", split)
        pas = ground[ground.index("case Rune::ThouShaltNotPass:"):ground.index("case Rune::FiresOfHeaven:")]
        self.assertIn('Hold::Place(player, spellId, center, footprint, Numbers::Num(spellId, "duration_seconds"),', pas)
        self.assertIn('Tune("heavens_fury_barrier_check_seconds")', pas)
        self.assertIn("case Rune::FiresOfHeaven: Beam(player, spellId, center);", ground)

    def test_ascendancys_area_is_its_own_and_the_others_the_casts(self):
        footprint = self.code[self.code.index("double Footprint("):self.code.index("void Beam(")]
        self.assertIn('Numbers::Own(spellId, "radius_yards").value_or(Combat::TargetRadius(spellId))', footprint)

    def test_the_beam_strikes_the_enemies_in_the_strip_and_counts_the_cast_once(self):
        beam = self.code[self.code.index("void Beam("):self.code.index("bool Is(")]
        self.assertIn('Tune("heavens_fury_fires_distance_yards")', beam)
        self.assertIn('Tune("heavens_fury_fires_radius_yards")', beam)
        self.assertIn("InBeam(Along(dx, dy, heading), Across(dx, dy, heading), distance, radius)", beam)
        self.assertIn('Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"))', beam)
        self.assertIn("if (hits) Combat::Connected(player, spellId, hits);", beam)

    def test_the_hold_puts_a_crosser_back_and_looks_by_the_floor(self):
        look = self.hold[self.hold.index("void Look("):self.hold.index("} // namespace")]
        self.assertIn("Consecration::Crossed(found->second.inside, distance, radius)", look)
        self.assertIn("enemy->NearTeleportTo(found->second.good.GetPositionX()", look)
        self.assertIn("if (!player->IsInWorld() || Now() >= until) return;", look)
        hold = self.hold[self.hold.index("void Place("):]
        self.assertIn("std::max(CheckFloorSeconds, checkSeconds)", hold)
        self.assertIn("if (!player || radius <= 0 || seconds <= 0) return;", hold)


if __name__ == "__main__":
    unittest.main()
