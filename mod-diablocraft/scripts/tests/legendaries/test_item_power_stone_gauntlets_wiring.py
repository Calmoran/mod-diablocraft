"""The source-text guards of stone gauntlets: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_stone_gauntlets.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_stone_gauntlets import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.passives = (SRC / "classes/barbarian/dc_barbarian_passives.cpp").read_text(encoding="utf-8")

    def body(self, start, end):
        at = self.powers.index(start)
        return self.powers[at:self.powers.index(end, at)]

    def test_a_hit_taken_stacks_both_records_on_one_timer(self):
        self.assertIn('Fire(player, "taken", "", 1.0);', self.body("void Taken(Player* player)", "void Damaged(Player* player, std::uint32_t damage)"))
        fire = self.body("void Fire(Player* player, char const* event", "} // namespace Detail")
        self.assertIn('else if (one.stat == "stack_buff" && one.row)\n                    StackBuff(player, *one.row, one.value);', fire)
        stack = self.body("void StackBuff(Player* player, ItemPower::Row const& row, double add)", "void MarkEnemy(")
        for line in ("std::int32_t const ms = static_cast<std::int32_t>(row.stackSeconds * 1000.0);",
                     "for (Shells::PowerBuff const& buff : Shells::PowerBuffs)", "if (row.owner != buff.owner)",
                     "aura = player->AddAura(buff.id, player);", "unsigned const stacks = ItemPower::Stacked(held, add, StackCap(row));",
                     "aura->SetStackAmount(static_cast<std::uint8_t>(stacks));", "aura->SetMaxDuration(ms);", "aura->SetDuration(ms);",
                     "StackSheet(player);"):
            self.assertIn(line, stack)

    def test_the_armor_reaches_the_sheet_and_leaves_it(self):
        sheet = self.body("void StackSheet(Player* player, std::uint32_t leaving = 0)", "void StackBuff(")
        self.assertIn('if (std::string(buff.stat) != "armor_pct")', sheet)
        self.assertIn("Aura const* aura = buff.id == leaving ? nullptr : player->GetAura(buff.id);", sheet)
        self.assertIn("aura->GetStackAmount() * ItemPower::BuffValue(Data().rows, buff.owner, buff.stat)", sheet)
        self.assertIn("Stats::RemoveContribution(guid, Source::Temporary, Stat::Armor, buff.id);", sheet)
        self.assertIn("Stats::AddContribution(guid, {Source::Temporary, Stat::Armor, buff.id, pct, Bucket::Percent});", sheet)
        self.assertLess(sheet.index("Stats::Recompute(player);"), sheet.index("Inventory::PushSheet(player);"))
        ends = self.body("class StackEnds final : public UnitScript", "void RegisterBuffScripts()")
        self.assertIn("{UNITHOOK_ON_AURA_REMOVE}", ends)
        self.assertIn('if (buff.id == id && std::string(buff.stat) == "armor_pct")\n                        StackSheet(player, id);', ends)
        self.assertIn("new StackEnds();", self.powers[self.powers.index("void RegisterBuffScripts()"):])

    def test_the_stacks_end_with_the_gloves(self):
        refresh = self.body("void Refresh(Player* player, Item* changed", "std::vector<double> WornRolls(")
        self.assertTrue(refresh.rstrip().endswith("DropStacks(player);\n    }"))
        drop = self.body("void DropStacks(Player* player)", "class StackEnds")
        self.assertIn("clocks[player->GetGUID().GetRawValue()].wornSince", drop)
        self.assertIn("if (!on.count(buff.owner) && ItemPower::BuffValue(Data().rows, buff.owner, buff.stat) != 0)\n"
                      "                    player->RemoveAurasDueToSpell(buff.id);", drop)

    def test_the_attack_speed_is_read_where_the_attacks_per_second_are(self):
        factor = self.body("double AttackSpeedFactor(Player* player)", "} // namespace DC::Combat::ItemPowers")
        self.assertIn('if (std::string(buff.stat) == "movement_speed_pct")', factor)       # the slow's stacks: gone with control immunity
        self.assertIn("factor *= ItemPower::StackedSpeedFactor(Data().rows, buff.owner, slow->GetStackAmount());", factor)
        aps = self.combat[self.combat.index("double AttacksPerSecond(Player* player, std::uint32_t spellId)"):self.combat.index("bool DualWielding(")]
        self.assertIn("WitchDoctor::AttackSpeed(player, spellId, Necromancer::AttackSpeed(player, spellId, Crusader::AttackSpeed(player, spellId, Primaries::AttackSpeed(player, spellId, Monk::AttackSpeed(player, spellId, sheet->attacksPerSecond))))) * ItemPowers::AttackSpeedFactor(player)", aps)
        hand = self.combat[self.combat.index("double HandAttacksPerSecond(Player* player"):self.combat.index("std::pair<double, double> WeaponRange(")]
        self.assertIn('ItemPowers::SkillFactor(player, ability->skill, "attack_speed_pct") : 1.0) * ItemPowers::AttackSpeedFactor(player);', hand)

    def test_juggernaut_leaves_the_power_buffs_alone(self):
        apply = self.passives[self.passives.index("void OnAuraApply(Unit* u, Aura* a) override"):self.passives.index("void OnAuraRemove(Unit* u")]
        self.assertIn("[&](Shells::PowerBuff const& buff) { return buff.id == a->GetId(); }))\n                    return;", apply)
        self.assertLess(apply.index("Shells::PowerBuffs"), apply.index("GetAllEffectsMechanicMask()"))


if __name__ == "__main__":
    unittest.main()
