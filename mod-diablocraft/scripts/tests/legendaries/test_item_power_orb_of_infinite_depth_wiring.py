"""The source-text guards of orb of infinite depth: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_orb_of_infinite_depth.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_orb_of_infinite_depth import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])

    def body(self, start, end):
        return self.powers[self.powers.index(start):self.powers.index(end)]

    def test_the_stacks_are_the_records(self):
        stacks = self.body("std::map<std::string, unsigned> BuffStacks(Player const* player)", "double IncomingFactor(Player const* player)")
        self.assertIn("for (Shells::PowerBuff const& buff : Shells::PowerBuffs)", stacks)
        self.assertIn("if (Aura const* aura = player->GetAura(buff.id))", stacks)
        self.assertIn("out[buff.owner] = std::max<unsigned>(out[buff.owner], aura->GetStackAmount());", stacks)

    def test_the_damage_dealt_and_taken_read_them(self):
        taken = self.body("double IncomingFactor(Player const* player)", "double TownPortalFactor(")
        dealt = self.body("double DealtFactor(Player const* player)", "double PetSpeedFactor(")
        for text, stat, sign in ((taken, "damage_reduction_pct", "-1.0"), (dealt, "damage_dealt_pct", "1.0")):
            self.assertLess(text.index("BuffStacks(player);"), text.index("std::lock_guard<std::mutex> lock(mutex);"))   # auras before the lock
            self.assertIn('ItemPower::StackedFactor(Data().rows, CountsOf(guid), stacks, "%s", %s, situation)' % (stat, sign), text)
        self.assertIn('ItemPower::PlayerFactor(Data().rows, CountsOf(guid), "damage_dealt_pct", situation)', dealt)   # the player rows stay
        self.assertIn('ItemPowers::SkillFactor(player, petName, "damage_increase_pct") * ItemPowers::DealtFactor(player) * CopyFactor();', self.combat)   # Rabid Strike's copy factor rides last (6d1jb)
        self.assertIn("ItemPowers::IncomingFactor(victim->ToPlayer())", self.combat)

    def test_an_explosive_blast_hit_stacks(self):
        self.assertIn('Fire(player, "hit", name, scale, target);', self.body("void Hit(Player* player, Unit* target, std::uint32_t spellId)",
                                                                           "void Attack(Player* player"))
        self.assertIn('else if (one.stat == "stack_buff" && one.row)\n                    StackBuff(player, *one.row, one.value);',
                      self.body("void Fire(Player* player, char const* event", "constexpr std::uint32_t ImmuneKey"))


if __name__ == "__main__":
    unittest.main()
