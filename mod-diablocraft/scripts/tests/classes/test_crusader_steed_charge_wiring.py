"""The source-text guards of Crusader Steed Charge: what the dispatch must call, and what each rune does in the ride.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_steed_charge.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_steed_charge import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_ride_its_seams(self):
        self.assertEqual(self.crusader.count("SteedCharge::Cast(player, spellId);"), 1)
        self.assertIn("if (auto steed = SteedCharge::BasePct(spellId)) return steed;", self.crusader)

    def test_the_ride_deals_no_damage_of_its_own_on_the_cast(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_cast_mounts_speeds_and_ticks_by_the_ticks_left(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('Numbers::Num(spellId, "duration_seconds")', cast)
        self.assertIn("Mount(player, seconds);", cast)
        self.assertIn("Buffs::Stack(player, spellId, Stat::MovementSpeed, Bucket::Uncapped,", cast)
        self.assertIn('SpeedPct(Tune("steed_charge_movement_speed_bonus"))', cast)
        self.assertIn("Dot::Ticks(seconds, tick)", cast)
        self.assertIn("ride->ticks = ticks;", cast)
        self.assertIn("Dismount(player);", cast)
        tick = self.code[self.code.index("void Tick("):self.code.index("void Dismount(")]
        self.assertIn("if (!player->IsInWorld() || !player->IsAlive() || left == 0) return;", tick)
        self.assertNotIn("Now()", tick)
        self.assertIn("if (left > 1) player->m_Events.AddEventAtOffset", tick)

    def test_each_rune_does_its_one_thing_in_a_tick(self):
        tick = self.code[self.code.index("void Tick("):self.code.index("void Dismount(")]
        barding = tick[tick.index("case Rune::SpikedBarding:"):tick.index("case Rune::Rejuvenation:")]
        self.assertIn('Combat::Enemies(player, spellId, here, Tune("steed_charge_spiked_barding_radius_yards"))', barding)
        self.assertIn('PerTick(Numbers::Num(spellId, "thorns_share_pct"), tick)', barding)
        rejuvenation = tick[tick.index("case Rune::Rejuvenation:"):tick.index("case Rune::Nightmare:")]
        self.assertIn('HealPerTick(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), ride->ticks)', rejuvenation)
        self.assertIn("Heal(player, player, spellId,", rejuvenation)
        nightmare = tick[tick.index("case Rune::Nightmare:"):tick.index("case Rune::DrawAndQuarter:")]
        self.assertIn("DropsPool(ride->lastPool.has_value(),", nightmare)
        self.assertIn('Tune("steed_charge_nightmare_pool_spacing_yards")', nightmare)
        self.assertIn("ride->lastPool = here;", nightmare)
        self.assertIn("case Rune::DrawAndQuarter: Drag(player, spellId, *ride, tick);", tick)

    def test_spiked_barding_deals_thorns_as_thorns_is_dealt(self):
        barding = self.code[self.code.index("void Barding("):self.code.index("void Pool(")]
        self.assertIn('hit.skillName = "Thorns";', barding)
        self.assertIn("Consecration::ThornsShare((*sheet)[Stat::Thorns], sharePct)", barding)
        self.assertIn("hit.crit = 1.0;", barding)
        self.assertIn("Combat::DealHit(player, enemy, spellId, hit);", barding)

    def test_nightmare_lays_a_zone_of_its_own_numbers(self):
        pool = self.code[self.code.index("void Pool("):self.code.index("void Drag(")]
        self.assertIn("Zone::Lay(player, spellId, where,", pool)
        self.assertIn('Tune("steed_charge_nightmare_pool_radius_yards")', pool)
        self.assertIn('PerTick(Numbers::Num(spellId, "damage_pct"), tick)', pool)
        self.assertIn('Tune("steed_charge_nightmare_pool_seconds")', pool)

    def test_draw_and_quarter_binds_the_nearest_at_the_cast_and_draws_by_the_header_rule(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('Nearest(distances, radius, std::size_t(Numbers::Num(spellId, "target_count")))', cast)
        self.assertIn('Tune("steed_charge_draw_radius_yards")', cast)
        drag = self.code[self.code.index("void Drag("):self.code.index("void Tick(")]
        self.assertIn("Dragged(distance, keep)", drag)
        self.assertIn("DragFraction(distance, keep)", drag)
        self.assertIn("Abilities::Pull(enemy, point);", drag)
        self.assertIn("Combat::Strike(player, enemy, spellId, pct, true);", drag)


if __name__ == "__main__":
    unittest.main()
