"""The source-text guards of Crusader Consecration: what the dispatch must call, and what each rune does.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_consecration.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_consecration import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.justice = squeeze((MODULE / "src/classes/crusader/dc_crusader_justice.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_ground_its_seams(self):
        self.assertEqual(self.crusader.count("Consecration::Cast(player, spellId);"), 1)
        self.assertIn("if (auto ground = Consecration::BasePct(spellId)) return ground;", self.crusader)
        self.assertLess(self.crusader.index("IronSkin::BasePct(spellId)"), self.crusader.index("Consecration::BasePct(spellId)"))

    def test_the_heal_and_the_fear_are_the_modules_one_each(self):
        self.assertEqual(self.crusader.count("void Heal(Player* caster, Unit* target, std::uint32_t spellId, double amount)"), 1)
        self.assertNotIn("void Heal(", self.justice)
        self.assertIn("constexpr std::uint32_t FearHold = 5782;", self.crusader)
        self.assertIn("bool Fear(Player* player, Unit* target, double seconds) { return Hold(player, target, FearHold, seconds); }", self.crusader)

    def test_the_ground_deals_no_damage_of_its_own_on_the_cast(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_ground_is_laid_where_the_crusader_stands_and_ticks_by_the_ticks_left(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("Position const center = player->GetPosition();", cast)
        self.assertIn('Numbers::Num(spellId, "duration_seconds")', cast)
        self.assertIn('Tune("consecration_tick_seconds")', cast)
        self.assertIn("Dot::Ticks(seconds, tick)", cast)
        tick = self.code[self.code.index("void Tick("):self.code.index("bool Is(")]
        self.assertIn("if (!player->IsInWorld() || left == 0) return;", tick)
        self.assertNotIn("Now()", tick)
        self.assertIn("if (left > 1) player->m_Events.AddEventAtOffset", tick)

    def test_the_heal_goes_to_the_crusader_and_the_group_standing_on_the_ground(self):
        tick = self.code[self.code.index("void Tick("):]
        self.assertIn('Numbers::Num(spellId, "heal_per_second_life")', tick)
        self.assertIn("std::vector<Player*> standing{player};", tick)
        self.assertIn("player->GetGroup()", tick)
        self.assertIn("OnGround(ally->GetExactDist(&center), radius)", tick)
        self.assertIn("Heal(player, ally, spellId, heal);", tick)

    def test_the_heal_reaches_only_a_member_on_the_crusaders_map(self):
        # t4kwd: a distance reads coordinates and never the map, so a member in another instance at the same x/y/z was
        # healed, from another map's thread. The condition that guards the heal names the map.
        tick = self.code[self.code.index("void Tick("):]
        guard = tick[tick.index("for (Player* ally : standing)"):tick.index("Heal(player, ally, spellId, heal);")]
        self.assertIn("ally->GetMap() == player->GetMap()", guard)
        self.assertIn("OnGround(ally->GetExactDist(&center), radius)", guard)

    def test_each_rune_does_its_one_thing(self):
        tick = self.code[self.code.index("void Tick("):]
        nails = tick[tick.index("case Rune::BedOfNails:"):tick.index("case Rune::ShatteredGround:")]
        self.assertIn("Nails(player, spellId, enemy);", nails)
        nail = self.code[self.code.index("void Nails("):self.code.index("void Tick(")]
        self.assertIn("ThornsShare((*sheet)[Stat::Thorns], Numbers::Num(spellId, \"thorns_share_pct\"))", nail)
        self.assertIn('hit.skillName = "Thorns";', nail)
        shattered = tick[tick.index("case Rune::ShatteredGround:"):tick.index("case Rune::Fearful:")]
        self.assertIn('Combat::Strike(player, enemy, spellId, Numbers::Own(spellId, "damage_pct"), true);', shattered)
        fearful = tick[tick.index("case Rune::Fearful:"):]
        self.assertIn('Procs(rand_chance(), Numbers::Num(spellId, "proc_chance_pct"))', fearful)
        self.assertIn('Fear(player, enemy, Numbers::Num(spellId, "fear_duration_seconds"));', fearful)

    def test_aegis_purgatory_looks_often_and_puts_a_crosser_back(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("if (RuneAt(spellId) == Rune::AegisPurgatory) Look(", cast)
        look = self.code[self.code.index("void Look("):self.code.index("void Nails(")]
        self.assertIn("Crossed(seen->second.inside, distance, radius)", look)
        self.assertIn("enemy->NearTeleportTo(", look)
        self.assertIn("Now() >= until", look)
        self.assertIn("CheckEvery()", look)
        self.assertIn("constexpr double CheckFloorSeconds = 0.1;", self.code)


if __name__ == "__main__":
    unittest.main()
