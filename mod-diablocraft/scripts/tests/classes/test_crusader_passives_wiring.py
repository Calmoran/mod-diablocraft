"""The source-text guards of the Crusader's first six passives: what the dispatch and the engine must call, and what each passive does.
They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_crusader_passives.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_crusader_passives import CODE, MODULE  # noqa: E402


def squeeze(text):
    return re.sub(r"\s+", " ", text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.combat = squeeze((MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_hands_the_passives_their_seams(self):
        self.assertIn("BlockShare::Multipliers(player, spellId, out); Passive::Multipliers(player, spellId, out);", self.crusader)
        self.assertIn("Slash::Connected(player, spellId, enemies); Passive::Connected(player, spellId);", self.crusader)
        self.assertIn("Punish::Blocked(player, attacker); Passive::Blocked(player);", self.crusader)
        self.assertIn("double AttackSpeed(Player* player, std::uint32_t spellId, double base) { return Passive::AttackSpeed(player, spellId, base); }", self.crusader)
        self.assertIn("Passive::Register();", self.crusader)

    def test_the_engine_asks_the_crusader_for_a_skills_attack_speed_for_both_the_sheet_and_each_hand(self):
        self.assertEqual(self.combat.count("Crusader::AttackSpeed(player, spellId,"), 2)
        self.assertIn("Crusader::AttackSpeed(player, spellId, Primaries::AttackSpeed(player, spellId, Monk::AttackSpeed(player, spellId, sheet->attacksPerSecond)))", self.combat)
        self.assertIn("Crusader::AttackSpeed(player, spellId, Primaries::AttackSpeed(player, spellId, Monk::AttackSpeed(player, spellId, hand)))", self.combat)

    def test_the_passives_are_the_crusaders_and_read_the_slots_and_the_items(self):
        self.assertIn('return IsCrusader(player) && Passives::Has(player, name);', self.code)
        self.assertIn('Classes::ClassIdOf(player) == Resources::Find("Crusader", "wrath")->classId', self.code)

    def test_the_grip_is_read_from_the_main_hand_and_the_off_hand(self):
        wield = self.code[self.code.index("Wield WieldOf("):self.code.index("// Per Crusader")]
        self.assertIn("EQUIPMENT_SLOT_MAINHAND", wield)
        self.assertIn("type == INVTYPE_WEAPON || type == INVTYPE_WEAPONMAINHAND", wield)
        self.assertIn("type == INVTYPE_2HWEAPON", wield)
        self.assertIn("EQUIPMENT_SLOT_OFFHAND", wield)
        self.assertIn("InventoryType == INVTYPE_SHIELD", wield)

    def test_the_core_is_told_the_grip_and_the_shield_comes_off_when_it_is_gone(self):
        update = self.code[self.code.index("class Update"):]
        self.assertIn("PLAYERHOOK_CAN_TITAN_GRIP", update)
        hook = update[update.index("bool OnPlayerCanTitanGrip(Player const* player) override"):update.index("void OnPlayerUpdate(")]
        self.assertIn("bool const crusader = IsCrusader(player);", hook)
        self.assertIn('HeavenlyStrengthGrip(crusader, crusader && Passives::Has(const_cast<Player*>(player), "Heavenly Strength"))', hook)
        tick = update[update.index("void OnPlayerUpdate("):update.index("void OnPlayerLogout(")]
        self.assertLess(tick.index("state.clock = 0;"), tick.index("GripBroken("))
        self.assertIn('if (GripBroken(WieldOf(player), On(player, "Heavenly Strength"))) player->AutoUnequipOffhandIfNeed();',
                      squeeze(tick))

    def test_the_sheet_rows_are_the_sheets_numbers_kept_by_the_update_script(self):
        refresh = self.code[self.code.index("void Refresh("):self.code.index("class Update")]
        for stat, token in (("AttackSpeed", "attack_speed_pct"), ("LifeRegen", "heal_per_second_life"), ("MaxFury", "max_pool_resource")):
            self.assertIn(f"Stat::{stat}", refresh)
            self.assertIn(f'"{token}"', refresh)
        self.assertIn('CooldownContribution(Numbers::Num(fervor, "cooldown_reduction_pct"))', refresh)
        self.assertIn('Numbers::Num(vigilant, "damage_reduction_pct")', refresh)
        self.assertIn("if (VigilantReduces(static_cast<Element>(e)))", refresh)
        self.assertIn("Passives::RefreshModifiers(player);", refresh)
        for stat in ("AttackSpeed", "CooldownReduction", "LifeRegen", "ElementReduction", "MaxFury"):
            self.assertIn(f"Stats::RemoveContribution(guid, Source::Passives, Stat::{stat},", refresh)
        update = self.code[self.code.index("class Update"):]
        self.assertIn('On(player, "Fervor") && FervorOn(WieldOf(player))', update)
        self.assertIn("refresh = state.dirty || state.signature != wanted || state.blockCenti != blockCenti || state.gems != gems || Classes::BuiltAtOtherLevel(state.level, level);", update)
        self.assertIn("OnPlayerMapChanged", update)

    def test_each_read_passive_does_its_one_thing(self):
        heavenly = self.code[self.code.index("void Multipliers("):self.code.index("double AttackSpeed(")]
        self.assertIn('AddFactor(out, "Heavenly Strength", -pct);', heavenly)
        self.assertIn('HeavenlyStrengthPct(WieldOf(player), Num("Heavenly Strength", "damage_dealt_reduction_pct"))', heavenly)
        fanatic = self.code[self.code.index("double AttackSpeed("):self.code.index("void Connected(")]
        self.assertIn("!FanaticismSkill(row->skill) || !On(player, \"Fanaticism\")", fanatic)
        self.assertIn('FanaticismAps(base, (*sheet)[Stat::AttackSpeed], Num("Fanaticism", "attack_speed_pct"), DC::NumericData::Rule("attack_speed_cap"))', fanatic)
        righteous = self.code[self.code.index("void Connected("):self.code.index("void Blocked(")]
        self.assertIn('Classes::CategoryOf(spellId) == "Primary"', righteous)
        self.assertIn("PayWrath(player, spellId, extra);", righteous)
        insurmountable = self.code[self.code.index("void Blocked("):self.code.index("void Register(")]
        self.assertIn('GainWrath(player, Id("Insurmountable"), InsurmountableWrath(Num("Insurmountable", "gain_resource")));', insurmountable)

    def test_the_second_six_are_dispatched(self):
        self.assertIn("Provoke::Landed(player, target, spellId); Passive::Landed(player, spellId);", self.crusader)
        self.assertIn("Passive::Multipliers(player, spellId, out);", self.crusader)
        self.assertIn("double DodgeFactor(Unit const* unit) { return Passive::DodgeFactor(unit); }", self.crusader)
        hooks = squeeze((MODULE / "src/combat/dc_combat_hooks.cpp").read_text(encoding="utf-8"))
        self.assertIn("dodge_chance = int32(dodge_chance * Crusader::DodgeFactor(defender));", hooks)
        self.assertIn("Crusader::DodgeFactor(player) > 0 && roll_chance_f(float(Abilities::DodgeChance(player) + Monk::Dodge(player)))", hooks)

    def test_the_sheet_rows_of_the_second_six(self):
        refresh = self.code[self.code.index("void Refresh("):self.code.index("class Update")]
        self.assertIn('Stat::BlockChance, ground, Numbers::Num(ground, "block_pct")', refresh)
        self.assertIn("DivineFortressPct(BlockChanceOf(player))", refresh)
        self.assertIn("Bucket::Percent", refresh)
        # Divine Fortress is read after the Block Chance (Hold Your Ground's too) is on the sheet.
        self.assertLess(refresh.index("Stats::Recompute(player);"), refresh.index("DivineFortressPct("))
        update = self.code[self.code.index("class Update"):self.code.index("class DamageHook")]
        self.assertIn("state.blockCenti != blockCenti", update)
        self.assertIn("PLAYERHOOK_ON_CREATURE_KILL", update)

    def test_indestructible_drops_a_fatal_hit_then_every_hit_for_its_seconds(self):
        damage = self.code[self.code.index("void Damage("):self.code.index("void Register(")]
        self.assertIn("dropped = fatal.Active(now) || (has && fatal.Save(now, damage, victim->GetHealth(),", damage)
        self.assertIn('Numbers::Num(id, "internal_cooldown_seconds")', damage)
        self.assertIn('Numbers::Num(id, "duration_seconds")', damage)
        self.assertIn("if (dropped) damage = 0;", damage)
        hook = self.code[self.code.index("class DamageHook"):self.code.index("// The cast of a Crusader skill")]
        self.assertIn("UNITHOOK_ON_DAMAGE", hook)
        killed = self.code[self.code.index("void OnPlayerCreatureKill("):self.code.index("class DamageHook")]
        self.assertIn('Heal(killer, killer, Id("Indestructible"), Classes::HealAtLevel(Num("Indestructible", "heal_per_hit_life"), killer->GetLevel()));', killed)
        mult = self.code[self.code.index("void Multipliers("):self.code.index("double AttackSpeed(")]
        self.assertIn('AddFactor(out, "Indestructible", Num("Indestructible", "damage_bonus_pct"));', mult)

    def test_holy_cause_lord_commander_and_wrathful(self):
        mult = self.code[self.code.index("void Multipliers("):self.code.index("double AttackSpeed(")]
        self.assertIn('AddFactor(out, "Holy Cause", Num("Holy Cause", "damage_bonus_pct"));', mult)
        self.assertIn('LordCommanderDamage(row->skill) && Passives::Has(player, "Lord Commander")', mult)
        self.assertIn('AddFactor(out, "Lord Commander", Num("Lord Commander", "damage_bonus_pct"));', mult)
        landed = self.code[self.code.index("void Landed("):self.code.index("double DodgeFactor(")]
        self.assertIn("info->GetSchoolMask() & SPELL_SCHOOL_MASK_HOLY", landed)
        self.assertIn('Num("Holy Cause", "heal_pct")', landed)
        cast = self.code[self.code.index("class CastHook"):self.code.index("void Multipliers(")]
        self.assertIn("ALLSPELLHOOK_ON_CAST", cast)
        self.assertIn("spell->IsTriggered()", cast)
        self.assertIn('WrathfulHeal(Classes::HealAtLevel(Num("Wrathful", "heal_per_hit_life"), player->GetLevel()), wrath)', cast)
        self.assertIn("player->GetSpellCooldownDelay(info->Id)", cast)
        self.assertIn('Numbers::Num(Id("Lord Commander"), "cooldown_reduction_pct", qualifier)', cast)
        self.assertIn("Combat::SendSkillCooldown(player, info->Id, left - cut);", cast)
        spent = self.code[self.code.index("double WrathSpent("):self.code.index("// Per Crusader")]
        self.assertIn("spell->GetSpellInfo()->PowerType != POWER_ENERGY", spent)
        self.assertIn("Resources::ToPoints(wrath, spell->GetPowerCost())", spent)

    def test_hold_your_ground_ends_dodging_for_the_crusader_that_holds_it(self):
        dodge = self.code[self.code.index("double DodgeFactor("):self.code.index("void Damage(")]
        self.assertIn('Passive::DodgeFactor(On(player, "Hold Your Ground"))', dodge)

    def test_the_last_six_sheet_rows_and_hooks(self):
        refresh = self.code[self.code.index("void Refresh("):self.code.index("class Update")]
        self.assertIn('Stat::Thorns, maiden, Numbers::Num(maiden, "thorns_pct")', refresh)
        self.assertIn('FineryPct(Numbers::Num(finery, "primary_stat_pct"), gems)', refresh)
        self.assertIn("Stat::Strength, finery", refresh)
        self.assertIn("Bucket::Percent", refresh)
        for stat, passive in (("Thorns", "maiden"), ("Strength", "finery")):
            self.assertIn(f"Stats::RemoveContribution(guid, Source::Passives, Stat::{stat}, {passive});", refresh)
        update = self.code[self.code.index("class Update"):self.code.index("class DamageHook")]
        self.assertIn('(On(player, "Iron Maiden") ? IronMaidenBit : 0u)', update)
        self.assertIn('(On(player, "Finery") ? FineryBit : 0u)', update)
        self.assertIn("(wanted & FineryBit) ? WornGems(player) : 0", update)
        gems = self.code[self.code.index("unsigned WornGems("):self.code.index("double BlockChanceOf(")]
        self.assertIn("Items::Get(item->GetGUID().GetCounter())", gems)
        self.assertIn('affix.kind == "gem"', gems)
        self.assertIn("EQUIPMENT_SLOT_START", gems)

    def test_renewal_and_insurmountable_both_answer_a_block(self):
        blocked = self.code[self.code.index("void Blocked("):self.code.index("double LongArmSeconds(")]
        self.assertIn('GainWrath(player, Id("Insurmountable")', blocked)
        self.assertIn('Heal(player, player, Id("Renewal"), RenewalHeal(Classes::HealAtLevel(Num("Renewal", "heal_life"), player->GetLevel())));', blocked)

    def test_blunt_and_towering_shield_name_their_skills(self):
        mult = self.code[self.code.index("void Multipliers("):self.code.index("double AttackSpeed(")]
        self.assertIn('BluntSkill(row->skill) && Passives::Has(player, "Blunt")', mult)
        self.assertIn('AddFactor(out, "Blunt", Num("Blunt", "damage_bonus_pct"));', mult)
        self.assertIn('ToweringDamageSkill(row->skill) && Passives::Has(player, "Towering Shield")', mult)
        self.assertIn('AddFactor(out, "Towering Shield", Num("Towering Shield", "damage_bonus_pct"));', mult)
        cast = self.code[self.code.index("class CastHook"):self.code.index("void Multipliers(")]
        self.assertIn('ToweringCooldownSkill(row->skill) && On(player, "Towering Shield")', cast)
        self.assertIn('cutPct = Num("Towering Shield", "cooldown_reduction_pct");', cast)
        self.assertIn("CooldownCut(left, cutPct)", cast)

    def test_long_arm_of_the_law_lengthens_every_active_effect_of_a_law(self):
        passive = self.code[self.code.index("double LongArmSeconds("):self.code.index("void Landed(")]
        self.assertIn('On(player, "Long Arm of the Law") ? Num("Long Arm of the Law", "duration_seconds") : 0.0', passive)
        laws = squeeze((MODULE / "src/classes/crusader/dc_crusader_laws.cpp").read_text(encoding="utf-8"))
        self.assertIn("double ActiveSeconds(Player* player, double seconds) { return Passive::LongArm(seconds, Passive::LongArmSeconds(player)); }", laws)
        self.assertIn("Millis(ActiveSeconds(player, Numbers::Num(base, flavour.window)))", laws)
        for name, token in (("valor", "duration_seconds"), ("justice", "duration_seconds"), ("justice", "absorb_duration_seconds"),
                            ("hope", "absorb_duration_seconds")):
            text = squeeze((MODULE / f"src/classes/crusader/dc_crusader_laws_of_{name}.cpp").read_text(encoding="utf-8"))
            self.assertIn(f'Laws::ActiveSeconds(player, Numbers::Num(spellId, "{token}"))', text, (name, token))

    def test_the_code_names_no_other_class(self):
        for name in ("Monk", "Barbarian", "Wizard", "Necromancer"):
            self.assertNotIn(name + "::", self.code)


class DecidedFromD3(unittest.TestCase):
    """the designer's answers from D3's sources (decisions.md 2026-10-21 "Cards closed from D3 sources", diablocraft-2v12l): the pins a
    return to the old readings must break."""

    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.sheet = (MODULE / "data/d3/crusader_passives.csv").read_text(encoding="utf-8")
        self.values = (MODULE / "data/d3/crusader_passive_values.csv").read_text(encoding="utf-8")

    def test_heavenly_strengths_cost_is_less_damage_dealt_and_never_movement_speed(self):
        # q-1021-31 (passive-heavenly-strength.txt:73-74): "Your damage dealt is reduced by 20%".
        row = [line for line in self.sheet.splitlines() if line.startswith('"Heavenly Strength"')][0]
        self.assertIn("Your damage dealt is reduced by {damage_dealt_reduction_pct}.", row)
        self.assertNotIn("movement", row.lower())
        tokens = [line for line in self.values.splitlines() if line.startswith('"Heavenly Strength"')]
        self.assertEqual(len(tokens), 1)
        self.assertIn('"damage_dealt_reduction_pct","","20","pct"', tokens[0])
        heavenly = self.code[self.code.index("void Multipliers("):self.code.index("double AttackSpeed(")]
        heavenly = heavenly[:heavenly.index('"Holy Cause"')]
        self.assertIn('AddFactor(out, "Heavenly Strength", -pct);', heavenly)
        self.assertNotIn("MovementSpeed", self.code)
        self.assertNotIn("MOVE_RUN", self.code)

    def test_holy_cause_heals_on_holy_damage_up_to_its_share_of_total_life(self):
        # q-1021-33 (passive-holy-cause.txt:73-74): "Whenever you deal Holy damage, you heal up to 1% of your total Life".
        row = [line for line in self.sheet.splitlines() if line.startswith('"Holy Cause"')][0]
        self.assertIn("Whenever you deal Holy damage, you heal up to {heal_pct} of your total Life.", row)
        tokens = [line for line in self.values.splitlines() if line.startswith('"Holy Cause"')]
        self.assertTrue(any('"heal_pct","","1","pct"' in line for line in tokens))
        landed = self.code[self.code.index("void Landed("):self.code.index("double DodgeFactor(")]
        self.assertIn('if (!On(player, "Holy Cause")) return;', landed)
        self.assertIn("HolyCauseHeal((info->GetSchoolMask() & SPELL_SCHOOL_MASK_HOLY) != 0, player->GetMaxHealth(), Num(\"Holy Cause\", \"heal_pct\"))", landed)
        # both of the engine's hit paths tell the Crusader's seam, which hands the hit to this
        resolve = squeeze((MODULE / "src/combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        self.assertGreaterEqual(resolve.count("Crusader::Landed(player, target,"), 2)
        crusader = squeeze((MODULE / "src/classes/crusader/dc_crusader.cpp").read_text(encoding="utf-8"))
        self.assertIn("Provoke::Landed(player, target, spellId); Passive::Landed(player, spellId);", crusader)


if __name__ == "__main__":
    unittest.main()
