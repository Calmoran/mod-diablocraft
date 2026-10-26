"""The source-text guards of blade of the warlord: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_blade_of_the_warlord.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_blade_of_the_warlord import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_hit_multiplies_the_factor_into_its_legendary_term(self):
        text = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn("hit.legendary *= ItemPowers::SpentFactor(player, petName, hit.spent);", text)
        # after the legendary term is set, before it is used; the base skill name, so every rune of Bash takes it
        self.assertLess(text.index('hit.legendary = ItemPowers::SkillFactor('), text.index("hit.legendary *= ItemPowers::SpentFactor("))
        self.assertLess(text.index("hit.legendary *= ItemPowers::SpentFactor("), text.index("hit.total = Total("))

    def test_the_gm_hit_previews_a_cast_at_the_fury_now(self):
        text = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        body = text[text.index("std::string baseSkill;"):]
        body = body[:body.index("handler->SendSysMessage(hit.Describe());")]
        self.assertIn("hit.spent = ItemPowers::ResourceSpend(player, baseSkill, CurrentFury(player));", body)
        self.assertLess(body.index("hit.spent ="), body.index("ComputeHit(player, handler->getSelectedUnit(), spellId, hit)"))

    def test_the_hit_carries_the_amount(self):
        self.assertRegex((SRC / "combat/dc_combat.h").read_text(encoding="utf-8"), r"double spent = 0;")

    def test_the_readers_are_declared_and_read_before_the_power_lock(self):
        header = (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8")
        self.assertIn("double ResourceSpend(Player const*, std::string const& skill, double have);", header)
        self.assertIn("double SpentFactor(Player const*, std::string const& skill, double spent);", header)
        text = item_powers_source.CPP.read_text(encoding="utf-8")
        for name, call in (("double ResourceSpend(", "ItemPower::ResourceSpend(Data().rows, CountsOf(guid), skill, have,"),
                           ("double SpentFactor(", "ItemPower::ResourceSpentFactor(Data().rows, CountsOf(guid), skill, spent,")):
            body = text[text.index(name):]
            body = body[:body.index("\n    }\n")]
            self.assertIn(call, body)
            self.assertRegex(body, r"if \(!player\)\s+return")

    def provider(self):
        text = (SRC / "classes/barbarian/dc_barbarian_primaries.cpp").read_text(encoding="utf-8")
        return text[text.index("bool ProvideFinalSpellDamage("):text.index("class GeometryAndControl")]

    def test_the_provider_takes_the_fury_after_the_hit_before_the_grant(self):
        body = self.provider()
        self.assertIn("ItemPowers::ResourceSpend(player, row->skill,", body)
        order = ["hit.spent =", "if (!ComputeHit(player, target, info->Id, hit))", "Resources::Add(player, Resources::Fury, -hit.spent)",
                 "Abilities::Spent(player, hit.spent)", "Fury(player, grant)"]
        positions = [body.index(x) for x in order]
        self.assertEqual(sorted(positions), positions, "the amount is set, the hit computed, the Fury taken, then the grant")
        # only a pressed cast of the primary pays: a triggered cast and the secondary shells do not
        self.assertIn("spell->IsTriggered()", body)

    def test_the_pulverize_shockwave_carries_the_amount(self):
        text = (SRC / "classes/barbarian/dc_barbarian_primaries.cpp").read_text(encoding="utf-8")
        self.assertIn("thread_local double secondarySpent", text)
        self.assertIn("secondarySpent = hit.spent;", text)


if __name__ == "__main__":
    unittest.main()
