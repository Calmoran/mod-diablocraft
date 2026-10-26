"""The source-text guards of Crusader Smite: what the dispatch and the code must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_smite.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_smite import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_smite_its_seams(self):
        self.assertEqual(self.crusader.count("Smite::Cast(player, spellId, targets);"), 1)
        self.assertIn("if (auto smite = Smite::BasePct(spellId)) return smite;", self.crusader)
        # Punish answers its own spells first; Smite's hit is asked only of the rest.
        self.assertLess(self.crusader.index("Punish::BasePct(spellId)"), self.crusader.index("Smite::BasePct(spellId)"))

    def test_the_hit_is_the_skills_hit_for_every_rune(self):
        self.assertIn('return Numbers::Get(BaseId(Skill), "damage_pct", "hit");', self.code)

    def test_the_chains_strike_the_nearest_enemies_for_the_chain_damage(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn('Numbers::Num(spellId, "radius_yards", "chain")', cast)
        self.assertIn('auto const chain = Numbers::Get(spellId, "damage_pct", "chain");', cast)
        self.assertIn('Chained(distances, radius, std::size_t(Numbers::Num(spellId, "target_count")))', cast)
        self.assertIn("if (Combat::Strike(player, candidates[index], spellId, chain)) hit.push_back(candidates[index]);", cast)
        # The rune acts on the enemies the chains did strike, after them.
        self.assertLess(cast.index("hit.push_back("), cast.index("switch (RuneAt(spellId))"))

    def test_each_rune_does_its_one_thing(self):
        cast = self.code[self.code.index("switch (RuneAt(spellId))"):]
        shackle = cast[cast.index("case Rune::Shackle:"):cast.index("case Rune::Shatter:")]
        self.assertIn('roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct")))', shackle)
        self.assertIn('Root(player, enemy, Numbers::Num(spellId, "immobilize_duration_seconds"))', shackle)
        shatter = cast[cast.index("case Rune::Shatter:"):cast.index("case Rune::Reaping:")]
        self.assertIn("for (Unit* centre : hit)", shatter)
        self.assertIn('double const delay = Tune("smite_shatter_delay_seconds");', shatter)
        self.assertIn("if (delay <= 0) Explode(player, spellId, raw, where); else player->m_Events.AddEventAtOffset(", shatter)
        self.assertIn("std::chrono::milliseconds(std::uint64_t(delay * 1000))", shatter)
        explode = self.code[self.code.index("void Explode("):self.code.index("void Check(")]
        self.assertIn('Numbers::Num(spellId, "radius_yards")', explode)
        self.assertIn("if (!player->IsInWorld() || !player->IsAlive()) return;", explode)
        self.assertIn("where = centre->GetPosition();", explode)
        reaping = cast[cast.index("case Rune::Reaping:"):cast.index("default:")]
        self.assertIn("Stat::LifeRegen, Bucket::Flat", reaping)
        self.assertIn("unsigned(hit.size())", reaping)
        self.assertIn("case Rune::SharedFate: Bind(player, spellId, hit);", cast)

    def test_shared_fate_looks_until_nothing_is_bound_and_stuns_both_of_a_pair(self):
        check = self.code[self.code.index("void Check("):self.code.index("void Bind(")]
        self.assertIn("MovedApart(one->GetExactDist(other), tie.gap, tie.distance)", check)
        self.assertIn("if (!Bound(now, tie.until)) return true;", check)
        self.assertIn("for (std::uint64_t raw : {pair.first, pair.second})", check)
        self.assertIn("if (more) player->m_Events.AddEventAtOffset", check)
        # The stuns and the reschedule happen outside the lock.
        self.assertEqual(check.count("lock_guard"), 1)
        self.assertLess(check.index("more = !mine.empty();"), check.index("Stun(player, enemy, stun);"))
        bind = self.code[self.code.index("void Bind("):self.code.index("} // namespace")]
        self.assertIn("hit[i]->GetExactDist(hit[j])", bind)
        self.assertIn("start = !mine.empty() && !watching[guid];", bind)


if __name__ == "__main__":
    unittest.main()
