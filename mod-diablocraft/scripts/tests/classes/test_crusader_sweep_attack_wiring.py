"""The source-text guards of Crusader Sweep Attack: what the dispatch and the code must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_sweep_attack.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_sweep_attack import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.movement = squeeze((MODULE / "src/combat/dc_movement_effects.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_sweep_its_seams(self):
        self.assertEqual(self.crusader.count("SweepAttack::Cast(player, spellId, targets);"), 1)
        self.assertIn("return sweep;", self.crusader)
        self.assertLess(self.crusader.index("ShieldBash::BasePct(spellId)"), self.crusader.index("SweepAttack::BasePct(spellId)"))

    def test_a_weapon_is_asked_for_by_the_skills_that_list_it(self):
        self.assertIn("if (player && row && RequiresWeapon(row->skill) && !SweepAttack::WeaponWorn(player)) return SPELL_FAILED_EQUIPPED_ITEM_CLASS_MAINHAND;",
                      self.crusader)
        self.assertIn("Class == ITEM_CLASS_WEAPON", self.code)
        self.assertIn("EQUIPMENT_SLOT_MAINHAND", self.code)

    def test_the_hit_is_the_skills_for_every_rune(self):
        self.assertIn('return Numbers::Get(BaseId(Skill), "damage_pct");', self.code)

    def test_the_half_circle_strikes_what_the_cone_did_not_take_and_counts_the_swing_once(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("player->HasInArc(arc, enemy)", cast)
        self.assertIn("std::find(targets.begin(), targets.end(), enemy) != targets.end()", cast)
        self.assertIn("if (targets.empty() && !hit.empty()) Combat::Connected(player, spellId, unsigned(hit.size()));", cast)
        self.assertLess(cast.index("Combat::Connected("), cast.index("switch (RuneAt(spellId))"))

    def test_each_rune_acts_on_the_enemies_the_sweep_hit(self):
        cast = self.code[self.code.index("switch (RuneAt(spellId))"):]
        self.assertIn('Abilities::PullToward(player, enemy, Tune("sweep_attack_pull_yards"))', cast)
        blazing = cast[cast.index("case Rune::BlazingSweep:"):cast.index("case Rune::HolyShock:")]
        self.assertIn('Dot::Burn(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "dot_duration_seconds"), Tune("sweep_attack_burn_tick_seconds"));', blazing)
        self.assertIn('Heal(player, spellId, HealFor(Classes::HealAtLevel(Numbers::Num(spellId, "heal_per_hit_life"), player->GetLevel()), unsigned(hit.size())));', cast)
        trip = cast[cast.index("case Rune::TripAttack:"):cast.index("case Rune::InspiringSweep:")]
        self.assertIn('roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct")))', trip)
        self.assertIn("StunFactor(player)", trip)
        self.assertIn("Stat::Armor, Bucket::Percent", cast)

    def test_the_pull_is_the_shared_movement_helper_at_the_same_speeds(self):
        self.assertIn("void PullToward(Player* p, Unit* u, double yards)", self.movement)
        self.assertIn("Pull(u, point);", self.movement)


if __name__ == "__main__":
    unittest.main()
