"""The source-text guards of Crusader Condemn: what the dispatch and the damage path must call, and what each rune does.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_condemn.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_condemn import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def source(path):
    return squeeze((MODULE / path).read_text(encoding="utf-8"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = source("src/classes/crusader/dc_crusader.cpp")

    def test_the_dispatch_hands_condemn_its_seams(self):
        self.assertEqual(self.crusader.count("Condemn::Cast(player, spellId);"), 1)
        self.assertIn("if (auto condemn = Condemn::BasePct(spellId)) return condemn;", self.crusader)
        self.assertIn("Condemn::Taken(player, damage);", self.crusader)

    def test_the_damage_taken_seam_carries_the_damage_at_every_call(self):
        self.assertIn("void Taken(Unit* victim, Unit* attacker, double damage);", source("src/classes/crusader/dc_crusader.h"))
        self.assertIn("void Taken(Unit* victim, Unit* attacker, double damage)", self.crusader)
        hooks = source("src/combat/dc_combat_hooks.cpp")
        self.assertEqual(hooks.count("if(damage>0)Crusader::Taken(target,attacker,damage);"), 2)
        self.assertEqual(hooks.count("Crusader::Taken("), 2)
        combat = source("src/combat/dc_combat.cpp")
        self.assertEqual(combat.count("if(damage>0)Crusader::Taken(victim,attacker,damage);"), 1)
        self.assertEqual(combat.count("Crusader::Taken("), 1)

    def test_condemn_deals_no_damage_of_its_own_on_the_cast(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_cast_builds_then_explodes_and_unleashed_does_it_at_once(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Taken(")]
        self.assertIn('BuildSeconds(rune, Numbers::Num(spellId, "duration_seconds"))', cast)
        self.assertIn("if (seconds <= 0) { Explode(player, spellId, cast); return; }", cast)
        self.assertIn("Explode(player, spellId, cast); }, std::chrono::milliseconds(std::uint64_t(seconds * 1000.0)));", cast)

    def test_the_explosion_strikes_round_the_crusader_for_the_sheets_percentage_and_radius(self):
        explode = self.code[self.code.index("void Explode("):self.code.index("void Suck(")]
        self.assertIn("if (!player->IsInWorld() || !player->IsAlive()) return;", explode)
        self.assertIn('Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards"))', explode)
        self.assertIn('Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"))', explode)

    def test_reciprocate_counts_the_damage_taken_while_it_builds_and_adds_it_to_each_hit(self):
        explode = self.code[self.code.index("void Explode("):self.code.index("void Suck(")]
        self.assertIn('Reciprocated(rune, taken, Numbers::Num(spellId, "damage_share_pct"))', explode)
        self.assertIn("Added(player, spellId, enemy, extra);", explode)
        taken = self.code[self.code.index("void Taken("):]
        self.assertIn("Building(Now(), found->second.until)", taken)
        self.assertIn("found->second.taken += damage;", taken)
        explode_head = explode[:explode.index("if (!player->IsInWorld()")]
        self.assertIn("found->second.cast == cast", explode_head)
        self.assertIn("builds.erase(found);", explode_head)

    def test_eternal_retaliation_cuts_every_runes_shared_cooldown_by_the_enemies_hit(self):
        explode = self.code[self.code.index("void Explode("):self.code.index("void Suck(")]
        self.assertIn('Cut(player, CooldownCut(rune, hits, Numbers::Num(spellId, "cooldown_reduction_seconds")));', explode)
        cut = self.code[self.code.index("void Cut("):self.code.index("void Added(")]
        self.assertIn("player->GetSpellCooldownDelay(row.id)", cut)
        self.assertIn("player->ModifySpellCooldown(row.id, -static_cast<int32>(seconds * 1000.0));", cut)

    def test_vacuum_pulses_through_the_build_and_draws_the_nearest_beyond_the_explosion(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Taken(")]
        self.assertIn("if (rune == Rune::Vacuum)", cast)
        self.assertIn('Pulses(seconds, interval)', cast)
        suck = self.code[self.code.index("void Suck("):self.code.index("bool Is(")]
        self.assertIn('PullReach(radius, Tune("condemn_vacuum_radius_step_yards"), pulse)', suck)
        self.assertIn("SuckedIn(distance, radius, reach)", suck)
        self.assertIn('Nearest(distances, reach, std::size_t(Tune("condemn_vacuum_max_targets")))', suck)
        self.assertIn("Abilities::Pull(enemy, point);", suck)
        self.assertIn("if (pulse < pulses) player->m_Events.AddEventAtOffset", suck)


if __name__ == "__main__":
    unittest.main()
