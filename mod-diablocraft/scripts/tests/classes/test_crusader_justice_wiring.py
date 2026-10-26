"""The source-text guards of Crusader Justice: what the engine and the dispatch must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_justice.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_justice import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.resolve = squeeze((MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))

    def test_both_places_a_hit_lands_tell_the_crusader_after_the_monk(self):
        self.assertEqual(self.resolve.count("Crusader::Landed("), 2)
        self.assertIn("Monk::Landed(player, target, shell.spellId); Crusader::Landed(player, target, shell.spellId);", self.resolve)
        self.assertIn("Monk::Landed(player, target, spellId); Crusader::Landed(player, target, spellId);", self.resolve)

    def test_the_dispatch_hands_justice_its_seams(self):
        self.assertEqual(self.crusader.count("Justice::Landed(player, target, spellId);"), 1)
        self.assertIn("return Justice::BasePct(spellId);", self.crusader)
        self.assertLess(self.crusader.index("Smite::BasePct(spellId)"), self.crusader.index("Justice::BasePct(spellId)"))

    def test_the_hit_is_the_skills_unless_the_rune_replaces_it(self):
        self.assertIn('HitPct(RuneOf(row->rune), Numbers::Num(BaseId(Skill), "damage_pct"), Numbers::Get(spellId, "damage_pct").value_or(0.0))',
                      self.code)

    def test_a_rune_s_follow_on_hits_never_start_it_again(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("if (answering || !player || !target || !Is(spellId)) return;", landed)
        self.assertEqual(landed.count("answering = true;"), 2)
        self.assertEqual(landed.count("answering = false;"), 2)

    def test_each_rune_does_its_one_thing(self):
        landed = self.code[self.code.index("void Landed("):]
        crack = landed[landed.index("case Rune::Crack:"):landed.index("case Rune::Burst:")]
        self.assertIn('roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct")))', crack)
        self.assertIn('Nearest(distances, radius, std::size_t(Numbers::Num(spellId, "spawn_count")))', crack)
        self.assertIn('Numbers::Own(spellId, "damage_pct")', crack)
        self.assertIn("if (enemy != target)", crack)
        burst = landed[landed.index("case Rune::Burst:"):landed.index("case Rune::HolyBolt:")]
        self.assertIn('Numbers::Num(spellId, "radius_yards")', burst)
        self.assertIn('double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);', burst)
        self.assertIn("Stun(player, enemy, stun)", burst)
        sword = landed[landed.index("case Rune::SwordOfJustice:"):landed.index("case Rune::Crack:")]
        self.assertIn("Stat::MovementSpeed, Bucket::Flat", sword)
        bolt = landed[landed.index("case Rune::HolyBolt:"):landed.index("default:")]
        self.assertIn("std::vector<Player*> healed{player};", bolt)
        # The bounds are the sheet's, scaled to the Crusader's level (test_level_heals.py), then one roll for each ally.
        self.assertIn("Classes::HealAtLevel(Numbers::Num(spellId, \"heal_min_life\"), player->GetLevel())", bolt)
        self.assertIn("Classes::HealAtLevel(Numbers::Num(spellId, \"heal_max_life\"), player->GetLevel())", bolt)
        self.assertIn("HealAmount(minLife, maxLife, rand_norm())", bolt)
        self.assertIn("player->IsWithinDistInMap(member, reach)", bolt)


if __name__ == "__main__":
    unittest.main()
