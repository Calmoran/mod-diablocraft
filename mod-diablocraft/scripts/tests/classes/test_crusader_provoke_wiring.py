"""The source-text guards of Crusader Provoke: what the dispatch must call, and what each rune does.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_provoke.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_provoke import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.common = squeeze((MODULE / "src/classes/crusader/dc_crusader_common.h").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_provoke_its_seams(self):
        self.assertEqual(self.crusader.count("Provoke::Cast(player, spellId, targets);"), 1)
        self.assertEqual(self.crusader.count("Provoke::Landed(player, target, spellId);"), 1)
        self.assertIn("if (auto provoke = Provoke::BasePct(spellId)) return provoke;", self.crusader)
        self.assertLess(self.crusader.index("Judgment::BasePct(spellId)"), self.crusader.index("Provoke::BasePct(spellId)"))

    def test_the_stock_auras_are_the_ones_the_tests_read_from_the_client(self):
        self.assertIn("constexpr std::uint32_t TauntHold = 1161;", self.crusader)
        self.assertIn("constexpr std::uint32_t WearyHold = 10371;", self.crusader)
        self.assertIn("bool Taunt(Player* player, Unit* target, double seconds) { return Hold(player, target, TauntHold, seconds); }", self.crusader)
        self.assertIn("Hold(player, target, WearyHold, seconds, -static_cast<int>(std::lround(pct)));", self.crusader)

    def test_a_hold_says_whether_it_took_hold(self):
        hold = self.crusader[self.crusader.index("bool Hold("):self.crusader.index("// The skills whose tooltip says \"Requires Shield\"")]
        self.assertIn("Aura* hold = player->AddAura(aura, target); if (!hold) return false;", hold)
        self.assertTrue(hold.rstrip().rstrip("}").rstrip().endswith("return true;"))
        self.assertIn("bool Fear(Player* player, Unit* target, double seconds)", self.common)
        self.assertIn("bool Taunt(Player* player, Unit* target, double seconds)", self.common)

    def test_provoke_deals_no_damage_of_its_own(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_enemies_are_taunted_or_frightened_and_the_count_pays_the_wrath(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn('Numbers::Num(BaseId(Skill), "duration_seconds")', cast)
        self.assertIn('(Frightens(rune) ? Fear(player, enemy, Numbers::Num(spellId, "fear_duration_seconds")) : Taunt(player, enemy, taunt))', cast)
        self.assertIn("held.push_back(enemy);", cast)
        self.assertIn('PayWrath(player, spellId, WrathFor(Numbers::Num(spellId, "generated_resource", "base"), Numbers::Num(spellId, "generated_resource", "per_enemy"), unsigned(held.size())));', cast)
        self.assertLess(cast.index("held.push_back(enemy);"), cast.index("PayWrath("))
        # One place multiplies the generation by the item power's factor: the primaries' and Provoke's Wrath both go through it.
        self.assertIn("void PayWrath(Player* player, std::uint32_t spellId, double points)", self.crusader)
        self.assertIn('if (auto const points = Numbers::Get(spellId, "generated_resource")) PayWrath(player, spellId, *points);', self.crusader)
        self.assertEqual(self.crusader.count("resource_generation_pct"), 1)

    def test_each_rune_does_its_one_thing_to_the_enemies_it_took_hold_of(self):
        cast = self.code[self.code.index("switch (rune)"):self.code.index("void Landed(")]
        cleanse = cast[cast.index("case Rune::Cleanse:"):cast.index("case Rune::TooScaredToRun:")]
        self.assertIn("Stat::LifePerHit", cleanse)
        self.assertIn("CleanseStacks(rune, unsigned(held.size()))", cleanse)
        self.assertIn('Numbers::Num(spellId, "heal_per_hit_life")', cleanse)
        scared = cast[cast.index("case Rune::TooScaredToRun:"):cast.index("case Rune::ChargedUp:")]
        self.assertIn("for (Unit* enemy : held)", scared)
        self.assertIn('Slow(player, enemy, Numbers::Num(spellId, "slow_pct")', scared)
        self.assertIn('Weary(player, enemy, Numbers::Num(spellId, "attack_speed_pct")', scared)
        charged = cast[cast.index("case Rune::ChargedUp:"):cast.index("case Rune::HitMe:")]
        self.assertIn('Numbers::Num(spellId, "duration_seconds") * 1000.0', charged)
        self.assertIn("charged[player->GetGUID().GetRawValue()] = {spellId, until};", charged)
        hit_me = cast[cast.index("case Rune::HitMe:"):]
        self.assertIn("Stat::BlockChance", hit_me)
        self.assertIn('Numbers::Num(spellId, "block_pct")', hit_me)

    def test_charged_ups_rider_is_a_strike_of_the_runes_own_lightning_shell(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("RiderPct(RuneAt(rider), true, Is(spellId), Numbers::Own(rider, \"damage_pct\").value_or(0.0))", landed)
        self.assertIn("Combat::Strike(player, target, rider, pct);", landed)
        self.assertIn("if (!Charged(Now(), found->second.until))", landed)


if __name__ == "__main__":
    unittest.main()
