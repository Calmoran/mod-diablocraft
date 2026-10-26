"""The source-text guards of Crusader Falling Sword: what the dispatch must call, what each rune leaves at the landing, and
how the cooldown starts again.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_falling_sword.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_falling_sword import CODE, MODULE  # noqa: E402

CRUSADER = MODULE / "src/classes/crusader"


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((CRUSADER / "dc_crusader.cpp").read_text(encoding="utf-8"))
        self.phalanx = squeeze((CRUSADER / "dc_crusader_phalanx.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_skill_its_seams(self):
        self.assertEqual(self.crusader.count("FallingSword::Cast(player, spellId, targets);"), 1)
        self.assertEqual(self.crusader.count("FallingSword::Ground(player, spellId, center);"), 1)
        self.assertIn("if (auto sword = FallingSword::BasePct(spellId)) return sword;", self.crusader)

    def test_the_landing_hit_is_the_skills_own_number_for_every_rune(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn('Numbers::Own(BaseId(Skill), "damage_pct")', base)

    def test_the_cooldown_starts_again_whole_once_the_effects_are_over(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Ground(")]
        self.assertIn("SkillCooldownMilliseconds(player, spellId)", cast)
        self.assertIn('WaitSeconds(rune, Numbers::Num(spellId, "duration_seconds"))', cast)
        self.assertIn("CooldownSeconds(rune, whole, unsigned(targets.size())", cast)
        self.assertIn('Numbers::Num(spellId, "min_cooldown_seconds")', cast)
        self.assertEqual(cast.count("SendSkillCooldown(player, spellId, start);"), 2)
        self.assertIn("player->m_Events.AddEventAtOffset(", cast)
        self.assertIn("Millis(wait)", cast)

    def test_superheated_burns_the_ground_in_ticks_of_the_rate(self):
        ground = self.code[self.code.index("void Ground("):]
        burn = ground[ground.index("case Rune::Superheated:"):ground.index("case Rune::PartTheClouds:")]
        self.assertIn("Zone::Lay(player, spellId, center", burn)
        self.assertIn('Tune("falling_sword_superheated_radius_yards")', burn)
        self.assertIn('PctPerTick(Numbers::Num(spellId, "damage_pct"), seconds, tick)', burn)

    def test_part_the_clouds_strikes_one_random_enemy_a_strike_and_stuns_it(self):
        storm = self.code[self.code.index("void Storm("):self.code.index("bool Is(")]
        self.assertIn('Tune("falling_sword_part_the_clouds_radius_yards")', storm)
        self.assertIn("Pick(under.size(), rand_chance() / 100.0)", storm)
        self.assertIn('Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));', storm)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player)', storm)
        self.assertIn("if (!player->IsInWorld() || !player->IsAlive() || left == 0) return;", storm)
        self.assertIn("if (left > 1) player->m_Events.AddEventAtOffset", storm)
        self.assertNotIn("Now()", storm)
        ground = self.code[self.code.index("void Ground("):]
        clouds = ground[ground.index("case Rune::PartTheClouds:"):ground.index("case Rune::RiseBrothers:")]
        self.assertIn("Dot::Ticks(seconds, every)", clouds)
        self.assertIn('Tune("falling_sword_part_the_clouds_strike_seconds")', clouds)

    def test_rise_brothers_sends_phalanxs_fighters_with_its_own_numbers(self):
        ground = self.code[self.code.index("void Ground("):]
        brothers = ground[ground.index("case Rune::RiseBrothers:"):ground.index("case Rune::Flurry:")]
        self.assertIn('Phalanx::Fighters(player, spellId, unsigned(Numbers::Num(spellId, "pet_count")), seconds,', brothers)
        self.assertIn("player->GetPosition()", brothers)
        fighters = self.phalanx[self.phalanx.index("void Fighters("):self.phalanx.index("void RegisterScripts()")]
        self.assertIn("Behavior::Fight", fighters)
        self.assertIn("mind->Follow(i)", fighters)

    def test_flurry_stuns_the_enemies_in_it_and_strikes_them_each_tick(self):
        ground = self.code[self.code.index("void Ground("):]
        flurry = ground[ground.index("case Rune::Flurry:"):]
        self.assertIn('Tune("falling_sword_flurry_radius_yards")', flurry)
        self.assertIn("Stun(player, enemy, seconds * ItemPowers::StunFactor(player));", flurry)
        self.assertIn("Zone::Lay(player, spellId, center, radius,", flurry)
        self.assertIn('PctPerTick(Numbers::Num(spellId, "damage_pct"), seconds, tick)', flurry)

    def test_rapid_descent_adds_no_effect_at_the_landing(self):
        ground = self.code[self.code.index("void Ground("):]
        self.assertNotIn("RapidDescent", ground)


if __name__ == "__main__":
    unittest.main()
