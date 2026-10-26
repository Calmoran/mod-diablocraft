"""The source-text guards of Crusader Blessed Hammer: what the dispatch and the code must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_blessed_hammer.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_blessed_hammer import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_hammer_its_seams(self):
        self.assertEqual(self.crusader.count("BlessedHammer::Cast(player, spellId, targets);"), 1)
        self.assertIn("if (auto hammer = BlessedHammer::BasePct(spellId)) return hammer;", self.crusader)
        self.assertLess(self.crusader.index("SweepAttack::BasePct(spellId)"), self.crusader.index("BlessedHammer::BasePct(spellId)"))

    def test_the_cast_starts_a_hammer_from_the_tunables_and_needs_a_hit_radius(self):
        cast = self.code[self.code.index("void Cast("):]
        for read in ('Tune("blessed_hammer_reach_yards")', 'Tune("blessed_hammer_seconds")', 'Tune("blessed_hammer_loops")',
                     'Tune("blessed_hammer_hit_radius_yards")', 'Tune("blessed_hammer_step_seconds")',
                     'Tune("blessed_hammer_limitless_life_factor")'):
            self.assertIn(read, cast)
        self.assertIn("hammer->heading = player->GetOrientation();", cast)
        self.assertIn("if (hammer->hitRadius <= 0 || !hammer->steps) return;", cast)
        self.assertIn("Reach(hammer->rune, Tune(\"blessed_hammer_reach_yards\"), hammer->rune == Rune::Limitless ? Numbers::Num(spellId, \"radius_yards\") : 0.0);", cast)

    def test_each_look_moves_the_hammer_hits_the_enemies_it_reaches_and_keeps_the_next_look(self):
        look = self.code[self.code.index("void Look("):self.code.index("} // namespace\n") if "} // namespace\n" in self.code else self.code.index("bool Is(")]
        self.assertIn("hammer->rune == Rune::Dominion ? player->GetPosition() : hammer->center", look)
        self.assertIn("Orbit(hammer->done * hammer->step, hammer->lifetime, hammer->reach, hammer->loops, hammer->heading)", look)
        self.assertIn("if (Enters(hammer->touching.count(raw) != 0, true)) Hit(player, *hammer, enemy);", look)
        self.assertIn("hammer->touching = std::move(now);", look)
        self.assertIn('hammer->rune == Rune::Thunderstruck && roll_chance_f(float(Tune("blessed_hammer_arc_chance_pct")))', look)
        self.assertIn("if (hammer->done < hammer->steps) player->m_Events.AddEventAtOffset", look)

    def test_a_hit_pays_the_skill_once_and_acts_by_rune(self):
        hit = self.code[self.code.index("void Hit("):self.code.index("void Arc(")]
        self.assertIn("if (!Combat::Strike(player, enemy, spellId, hammer.pct)) return;", hit)
        self.assertIn("if (!hammer.connected) { hammer.connected = true; Combat::Connected(player, spellId, 1); }", hit)
        burning = hit[hit.index("case Rune::BurningWrath:"):hit.index("case Rune::BruteForce:")]
        self.assertIn('roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct")))', burning)
        self.assertIn("LayPool(player, spellId, enemy);", burning)
        brute = hit[hit.index("case Rune::BruteForce:"):]
        self.assertIn('Slow(player, enemy, Tune("blessed_hammer_slow_pct"), Tune("blessed_hammer_slow_seconds"));', brute)
        self.assertIn('Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);', brute)
        self.assertIn("Stun(player, near, stun);", brute)

    def test_thunderstruck_arcs_along_the_segment_from_the_crusader_to_the_hammer(self):
        arc = self.code[self.code.index("void Arc("):self.code.index("void Look(")]
        self.assertIn('auto const pct = Numbers::Own(hammer.spellId, "damage_pct");', arc)
        self.assertIn("SegmentDistance(", arc)
        self.assertIn("hammer.hitRadius", arc)

    def test_burning_wrath_lays_pools_with_a_cap_and_a_lock(self):
        lay = self.code[self.code.index("void LayPool("):self.code.index("struct Hammer")]
        self.assertIn('PoolRoom(mine.size(), std::size_t(Tune("blessed_hammer_pools_at_once")))', lay)
        self.assertIn("Position const where = enemy->GetPosition();", lay)
        self.assertLess(lay.index("mine.push_back(until);"), lay.index("AddEventAtOffset"))
        tick = self.code[self.code.index("void PoolTick("):self.code.index("void LayPool(")]
        self.assertIn("Combat::Strike(player, enemy, spellId, pct, true);", tick)
        self.assertIn('Tune("blessed_hammer_pool_radius_yards")', tick)


if __name__ == "__main__":
    unittest.main()
