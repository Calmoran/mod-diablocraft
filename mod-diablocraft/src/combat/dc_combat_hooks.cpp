// Combat: the core's melee, defence and damage hooks (no auto attack, always hit, monster hits, Fury from damage taken).
#include "dc_combat_internal.h"
#include "../classes/follower/dc_follower_skills.h"

namespace DC::Combat
{
    namespace
    {
        // C1: no auto-attack. A Diablocraft character never swings on its own; damage
        // comes only from a skill the player pressed.
        //
        // Melee auto-attack begins in one place: WorldSession::HandleAttackSwingOpcode,
        // which the client reaches by right-clicking a target or pressing the attack
        // key. Dropping CMSG_ATTACKSWING before that handler runs means the swing state
        // (UNIT_STATE_MELEE_ATTACKING) is never set, so no swing timer starts, no
        // SMSG_ATTACKSTART is sent, and the client's attack toggle never lights. That
        // is the whole fix; no core change and no client patch. Creature auto-attack is
        // untouched, because this only inspects player sessions.
        class CombatNoAutoAttack final : public ServerScript
        {
        public:
            CombatNoAutoAttack()
                : ServerScript("dc_combat_no_auto_attack", {SERVERHOOK_CAN_PACKET_RECEIVE})
            {
            }

            bool CanPacketReceive(WorldSession* session, WorldPacket const& packet) override
            {
                if (packet.GetOpcode() != CMSG_ATTACKSWING)
                    return true;
                // Every playable D3 class, from class data;
                // other classes keep stock combat.
                return !session || !HitsThroughCombat(session->GetPlayer());
            }
        };

        // Catch a swing started by a route other than CMSG_ATTACKSWING (a charge effect
        // or stray triggered cast). AttackStop clears the state and tells the client.
        class CombatNoAutoAttackUpdate final : public PlayerScript
        {
        public:
            CombatNoAutoAttackUpdate()
                : PlayerScript("dc_combat_no_auto_attack_update", {PLAYERHOOK_ON_UPDATE})
            {
            }

            void OnPlayerUpdate(Player* player, uint32) override
            {
                if (!HitsThroughCombat(player))
                    return;
                if (player->HasUnitState(UNIT_STATE_MELEE_ATTACKING))
                    player->AttackStop();
            }
        };

        // 02 §5: D3 has no miss, no dodge and no parry on
        // either side. Every shell generate_spells.py emits carries
        // SPELL_ATTR3_ALWAYS_HIT, which settles every spell in the game, ours and the
        // ones the module casts for a monster. A creature's plain melee swing is not a
        // spell and goes through WoW's hit table instead, so the avoid rolls are zeroed
        // here before the roll happens (Unit::RollMeleeOutcomeAgainst).
        //
        // WoW's block is zeroed with them on purpose: D3 does have Block, but it is a
        // flat reduction of an incoming hit that belongs in our own mitigation math
        // beside Armor and resists, never a hit-table outcome.
        class CombatAlwaysHit final : public UnitScript
        {
        public:
            CombatAlwaysHit()
                : UnitScript("dc_combat_always_hit", true, {UNITHOOK_ON_BEFORE_ROLL_MELEE_OUTCOME_AGAINST})
            {
            }

            void OnBeforeRollMeleeOutcomeAgainst(Unit const* attacker, Unit const* victim, WeaponAttackType, int32&,
                                                 int32&, int32&, int32&, int32&, int32& miss_chance,
                                                 int32& dodge_chance, int32& parry_chance, int32& block_chance) override
            {
                // Every D3-sheeted side, from class data;
                // a stock player keeps the native table.
                Player const* defender = victim ? victim->ToPlayer() : nullptr;
                if (!HitsThroughCombat(defender) && !HitsThroughCombat(attacker ? attacker->ToPlayer() : nullptr))
                    return;
                miss_chance = parry_chance = block_chance = 0;
                miss_chance = int32((Monk::MissChance(attacker) + Shaman::MissChance(attacker)) * 100);
                // D3 Dodge only where the sheet's skills supply it.
                dodge_chance = HitsThroughCombat(defender) ? int32((Abilities::DodgeChance(defender) + Monk::Dodge(defender)) * 100) : 0;
                dodge_chance = int32(dodge_chance * Crusader::DodgeFactor(defender));
            }
        };

        // The one place a core-owned incoming number is turned into a D3 one.
        // Every core hook that hands us damage on its way to a player calls this
        // and nothing else: the factor is DamageTakenFactor's single copy of
        // 01-stats §3, and the WoW armor/resistance fields are held at 0 so the
        // core's subsequent mitigation steps subtract nothing on top.
        //
        // Re-zero on every hit: stat-modifier auras and item equip rebuild
        // armor/resistances through Player::UpdateArmor/UpdateAllResistances.
        // Display() writes zero too; this guarantees the values a hit reads.
        // The setters skip writes when the fields already hold zero.
        //
        // False means this victim has no D3 sheet, and its defence is still the
        // core's to compute: leave its defence fields and mitigation alone
        // rather than zero one and replace it with nothing.
        template<typename Amount>
        bool ApplyPlayerDefence(Player* player, unsigned schoolMask, Amount& damage, bool melee, Unit* attacker)
        {
            // Every class with a D3 sheet: its
            // Display() zeroes the same armor and resistance fields, so leaving
            // a Wizard on the core's mitigation would leave it with none.
            if (!HitsThroughCombat(player))
                return false;
            auto const mitigated = Mitigate(player, schoolMask, static_cast<double>(damage), nullptr, melee, attacker);
            if (!mitigated)
                return false;
            player->SetArmor(0);
            for (unsigned school = SPELL_SCHOOL_HOLY; school < MAX_SPELL_SCHOOL; ++school)
                player->SetResistance(static_cast<SpellSchools>(school), 0);
            damage = static_cast<Amount>(std::max(0.0, *mitigated));
            // What the worn powers prevent of what is left, and heal (N-PREVENT).
            std::uint32_t left = static_cast<std::uint32_t>(damage);
            ItemPowers::Prevent(player, schoolMask, left);
            damage = static_cast<Amount>(left);
            return true;
        }

        // The core dispatches UNITHOOK_MODIFY_PERIODIC_DAMAGE_AURAS_TICK from
        // the periodic HEAL tick as well (SpellAuraEffects.cpp
        // HandlePeriodicHealAurasTick), handing it the heal in the same uint32,
        // so mitigating everything the hook sees would cut the player's own
        // healing by the same factor. Only a spell that actually carries a
        // damaging periodic effect - and no healing one - is treated as damage.
        bool PeriodicDealsDamage(SpellInfo const* info)
        {
            if (!info)
                return false;
            bool damaging = false;
            for (auto const& effect : info->Effects)
            {
                switch (effect.ApplyAuraName)
                {
                    case SPELL_AURA_PERIODIC_DAMAGE:
                    case SPELL_AURA_PERIODIC_DAMAGE_PERCENT:
                    case SPELL_AURA_PERIODIC_LEECH:
                        damaging = true;
                        break;
                    case SPELL_AURA_PERIODIC_HEAL:
                    case SPELL_AURA_OBS_MOD_HEALTH:
                        return false;
                    default:
                        break;
                }
            }
            return damaging;
        }

        // 02 §5, the plain creature swing. This half of the
        // monster hit never reached DealMonsterHit - only rift abilities and
        // affixes call that - so a swing was mitigated by WoW's armor formula
        // and by nothing of ours, and D3 resistances did not touch it at all.
        // The core fires this hook in Unit::CalculateMeleeDamage eight lines
        // before its own armor step, so the D3 defence factor is applied here,
        // against the attacker's own melee school.
        class CombatMonsterMelee final : public UnitScript
        {
        public:
            CombatMonsterMelee()
                : UnitScript("dc_combat_monster_melee", true, {UNITHOOK_MODIFY_MELEE_DAMAGE})
            {
            }
            void ModifyMeleeDamage(Unit* target, Unit* attacker, uint32& damage) override
            {
                unsigned const school =
                    attacker ? unsigned(attacker->GetMeleeDamageSchoolMask()) : unsigned(SPELL_SCHOOL_MASK_NORMAL);
                damage=uint32(damage*Abilities::IncomingFactor(attacker)*Wizard::IncomingFactor(attacker) * Monk::IncomingFactor(attacker));
                ApplyPlayerDefence(target ? target->ToPlayer() : nullptr, school, damage, true, attacker);
                if(damage>0)Passives::Taken(target?target->ToPlayer():nullptr,school,false,damage);
                if(damage>0)Monk::Taken(target,attacker);
                if(damage>0)Crusader::Taken(target,attacker,damage);
                Abilities::ReflectMelee(target?target->ToPlayer():nullptr,attacker,damage);
                Wizard::Incoming(target ? target->ToPlayer() : nullptr, attacker, damage, Wizard::Attack::Melee);
                GemPowers::Incoming(target ? target->ToPlayer() : nullptr, attacker, damage);
                GemPowers::PetIncoming(target, damage); // Enforcer, rank 25: a pet's hit taken
            }
        };

        // The other two halves of the monster hit. Zeroing the WoW armor field
        // for the swing also emptied the core's armor step for a
        // creature's physical SPELL, its ranged hit and every damage-over-time
        // tick, and none of those ever reached DealMonsterHit - that is rift
        // abilities and affixes only - so they arrived with nothing reducing
        // them. Rift creatures keep casting their native WoW abilities, so this
        // is the live path, not a spare one.
        //
        // Both core hooks run before the core's armor, crit, block, resilience
        // and absorb steps, which is the same position the melee hook has, so
        // all three apply the one factor the same way. The school is the
        // SpellInfo's, not the attacker's melee school: a creature swinging a
        // sword can cast Fire.
        //
        // Nothing reaching either hook also reaches DealMonsterHit or
        // ModifyMeleeDamage:
        //   - DealMonsterHit fills its own SpellNonMeleeDamage and calls
        //     DealSpellDamage, which never enters Unit::CalculateSpellDamageTaken,
        //     the only place ModifySpellDamageTaken is dispatched from. The
        //     affix/ability shell a rift also casts for the visual carries
        //     Effect_1 = DUMMY with zero base points (generate_spells.py), so
        //     Spell.cpp's `m_damage > 0` damage branch is never entered for it.
        //   - ModifyMeleeDamage is dispatched only from Unit::CalculateMeleeDamage,
        //     which returns for anything but BASE_ATTACK and OFF_ATTACK. Every
        //     spell, SPELL_DAMAGE_CLASS_MELEE and _RANGED ones included, goes
        //     through CalculateSpellDamageTaken instead.
        //   - The core's three periodic dispatch sites are disjoint handlers
        //     (damage tick, health-leech tick, heal tick), and the mana-burn and
        //     proc-trigger-damage paths call CalculateSpellDamageTaken only.
        class CombatMonsterSpell final : public UnitScript
        {
        public:
            CombatMonsterSpell()
                : UnitScript("dc_combat_monster_spell", true,
                             {UNITHOOK_MODIFY_SPELL_DAMAGE_TAKEN, UNITHOOK_MODIFY_PERIODIC_DAMAGE_AURAS_TICK})
            {
            }

            void ModifySpellDamageTaken(Unit* target, Unit* attacker, int32& damage, SpellInfo const* spellInfo) override
            {
                if (!spellInfo || damage <= 0)
                    return;
                if (Player* player=target?target->ToPlayer():nullptr)
                    if (!spellInfo->IsTargetingArea() && Crusader::DodgeFactor(player) > 0 && roll_chance_f(float(Abilities::DodgeChance(player) + Monk::Dodge(player)))) { damage=0; return; }
                damage=int32(damage*Abilities::IncomingFactor(attacker)*Wizard::IncomingFactor(attacker) * Monk::IncomingFactor(attacker));
                ApplyPlayerDefence(target ? target->ToPlayer() : nullptr, unsigned(spellInfo->GetSchoolMask()), damage,
                                   spellInfo->DmgClass == SPELL_DAMAGE_CLASS_MELEE, attacker);
                if(damage>0)Passives::Taken(target?target->ToPlayer():nullptr,unsigned(spellInfo->GetSchoolMask()),spellInfo->DmgClass==SPELL_DAMAGE_CLASS_RANGED,damage);
                if(damage>0)Monk::Taken(target,attacker);
                if(damage>0)Crusader::Taken(target,attacker,damage);
                if (damage > 0)
                {
                    uint32 taken = uint32(damage);
                    Wizard::Incoming(target ? target->ToPlayer() : nullptr, attacker, taken,
                                     spellInfo->DmgClass == SPELL_DAMAGE_CLASS_RANGED ? Wizard::Attack::Ranged
                                     : spellInfo->DmgClass == SPELL_DAMAGE_CLASS_MELEE ? Wizard::Attack::Melee
                                                                                         : Wizard::Attack::Spell);
                    GemPowers::Incoming(target ? target->ToPlayer() : nullptr, attacker, taken);
                    damage = int32(taken);
                }
                if (damage > 0)
                {
                    uint32 taken = uint32(damage);
                    GemPowers::PetIncoming(target, taken); // Enforcer, rank 25
                    damage = int32(taken);
                }
            }

            void ModifyPeriodicDamageAurasTick(Unit* target, Unit* attacker, uint32& damage, SpellInfo const* spellInfo) override
            {
                if (!damage || !PeriodicDealsDamage(spellInfo))
                    return;
                damage=uint32(damage*Abilities::IncomingFactor(attacker)*Wizard::IncomingFactor(attacker) * Monk::IncomingFactor(attacker));
                ApplyPlayerDefence(target ? target->ToPlayer() : nullptr, unsigned(spellInfo->GetSchoolMask()), damage,
                                   spellInfo->DmgClass == SPELL_DAMAGE_CLASS_MELEE, attacker);
                if(damage>0)Passives::Taken(target?target->ToPlayer():nullptr,unsigned(spellInfo->GetSchoolMask()),spellInfo->DmgClass==SPELL_DAMAGE_CLASS_RANGED,damage);
                Wizard::Incoming(target ? target->ToPlayer() : nullptr, attacker, damage, Wizard::Attack::Periodic);
                GemPowers::Incoming(target ? target->ToPlayer() : nullptr, attacker, damage);
                GemPowers::PetIncoming(target, damage); // Enforcer, rank 25
            }
        };

        // 02 §4: +0.5 Fury per 1% of Life lost.
        class CombatDamage final : public UnitScript
        {
        public:
            CombatDamage()
                : UnitScript("dc_combat_damage", true, {UNITHOOK_ON_DAMAGE})
            {
            }
            void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override
            {
                // A hit that landed pays a Shaman's Elemental Shield its charge even when every point of it was absorbed (damage 0).
                Shaman::Damaged(attacker, victim, damage);
                Player* player = victim ? victim->ToPlayer() : nullptr;
                if (!player || !damage)
                    return;
                // A transformation's free save comes before an item's, which is destroyed by saving.
                Crusader::Fatal(player, damage);
                DemonHunter::Fatal(player, damage);
                Shaman::Fatal(player, damage);
                Classes::Follower::Fatal(player, damage);
                if (Barbarian(player))
                {
                    Classes::Ancients::Redirect(player, damage);
                    Passives::Fatal(player,damage);
                }
                // After Nerves of Steel, so the Barbarian's free save is used before an item's
                ItemPowers::Fatal(player, damage);
                if (!Barbarian(player))
                    return;
                if (!GemPowers::PayingStagger())
                    Abilities::Taken(player,attacker,damage); // Revenge: a hit, not Moratorium's payment of one
                double const maxLife = player->GetMaxHealth();
                if (maxLife <= 0)
                    return;
                double const percentLost = 100.0 * damage / maxLife;
                ChangeFury(player, percentLost * FuryPerPercentLife());
            }
        };
    } // namespace

    void RegisterHookScripts()
    {
        new CombatNoAutoAttack();
        new CombatNoAutoAttackUpdate();
        new CombatAlwaysHit();
        new CombatMonsterMelee();
        new CombatMonsterSpell();
        new CombatDamage();
    }
} // namespace DC::Combat
