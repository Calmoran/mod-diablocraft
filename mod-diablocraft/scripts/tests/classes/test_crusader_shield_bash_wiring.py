"""The source-text guards of Crusader Shield Bash: what the engine and the dispatch must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_shield_bash.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_shield_bash import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.share = squeeze((MODULE / "src/classes/crusader/dc_crusader_block_share.cpp").read_text(encoding="utf-8"))
        self.resolve = squeeze((MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        self.combat = squeeze((MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_charge_comes_before_the_targets_are_resolved(self):
        self.assertEqual(self.resolve.count("Crusader::Approach("), 1)
        order = [self.resolve.index(m) for m in ("Crusader::Approach(player, shell.spellId, explicitTarget);",
                                                 "auto targets = ResolveTargets(player, info, shell.targeting, center, reached, explicitTarget);")]
        self.assertEqual(order, sorted(order))

    def test_the_hit_takes_the_share_with_the_other_multipliers(self):
        self.assertEqual(self.combat.count("Crusader::Multipliers(player, shell.spellId, hit.factors);"), 1)
        self.assertLess(self.combat.index("Monk::Multipliers(player, target, shell.spellId, hit.factors);"),
                        self.combat.index("Crusader::Multipliers("))

    def test_the_dispatch_hands_the_bash_its_seams(self):
        for call in ("ShieldBash::Cast(player, spellId, targets);", "ShieldBash::Approach(player, spellId, target);",
                     "BlockShare::Multipliers(player, spellId, out);", "ShieldBash::BasePct(spellId)"):
            self.assertEqual(self.crusader.count(call), 1, call)

    def test_a_shield_is_asked_for_by_the_skills_that_list_it(self):
        self.assertIn("InventoryType == INVTYPE_SHIELD", self.crusader)
        self.assertIn("EQUIPMENT_SLOT_OFFHAND", self.crusader)
        self.assertIn("if (player && row && RequiresShield(row->skill) && !ShieldWorn(player)) return SPELL_FAILED_EQUIPPED_ITEM_CLASS_OFFHAND;",
                      self.crusader)

    def test_the_engines_hit_takes_the_share_and_the_crusaders_own_strikes_carry_it(self):
        self.assertIn("if (own || !player) return;", self.share)
        self.assertIn('out.emplace_back("Block Chance share", factor);', self.share)
        # Every strike of the bash's own is made inside a scope that keeps the multiplier from adding the share a second time.
        self.assertEqual(self.code.count("BlockShare::OwnStrikes scope;"), 2)
        self.assertEqual(self.code.count("BlockShare::PctNow(player, damage, share)"), 2)
        extra = self.code[self.code.index("void ExtraStrike("):self.code.index("} // namespace")]
        self.assertLess(extra.index("BlockShare::OwnStrikes scope;"), extra.index("Combat::Strike("))

    def test_each_rune_does_its_one_thing(self):
        cast = self.code[self.code.index("switch (rune)"):]
        shattered = cast[cast.index("case Rune::ShatteredShield:"):cast.index("case Rune::ShieldCross:")]
        self.assertIn('Numbers::Num(spellId, "damage_pct")', shattered)
        self.assertIn('Numbers::Num(spellId, "block_chance_share_pct")', shattered)
        cross = cast[cast.index("case Rune::ShieldCross:"):cast.index("case Rune::OneOnOne:")]
        self.assertIn("if (length <= 0 || width <= 0) break;", cross)
        self.assertIn("OnCross(", cross)
        one = cast[cast.index("case Rune::OneOnOne:"):cast.index("default:")]
        self.assertIn('Stun(player, aimed, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));', one)
        self.assertIn('Abilities::Knockback(player, enemy, Tune("shield_bash_knockback_yards"));', one)
        self.assertIn("if (enemy != aimed)", one)

    def test_the_bash_reaches_the_cone_around_the_enemy_aimed_at(self):
        cast = self.code[self.code.index("void Cast("):]
        self.assertIn("double const heading = player->GetAngle(aimed)", cast)
        self.assertIn("if (enemy == aimed) continue;", cast)
        self.assertIn("InCone(distance, off, radius, arc)", cast)
        self.assertIn("rune == Rune::ShatteredShield && Fragment(distance, off, radius, arc, extraRadius, extraArc)", cast)


if __name__ == "__main__":
    unittest.main()
