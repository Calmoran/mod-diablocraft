"""The source-text guards of Crusader Fist of the Heavens: what the engine and the dispatch must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_fist_of_the_heavens.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_fist_of_the_heavens import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.resolve = squeeze((MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        self.zone = squeeze((MODULE / "src/classes/crusader/dc_crusader_zone.cpp").read_text(encoding="utf-8"))

    def test_the_engine_tells_the_crusader_where_the_cast_landed_after_the_hits(self):
        self.assertEqual(self.resolve.count("Crusader::Ground("), 1)
        self.assertIn("Monk::Ground(player, shell.spellId, center); Crusader::Ground(player, shell.spellId, center);", self.resolve)
        order = [self.resolve.index(m) for m in ("ResolveHit(player, target, punch.pct", "Crusader::Cast(player, shell.spellId, targets);",
                                                 "Crusader::Ground(player, shell.spellId, center);", "Connected(player, shell.spellId, connected);")]
        self.assertEqual(order, sorted(order))

    def test_the_dispatch_hands_the_fist_its_seams(self):
        self.assertEqual(self.crusader.count("FistOfTheHeavens::Ground(player, spellId, center);"), 1)
        self.assertIn("if (auto fist = FistOfTheHeavens::BasePct(spellId)) return fist;", self.crusader)
        self.assertLess(self.crusader.index("BlessedShield::BasePct(spellId)"), self.crusader.index("FistOfTheHeavens::BasePct(spellId)"))

    def test_the_bolts_need_a_width_and_leave_evenly_from_the_aim(self):
        bolts = self.code[self.code.index("std::vector<Unit*> Bolts("):self.code.index("void Zaps(")]
        self.assertIn("if (width <= 0) return struck;", bolts)
        self.assertIn("BoltHeading(index, count, first)", bolts)
        self.assertIn('unsigned(Numbers::Num(spellId, "projectile_count"))', bolts)
        self.assertIn('Numbers::Get(spellId, "damage_pct", "bolt")', bolts)
        ground = self.code[self.code.index("void Ground("):]
        self.assertIn("double const first = player->GetAngle(&center);", ground)

    def test_each_rune_does_its_one_thing(self):
        ground = self.code[self.code.index("void Ground("):]
        tempest = ground[ground.index("case Rune::HeavensTempest:"):ground.index("case Rune::Reverberation:")]
        self.assertIn('Zone::Lay(player, spellId, center, Numbers::Num(spellId, "radius_yards"), Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "duration_seconds"), Tune("fist_tempest_tick_seconds"));', tempest)
        reverb = ground[ground.index("case Rune::Reverberation:"):ground.index("case Rune::Fissure:")]
        self.assertIn("for (Unit* enemy : struck)", reverb)
        self.assertIn('Slow(player, enemy, Numbers::Num(spellId, "slow_pct"), Numbers::Num(spellId, "slow_duration_seconds"));', reverb)
        self.assertIn('Abilities::Knockback(player, enemy, Tune("fist_knockback_yards"));', reverb)
        self.assertIn("case Rune::Fissure: LayFissure(player, spellId, center);", ground)
        self.assertIn("case Rune::DivineWell: Zaps(player, spellId, center, first);", ground)
        retribution = ground[:ground.index("std::vector<Unit*> const struck")]
        self.assertIn("if (rune == Rune::Retribution)", retribution)
        self.assertIn('Numbers::Get(spellId, "damage_pct", "hit")', retribution)
        self.assertIn("if (width > 0)", retribution)

    def test_the_fissure_burns_as_a_zone_and_arcs_between_two_that_are_near(self):
        fissure = self.code[self.code.index("void LayFissure("):self.code.index("} // namespace\n") if "} // namespace\n" in self.code else self.code.index("bool Is(")]
        self.assertIn('Dot::TickPct(Numbers::Num(spellId, "damage_pct", "dot"), ticks)', fissure)
        self.assertIn('Tune("fist_fissure_radius_yards")', fissure)
        self.assertIn('Tune("fist_fissure_arc_yards")', fissure)
        self.assertIn("if (Tune(\"fist_bolt_width_yards\") <= 0) return;", fissure)
        arc = self.code[self.code.index("void ArcTick("):self.code.index("void LayFissure(")]
        self.assertIn('Numbers::Get(spellId, "damage_pct", "arc")', arc)
        self.assertIn("OnBolt(along, across, length, width)", arc)

    def test_the_zone_ticks_are_bound_by_the_ticks_left_and_not_the_clock(self):
        self.assertIn("if (!player->IsInWorld() || !player->IsAlive() || left == 0) return;", self.zone)
        self.assertNotIn("Now()", self.zone)
        self.assertIn("if (left > 1) player->m_Events.AddEventAtOffset", self.zone)


if __name__ == "__main__":
    unittest.main()
