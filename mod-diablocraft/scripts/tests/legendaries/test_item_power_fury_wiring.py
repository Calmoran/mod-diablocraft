"""The source-text guards of fury: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_fury.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_fury import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ancients = (SRC / "classes/barbarian/dc_barbarian_call_of_the_ancients.cpp").read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])

    def test_the_given_rune_reads_its_own_row(self):
        row = self.ancients[self.ancients.index("Row const* FuryRow(Player const* p, Row const* r)"):self.ancients.index("std::vector<Creature*> Living(")]
        self.assertIn('if (Rune(r, "Ancients\' Fury"))\n                return r;', row)                       # chosen: the summoning row, once
        self.assertIn('Combat::ItemPowers::GrantsRune(p, "Call of the Ancients", "Ancients\' Fury")', row)
        self.assertIn('std::string(row.skill) == "Call of the Ancients" && Rune(&row, "Ancients\' Fury")', row)
        hit = self.ancients[self.ancients.index("void Hit(Player* p, Unit* target, uint32 spell, bool basic)"):self.ancients.index("void UpdateAI(")]
        self.assertIn('if (Row const* fury = FuryRow(p, r))\n                    Resources::Modify(p, Resources::Fury, '
                      'Combat::Numbers::Num(fury->id, "gain_resource") * Combat::Passives::GenerationFactor(p));', hit)
        self.assertNotIn('Rune(r, "Ancients\' Fury")', hit)

    def test_the_ancients_swing_faster_and_the_cast_does_not(self):
        update = self.ancients[self.ancients.index("void UpdateAI(uint32 diff) override"):]
        self.assertIn('double aps = Combat::AttacksPerSecond(p) * Combat::ItemPowers::SkillFactor(p, "Call of the Ancients", "summon_attack_speed_pct") *',
                      update)               # and Tasker and Theo's pet speed after it (test_item_power_tasker_and_theo.py)
        self.assertLess(update.index("double aps ="), update.index("swing >= 1000 / aps"))
        self.assertIn('ItemPowers::SkillFactor(player, ability->skill, "attack_speed_pct")', self.combat)
        self.assertNotIn("summon_attack_speed_pct", self.combat)


if __name__ == "__main__":
    unittest.main()
