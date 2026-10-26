"""The source-text guards of Crusader Punish: what the engine must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_punish.py, which a
.cpp edit then does not re-run.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_punish import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = CODE.read_text(encoding="utf-8")
        self.crusader = (MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8")
        self.combat = (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8")
        self.resolve = (MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")

    def test_the_loader_asks_the_crusader_after_the_monk(self):
        text = squeeze(self.combat)
        self.assertIn("else if (auto crusader = Crusader::BasePct(ability.id)) shell.damagePct = *crusader;", text)
        self.assertLess(text.index("Monk::BasePct(ability.id)"), text.index("Crusader::BasePct(ability.id)"))

    def test_the_spell_check_refuses_with_the_crusaders_own_result(self):
        text = squeeze(self.combat)
        self.assertIn("Crusader::CanCast(player, spell->GetSpellInfo()->Id); refused != SPELL_CAST_OK", text)
        self.assertIn("result = refused;", text)
        # A triggered cast (a rune's own follow-on) is not refused for a missing shield.
        self.assertRegex(text, r"if \(!spell->IsTriggered\(\)\) if \(SpellCastResult const refused = Crusader::CanCast")
        self.assertIn("SPELL_FAILED_EQUIPPED_ITEM_CLASS_OFFHAND", self.crusader)

    def test_a_block_is_told_once_where_it_is_decided(self):
        text = squeeze(self.combat)
        self.assertEqual(text.count("Crusader::Blocked("), 1)
        block = text[text.index("if (result > 0 && chance > 0 && Roll() * 100 < chance)"):text.index("result = Monk::Absorb(")]
        # The Crusader hears the block as the flag is set and before the items do (fold I's guard test plants mutants on the flag and on the line before the brace).
        self.assertIn("Crusader::Blocked(victim, attacker); if (blocked) *blocked = true; ItemPowers::Blocked(wearer, attacker); }", block)

    def test_the_critical_chance_takes_the_crusaders_bonus_with_the_others(self):
        text = squeeze(self.combat)
        self.assertEqual(text.count("Crusader::CritBonus(player, target, shell.spellId)"), 1)
        self.assertIn("+Wizard::CritBonus(player, target, shell.spellId)+Crusader::CritBonus(player, target, shell.spellId)+Necromancer::CritBonus(player, target)+DemonHunter::CritBonus(player, target, shell.spellId)+GemPowers::CritBonus", text)

    def test_connected_is_told_to_the_crusader_after_the_monk(self):
        text = squeeze(self.resolve)
        self.assertIn("Monk::Connected(player, spellId); Crusader::Connected(player, spellId, enemies); Necromancer::Connected(player, spellId, enemies); DemonHunter::Connected(player, spellId); WitchDoctor::Connected(player, spellId, enemies); Shaman::Connected(player, spellId, enemies); }", text)

    def test_the_dispatch_hands_punish_every_seam(self):
        text = squeeze(self.crusader)
        for call in ("Punish::BasePct(spellId)", "Punish::Connected(player, spellId)",
                     "Punish::CritBonus(player, spellId)", "Punish::Blocked(player, attacker)"):
            self.assertEqual(text.count(call), 1, call)
        # Wrath is paid before the skill's own effects, for a Crusader's Wrath row only.
        self.assertLess(text.index("Generate(player, spellId);"), text.index("Punish::Connected(player, spellId);"))
        self.assertIn("Classes::ClassIdOf(player) != Wrath.classId", text)
        self.assertIn('Numbers::Get(spellId, "generated_resource")', text)
        self.assertIn('ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct")', text)

    def test_a_block_answers_only_with_hardened_senses_and_never_twice(self):
        text = squeeze(self.code)
        blocked = text[text.index("void Blocked("):text.index("double CritBonus(")]
        self.assertIn("if (answering || !player) return;", blocked)
        self.assertIn("!Buffs::Stacks(player, SensesId(), Stat::BlockChance)", blocked)
        self.assertEqual(blocked.count("answering = true;"), 2)
        self.assertEqual(blocked.count("answering = false;"), 2)
        # The runes' own numbers, not the skill's hit.
        self.assertIn('Combat::Strike(player, attacker, spellId, Numbers::Own(spellId, "damage_pct"));', blocked)
        self.assertIn('auto const pct = Numbers::Own(spellId, "damage_pct");', blocked)

    def test_punish_gives_hardened_senses_and_uses_up_a_waiting_fury(self):
        text = squeeze(self.code)
        connected = text[text.index("void Connected("):text.index("void Blocked(")]
        self.assertLess(connected.index("furyArmed.erase("), connected.index("if (!Is(spellId)) return;"))
        self.assertLess(connected.index("if (!Is(spellId)) return;"), connected.index("Buffs::Stack("))

    def test_the_skill_asks_for_a_shield(self):
        # The shield check is the dispatch's, for every skill whose tooltip says it (test_crusader_shield_bash reads the sheet).
        self.assertIn('NeedShield = {"Punish",', self.crusader)
        self.assertNotIn("INVTYPE_SHIELD", self.code)

    def test_no_class_is_named_outside_the_crusader_folder(self):
        # The seams are the Crusader's namespace; the shared engine files add no class check of their own.
        for path in (MODULE / "src/combat").glob("dc_combat*"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("CLASS_PALADIN", text, path.name)


if __name__ == "__main__":
    unittest.main()
