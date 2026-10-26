"""The source-text guards of Crusader Slash: what the engine and the dispatch must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_slash.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_slash import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.resolve = squeeze((MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))

    def test_the_engine_tells_the_crusader_the_count_and_the_targets(self):
        self.assertIn("Monk::Connected(player, spellId); Crusader::Connected(player, spellId, enemies); Necromancer::Connected(player, spellId, enemies); DemonHunter::Connected(player, spellId); WitchDoctor::Connected(player, spellId, enemies); Shaman::Connected(player, spellId, enemies); }", self.resolve)
        self.assertEqual(self.resolve.count("Crusader::Cast("), 1)
        order = [self.resolve.index(m) for m in ("ResolveHit(player, target, punch.pct", "Monk::Cast(player, shell.spellId, targets, punch);",
                                                 "Crusader::Cast(player, shell.spellId, targets);", "Connected(player, shell.spellId, connected);")]
        self.assertEqual(order, sorted(order))

    def test_the_dispatch_hands_slash_every_seam(self):
        for call in ("Slash::Connected(player, spellId, enemies);", "Slash::Cast(player, spellId, targets);",
                     "Slash::CritBonus(player, spellId)"):
            self.assertEqual(self.crusader.count(call), 1, call)
        # Wrath is paid before the skill's own stacks.
        self.assertLess(self.crusader.index("Generate(player, spellId);"), self.crusader.index("Slash::Connected("))

    def test_zeal_and_guard_stack_for_each_enemy_hit(self):
        zeal = self.code[self.code.index("case Rune::Zeal:"):self.code.index("case Rune::Guard:")]
        self.assertIn("Stat::AttackSpeed, Bucket::Flat", zeal)
        self.assertTrue(zeal.rstrip().endswith("Numbers::Num(spellId, \"duration_seconds\"), enemies); break;"), zeal)
        guard = self.code[self.code.index("case Rune::Guard:"):self.code.index("default:")]
        self.assertIn("Stat::Armor, Bucket::Percent", guard)
        self.assertIn('Tune("slash_guard_seconds"), enemies);', guard)

    def test_electrify_rolls_for_each_enemy_and_stuns_for_the_sheets_seconds(self):
        electrify = self.code[self.code.index("case Rune::Electrify:"):self.code.index("case Rune::Carve:")]
        self.assertIn("for (Unit* enemy : targets)", electrify)
        self.assertIn('roll_chance_f(float(Numbers::Num(spellId, "proc_chance_pct")))', electrify)
        self.assertIn('double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);', electrify)
        self.assertIn("Stun(player, enemy, stun)", electrify)

    def test_carve_strikes_what_the_cone_did_not_take_and_counts_the_swing_once(self):
        carve = self.code[self.code.index("case Rune::Carve:"):self.code.index("double CritBonus(")]
        self.assertIn("player->HasInArc(arc, enemy)", carve)
        self.assertIn("std::find(targets.begin(), targets.end(), enemy) != targets.end()", carve)
        self.assertIn("if (targets.empty() && !struck.empty()) Combat::Connected(player, spellId, unsigned(struck.size()));", carve)

    def test_crush_reads_without_a_miss_log(self):
        self.assertIn('Numbers::Get(spellId, "crit_chance_pct").value_or(0.0)', self.code)

    def test_the_stun_is_the_stock_hold(self):
        self.assertIn("constexpr std::uint32_t StunHold = 15878;", self.crusader)
        self.assertIn("Hold(player, target, StunHold, seconds);", self.crusader)
        self.assertIn("target->RemoveAurasDueToSpell(aura, player->GetGUID());", self.crusader)


if __name__ == "__main__":
    unittest.main()
