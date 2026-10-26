"""The source-text guards of Crusader Laws of Justice: what the dispatch and the damage path must call, and what each rune does.
They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_laws_of_justice.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_laws_of_justice import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.combat = squeeze((MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_law_its_seams(self):
        self.assertEqual(self.crusader.count("LawsOfJustice::Cast(player, spellId, targets);"), 1)
        self.assertIn("if (auto justice = LawsOfJustice::BasePct(spellId)) return justice;", self.crusader)
        self.assertIn("LawsOfJustice::Register();", self.crusader)
        self.assertIn("LawsOfJustice::Taken(player, attacker);", self.crusader)
        self.assertIn("double Redirect(Unit* victim, double damage) { return LawsOfJustice::Redirect(victim, damage); }", self.crusader)

    def test_the_damage_path_asks_the_redirect_after_the_monks_absorb_and_before_the_hit_lands(self):
        self.assertEqual(self.combat.count("Crusader::Redirect(victim, result)"), 1)
        self.assertIn("result = Monk::Absorb(victim, result); result = Crusader::Redirect(victim, result); result = Necromancer::Reduce(victim, result); result = WitchDoctor::Reduce(victim, result); result = Shaman::Reduce(victim, attacker, result); return result;", self.combat)

    def test_the_law_deals_no_damage_of_its_own_on_the_cast(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_cast_empowers_then_pulses_at_once(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Taken(")]
        self.assertLess(cast.index("Laws::Press(flavour, player, spellId, targets);"), cast.index("Pulse(player, spellId, true);"))

    def test_every_holder_of_the_aura_wears_the_resistance_of_the_form_the_law_is_in(self):
        pulse = self.code[self.code.index("void Pulse("):self.code.index("void Activate(")]
        self.assertIn('Laws::Number(boosted, Numbers::Num(base, "resistance_points", "passive"), Numbers::Num(base, "resistance_points", "active"))', pulse)
        self.assertIn("for (Player* holder : Laws::InAura(owner, Skill)) Laws::Hold(holder, Stat::AllResistance, Bucket::Flat, id, points, Laws::Now() + Laws::PulseHoldMs());", pulse)

    def test_each_rune_does_its_one_thing_to_the_crusader_and_its_group(self):
        activate = self.code[self.code.index("void Activate("):self.code.index("Laws::Flavour const flavour")]
        armor = activate[activate.index("case Rune::ImmovableObject:"):activate.index("case Rune::FaithsArmor:")]
        self.assertIn("for (Player* holder : Laws::InAura(player, Skill))", armor)
        self.assertIn('Laws::Hold(holder, Stat::Armor, Bucket::Flat, id, Numbers::Num(spellId, "armor_points"), now + Millis(Laws::ActiveSeconds(player, Numbers::Num(spellId, "duration_seconds"))));', armor)
        shield = activate[activate.index("case Rune::FaithsArmor:"):activate.index("case Rune::Bravery:")]
        self.assertIn("player->AddAura(Shield, holder)", shield)
        self.assertIn('Numbers::Num(spellId, "absorb_duration_seconds")', shield)
        self.assertIn('Numbers::Num(spellId, "absorb_life")', shield)
        bravery = activate[activate.index("case Rune::Bravery:"):]
        self.assertIn("Immunity(holder, spellId, true);", bravery)
        self.assertIn("Immunity(holder, spellId, false);", bravery)
        self.assertIn('Millis(Laws::ActiveSeconds(player, Numbers::Num(spellId, "duration_seconds")))', bravery)
        self.assertIn("constexpr std::uint32_t Shield = 17;", self.code)

    def test_decaying_strength_weakens_the_enemy_that_attacks_the_crusader_or_an_ally(self):
        taken = self.code[self.code.index("void Taken("):self.code.index("double Redirect(")]
        self.assertIn("!attacker->IsHostileTo(victim)", taken)
        self.assertIn("Covering(victim, Rune::DecayingStrength, true)", taken)
        self.assertIn('EnemyEffects::Weaken(attacker, spellId, each, Numbers::Num(spellId, "duration_seconds"), MaxStacks(Numbers::Num(spellId, "max_bonus_pct"), each));', taken)

    def test_protect_the_innocent_sends_the_share_to_the_crusader_not_to_the_ally_itself(self):
        redirect = self.code[self.code.index("double Redirect("):self.code.index("void Register(")]
        self.assertIn("Covering(ally, Rune::ProtectTheInnocent, false)", redirect)
        self.assertIn("Unit::DealDamage(nullptr, crusader,", redirect)
        self.assertIn("return damage - share;", redirect)
        covering = self.code[self.code.index("std::vector<Player*> Covering("):self.code.index("void Pulse(")]
        self.assertIn("(crusader == member && !includeSelf)", covering)
        self.assertIn("Laws::Boosted(crusader->GetGUID().GetRawValue(), base, now)", covering)
        self.assertIn("Laws::InAura(crusader, Skill)", covering)

    def test_the_code_names_no_other_class(self):
        for name in ("Monk", "Barbarian", "Wizard", "Necromancer"):
            self.assertNotIn(name + "::", self.code)


if __name__ == "__main__":
    unittest.main()
