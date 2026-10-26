"""The source-text guards of Blood Brother: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_blood_brother.py, which a .cpp edit then does not re-run.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402
from test_item_power_blood_brother import CHANCE, CUT, EVENT, GENERATED, NEXT, REPO, SRC, definition, mine, mutate, source  # noqa: E402


def problems(powers, powers_h, combat, block_h):
    """What the source-text guards find wrong in the server files (the C++ is compile-checked, not run, here)."""
    out = []
    fire = definition("void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,", powers)
    loop = fire.index("for (ItemPower::Fired const& one : fired)")
    at = fire.find('one.stat == "next_attack_pct"')
    if at < 0:
        out.append("no executor for next_attack_pct")
    else:
        if at < loop:
            out.append("next_attack_pct is done before the lock is released")
        if "lock_guard" in fire[loop:]:
            out.append("the executors take the item powers' lock")
        executor = fire[at:fire.index("\n                else", at + 1) if "\n                else" in fire[at + 1:] else len(fire)]
        if "ArmNextAttack(player, one.row->owner, one.value);" not in executor:
            out.append("the executor does not hand the item and its rolled percent to ArmNextAttack")
    arm = definition("void ArmNextAttack(Player* player, std::string const& owner, double pct)", powers)
    for need, why in (('Shells::PowerBuffFor(owner.c_str(), "next_attack_pct")', "the aura is the item's record"),
                      ("player->AddAura(id, player)", "the record goes on the player"),
                      ("effect->ChangeAmount(", "the percent is kept in the aura's effect amount"),
                      ("ItemBlock::Arm(", "a block while armed keeps the larger bonus")):
        if need not in arm:
            out.append("ArmNextAttack lacks %s (%s)" % (need, why))
    armed = definition("double ArmedPct(Player const* player)", powers)
    if 'std::string(buff.stat) == "next_attack_pct"' not in armed or "GetAmount()" not in armed:
        out.append("ArmedPct does not read the next_attack_pct record's amount")
    connected = definition("void NextAttackConnected(Player* player, std::uint32_t spellId)", powers)
    for need, why in (("Shells::FindAbility(spellId)", "the cast's skill"),
                      ("ArmedPct(player)", "the armed percent is what is spent"),
                      ("ItemBlock::Connect(armed, spent, skill->skill)", "the rule spends it on the cast"),
                      ("DisarmNextAttack(player);", "the record goes off with the spend"),
                      ("clocks[player->GetGUID().GetRawValue()].nextSpent", "the spent bonus is the player's")):
        if need not in connected:
            out.append("NextAttackConnected lacks %s (%s)" % (need, why))
    disarm = definition("void DisarmNextAttack(Player* player)", powers)
    if "RemoveAurasDueToSpell(buff.id)" not in disarm or '"next_attack_pct"' not in disarm:
        out.append("DisarmNextAttack does not take the record off")
    attack = definition("void Attack(Player* player, std::uint32_t spellId, unsigned enemies)", powers)
    if "NextAttackConnected(player, spellId);" not in attack or attack.index("NextAttackConnected(player, spellId);") > attack.index("return;"):
        out.append("Attack does not spend the armed bonus before its early return")
    cast = definition("void Cast(Player* player, std::uint32_t spellId)", powers)
    if "NextAttackPressed(player);" not in cast or cast.index("NextAttackPressed(player);") > cast.index('Fire(player, "cast"'):
        out.append("Cast does not end the spent attack before it fires")
    if "ItemBlock::Press(mine->second.nextSpent)" not in definition("void NextAttackPressed(Player* player)", powers):
        out.append("NextAttackPressed does not end the spent attack by the rule")
    factor = definition("double NextAttackFactor(Player const* player, std::string const& skill)", powers)
    for need, why in (("ArmedPct(player)", "the armed record"), ("ItemBlock::NextAttackFactor(armed,", "the rule"), ("nextSpent", "the cast that spent it")):
        if need not in factor:
            out.append("NextAttackFactor lacks %s (%s)" % (need, why))
    if 'Fire(player, "block", "", 1.0, attacker);' not in definition("void Blocked(Player* player, Unit* attacker)", powers):
        out.append("Blocked does not fire the block event with the attacker")
    if 'PlayerSum(Data().rows, CountsOf(guid), "block_chance_pct"' not in definition("double BlockBonus(Player const* player)", powers):
        out.append("BlockBonus does not sum the block_chance_pct rows")
    if 'CutFactor(Data().rows, CountsOf(guid), "blocked_damage_cut_pct"' not in definition("double BlockedFactor(Player const* player)", powers):
        out.append("BlockedFactor does not cut by the blocked_damage_cut_pct rows")
    drop = definition("void DropStacks(Player* player)", powers)
    if 'row.stat == "next_attack_pct" && on.count(row.owner)' not in drop or "DisarmNextAttack(player);" not in drop or ".nextSpent = {}" not in drop:
        out.append("taking the sword off does not take the armed record and the spent bonus away")
    logout = definition("void OnPlayerLogout(Player* player) override", powers)
    if "clocks.erase(player->GetGUID().GetRawValue());" not in logout:
        out.append("a logout keeps the player's clock, and the bonus spent with it")
    for name in ("BlockBonus", "BlockedFactor", "Blocked", "NextAttackFactor"):
        if not re.search(r"\b%s\(" % name, powers_h):
            out.append("dc_item_powers.h does not declare %s" % name)
    mitigate = definition("std::optional<double> Mitigate(Unit* victim, unsigned schoolMask, double damage, bool* blocked, bool melee, Unit* attacker)", combat)
    for need, why in (("ItemPowers::BlockBonus(wearer)", "the worn items' chance"),
                      ("NumericData::Block().totalChanceCap", "the sheet's own total cap holds the sum"),
                      ("ItemBlock::Chance(s[Stat::BlockChance], bonus,", "the rule joins the sheet's chance and the items'"),
                      ("ItemBlock::Blocked(result, amount, ItemPowers::BlockedFactor(wearer))", "the cut, then the flat amount, in the rule"),
                      ("ItemPowers::Blocked(wearer, attacker);", "the block is an event"),
                      ("*blocked = true;", "the flag stays surfaced")):
        if need not in mitigate:
            out.append("Mitigate lacks %s (%s)" % (need, why))
    branch = definition("if (result > 0 && chance > 0 && Roll() * 100 < chance)", mitigate)
    if "ItemPowers::Blocked(wearer, attacker);" not in branch:
        out.append("the block event is not inside the blocked branch")
    compute = definition("bool ComputeHit(Player* player, Unit* target, std::uint32_t spellId, Hit& hit, std::optional<double> skillPct,", combat)
    if "if (!periodic && !petSkill)\n            hit.legendary *= ItemPowers::NextAttackFactor(player, shell.skill);" not in compute:
        out.append("ComputeHit does not give the next attack its bonus, or gives it to a tick or a pet")
    if '#include "dc_item_block_math.h"' not in combat or '#include "dc_item_block_math.h"' not in powers:
        out.append("a file that uses ItemBlock does not include dc_item_block_math.h")
    for need in ("inline double Chance(", "inline double Blocked(", "inline double NextAttackFactor(", "inline Spent Connect(", "inline Spent Press(", "inline double Arm("):
        if need not in block_h:
            out.append("dc_item_block_math.h lacks %s" % need)
    return out


class Hooks(unittest.TestCase):
    powers = item_powers_source.text()
    powers_h = source("dc_item_powers.h")
    combat = source("dc_combat.cpp")
    block_h = source("dc_item_block_math.h")

    def args(self, **changed):
        base = dict(powers=self.powers, powers_h=self.powers_h, combat=self.combat, block_h=self.block_h)
        base.update(changed)
        return base

    def test_the_guards_hold_on_the_source(self):
        self.assertEqual([], problems(**self.args()))

    def test_one_caller_of_the_block_event(self):
        self.assertEqual(["dc_combat.cpp"], [p.name for p in SRC.rglob("*.cpp") if "ItemPowers::Blocked(" in p.read_text(encoding="utf-8")])

    def test_the_stats_are_in_the_generator_and_the_contract(self):
        self.assertIn(NEXT, generator.EFFECT_STATS)
        self.assertIn(EVENT, generator.EVENTS)
        for stat in (CHANCE, CUT):
            self.assertIn(stat, generator.PLAYER_STATS)
            self.assertIn(stat, generator.POSITIVE_PLAYER_STATS)
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        for need in ("| `%s` (" % CHANCE, "| `%s` (" % CUT, "| `%s` (" % NEXT, "| `block` (", "### Blood Brother (`diablocraft-jxvsn`", GENERATED.name):
            self.assertIn(need, text)

    def test_the_server_mutants_fail_the_guards(self):
        p, c, h = self.powers, self.combat, self.powers_h
        mutants = {
            "no_executor": dict(powers=mutate(p, 'one.stat == "next_attack_pct" && one.row', 'one.stat == "next_attack" && one.row')),
            "the_item_dropped": dict(powers=mutate(p, "ArmNextAttack(player, one.row->owner, one.value);", 'ArmNextAttack(player, "", one.value);')),
            "the_percent_dropped": dict(powers=mutate(p, "ArmNextAttack(player, one.row->owner, one.value);", "ArmNextAttack(player, one.row->owner, 100.0);")),
            "arm_stacks": dict(powers=mutate(p, "ItemBlock::Arm(std::max(0, effect->GetAmount()), pct)", "std::max(0, effect->GetAmount()) + pct")),
            "arm_not_on_the_player": dict(powers=mutate(p, "aura = player->AddAura(id, player);\n            AuraEffect* effect = aura ? aura->GetEffect(0) : nullptr;\n            if (!effect)\n                return;\n            effect->ChangeAmount(", "aura = player->AddAura(id, nullptr);\n            AuraEffect* effect = aura ? aura->GetEffect(0) : nullptr;\n            if (!effect)\n                return;\n            effect->ChangeAmount(")),
            "the_armed_read_wrong": dict(powers=mutate(p, 'if (std::string(buff.stat) == "next_attack_pct")\n                    if (Aura const* aura = player->GetAura(buff.id))',
                                                      'if (std::string(buff.stat) == "armor_pct")\n                    if (Aura const* aura = player->GetAura(buff.id))')),
            "the_spend_not_ruled": dict(powers=mutate(p, "ItemBlock::Connect(armed, spent, skill->skill)", "ItemBlock::Spent{armed, skill->skill}")),
            "the_spend_keeps_the_record": dict(powers=mutate(p, "            DisarmNextAttack(player);\n        }\n\n        // A skill was pressed",
                                                            "        }\n\n        // A skill was pressed")),
            "the_record_never_removed": dict(powers=mutate(p, '"next_attack_pct")\n                    player->RemoveAurasDueToSpell(buff.id);',
                                                          '"next_attack_pct")\n                    ;')),
            "attack_spends_late": dict(powers=mutate(p, "        if (player)\n            NextAttackConnected(player, spellId);\n", "")),
            "no_press": dict(powers=mutate(p, "mine->second.nextSpent = ItemBlock::Press(mine->second.nextSpent);", ";")),
            "press_not_called": dict(powers=mutate(p, "        NextAttackPressed(player);\n", "")),
            "press_after_the_cast_event": dict(powers=mutate(p, "        NextAttackPressed(player);\n        Fire(player, \"cast\", skill->skill, 1.0);",
                                                             "        Fire(player, \"cast\", skill->skill, 1.0);\n        NextAttackPressed(player);")),
            "the_factor_unruled": dict(powers=mutate(p, "ItemBlock::NextAttackFactor(armed,", "ItemBlock::NextAttackFactor(0.0,")),
            "block_fires_nothing": dict(powers=mutate(p, 'Fire(player, "block", "", 1.0, attacker);', ";")),
            "block_without_the_attacker": dict(powers=mutate(p, 'Fire(player, "block", "", 1.0, attacker);', 'Fire(player, "block", "", 1.0);')),
            "chance_wrong_stat": dict(powers=mutate(p, '"block_chance_pct", SituationOf', '"crit_chance_pct", SituationOf')),
            "cut_wrong_stat": dict(powers=mutate(p, '"blocked_damage_cut_pct", SituationOf', '"damage_dealt_pct", SituationOf')),
            "sword_off_keeps_the_record": dict(powers=mutate(p, "            if (!arms)\n            {\n                DisarmNextAttack(player);", "            if (!arms)\n            {")),
            "sword_off_keeps_the_spend": dict(powers=mutate(p, "clocks[player->GetGUID().GetRawValue()].nextSpent = {};", ";")),
            "logout_keeps_the_clock": dict(powers=mutate(p, "                clocks.erase(player->GetGUID().GetRawValue());\n", "")),
            "not_declared": dict(powers_h=mutate(h, "double BlockedFactor(Player const*);", "")),
            "the_include_dropped": dict(combat=mutate(c, '#include "dc_item_block_math.h"\n', "")),
            "the_bonus_not_read": dict(combat=mutate(c, "double const bonus = ItemPowers::BlockBonus(wearer);", "double const bonus = 0.0;")),
            "the_cap_a_literal": dict(combat=mutate(c, "NumericData::Block().totalChanceCap", "75.0")),
            "the_chance_unruled": dict(combat=mutate(c, "ItemBlock::Chance(s[Stat::BlockChance], bonus,", "(s[Stat::BlockChance] + bonus + 0 *")),
            "the_cut_unread": dict(combat=mutate(c, "ItemBlock::Blocked(result, amount, ItemPowers::BlockedFactor(wearer))", "std::max(0.0, result - amount)")),
            "the_event_unfired": dict(combat=mutate(c, "            ItemPowers::Blocked(wearer, attacker);\n", "")),
            "the_event_on_every_hit": dict(combat=mutate(c, "            ItemPowers::Blocked(wearer, attacker);\n        }\n        result = Monk::Absorb", "        }\n        ItemPowers::Blocked(wearer, attacker);\n        result = Monk::Absorb")),
            "the_flag_lost": dict(combat=mutate(c, "            if (blocked)\n                *blocked = true;\n            ItemPowers::Blocked", "            ItemPowers::Blocked")),
            "ticks_take_the_bonus": dict(combat=mutate(c, "if (!periodic && !petSkill)\n            hit.legendary *= ItemPowers::NextAttackFactor", "if (!petSkill)\n            hit.legendary *= ItemPowers::NextAttackFactor")),
            "pets_take_the_bonus": dict(combat=mutate(c, "if (!periodic && !petSkill)\n            hit.legendary *= ItemPowers::NextAttackFactor", "if (!periodic)\n            hit.legendary *= ItemPowers::NextAttackFactor")),
            "the_bonus_not_read_in_the_hit": dict(combat=mutate(c, "hit.legendary *= ItemPowers::NextAttackFactor(player, shell.skill);", ";")),
        }
        for name, changed in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual([], problems(**self.args(**changed)), name + " survived")


if __name__ == "__main__":
    unittest.main()
