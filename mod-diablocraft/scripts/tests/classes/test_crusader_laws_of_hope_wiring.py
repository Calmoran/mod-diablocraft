"""The source-text guards of Crusader Laws of Hope and the Laws' spending hook: what the dispatch must call, and what each rune
does. They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_laws_of_hope.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_laws_of_hope import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.laws = squeeze((MODULE / "src/classes/crusader/dc_crusader_laws.cpp").read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_law_its_seams(self):
        self.assertEqual(self.crusader.count("LawsOfHope::Cast(player, spellId, targets);"), 1)
        self.assertIn("if (auto hope = LawsOfHope::BasePct(spellId)) return hope;", self.crusader)
        self.assertIn("LawsOfHope::Register();", self.crusader)

    def test_the_law_deals_no_damage_of_its_own_on_the_cast(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("return 0.0;", base)

    def test_the_window_is_the_shields_time_and_the_cast_empowers_without_a_second_heal(self):
        self.assertIn('.window = "absorb_duration_seconds"', self.code)
        cast = self.code[self.code.index("void Cast("):self.code.index("void Register(")]
        self.assertLess(cast.index("Laws::Press(flavour, player, spellId, targets);"), cast.index("Empower(player, spellId);"))
        self.assertNotIn("Heal(", cast)

    def test_the_pulse_heals_the_crusader_and_its_group_whether_or_not_the_law_is_empowered(self):
        pulse = self.code[self.code.index("void Pulse("):self.code.index("void Activate(")]
        self.assertIn('HealPerPulse(Classes::HealAtLevel(Numbers::Num(base, "heal_per_second_life"), owner->GetLevel()), Laws::PulseSeconds())', pulse)
        self.assertIn("for (Player* holder : Laws::InAura(owner, Skill)) Heal(owner, holder, slotted, heal);", pulse)
        self.assertIn("if (boosted) Empower(owner, slotted);", pulse)

    def test_the_press_shields_the_crusader_and_its_group(self):
        activate = self.code[self.code.index("void Activate("):self.code.index("void Spent(")]
        self.assertIn("for (Player* holder : Laws::InAura(player, Skill))", activate)
        self.assertIn("player->AddAura(Shield, holder)", activate)
        self.assertIn('Numbers::Num(spellId, "absorb_duration_seconds")', activate)
        self.assertIn('Numbers::Num(spellId, "absorb_life")', activate)
        self.assertIn("constexpr std::uint32_t Shield = 17;", self.code)

    def test_each_rune_adds_its_number_to_the_crusader_and_its_group_until_the_windows_end(self):
        empower = self.code[self.code.index("void Empower("):self.code.index("void Pulse(")]
        self.assertIn("std::min(Laws::Now() + Laws::PulseHoldMs(), Laws::BoostEnd(guid, base))", empower)
        self.assertIn("for (Player* holder : Laws::InAura(owner, Skill))", empower)
        for stat, token in (("MovementSpeed, Bucket::Uncapped", "movement_speed_pct"), ("LifePercent, Bucket::Flat", "max_life_pct")):
            self.assertIn(f'Laws::Hold(holder, Stat::{stat}, Laws::Key(guid, slotted), Numbers::Num(slotted, "{token}"), until);', empower)
        reduction = empower[empower.index("case Rune::HopefulCry:"):]
        self.assertIn("if (ReducesElement(rune, Element(e)))", reduction)
        self.assertIn("Laws::Hold(holder, Stat::ElementReduction, Bucket::Flat, Laws::Key(guid, slotted + 0x20000u * (e + 1)), Numbers::Num(slotted, \"damage_reduction_pct\"), until, Element(e));", reduction)

    def test_faiths_reward_heals_the_group_for_the_wrath_a_cast_costs_while_empowered(self):
        spent = self.code[self.code.index("void Spent("):self.code.index("Laws::Flavour const flavour")]
        self.assertIn("RuneAt(slotted) != Rune::FaithsReward", spent)
        self.assertIn("!Laws::Boosted(player->GetGUID().GetRawValue(), Laws::BaseId(Skill), Laws::Now())", spent)
        self.assertIn('HealForWrath(Classes::HealAtLevel(Numbers::Num(slotted, "heal_per_hit_life"), player->GetLevel()), wrath)', spent)
        self.assertIn("for (Player* holder : Laws::InAura(player, Skill)) Heal(player, holder, slotted, heal);", spent)
        self.assertIn(".spent = Spent", self.code)

    def test_the_cast_hook_tells_the_laws_the_wrath_a_crusader_skill_costs(self):
        hook = self.laws[self.laws.index("void OnPlayerSpellCast("):self.laws.index("void OnPlayerCreatureKill(")]
        self.assertIn("spell->GetPowerCost() <= 0", hook)
        self.assertIn("!Shells::FindAbility(spell->GetSpellInfo()->Id)", hook)
        self.assertIn("spell->GetSpellInfo()->PowerType != POWER_ENERGY", hook)
        self.assertIn("Resources::ToPoints(wrath, spell->GetPowerCost())", hook)
        self.assertIn("if (flavour->spent) flavour->spent(player, points);", hook)

    def test_the_code_names_no_other_class(self):
        for name in ("Monk", "Barbarian", "Wizard", "Necromancer"):
            self.assertNotIn(name + "::", self.code)


if __name__ == "__main__":
    unittest.main()
