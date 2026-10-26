#include "dc_wizard_auras.h"
#include "dc_wizard_arcane_orb.h"
#include "dc_wizard_armors.h"
#include "dc_wizard_archon.h"
#include "dc_wizard_buffs.h"
#include "dc_wizard_familiar.h"
#include "dc_wizard_frost_nova.h"
#include "dc_wizard_magic_missile.h"
#include "../dc_resources.h"
#include "../../combat/dc_item_powers.h"
#include "SpellAuraEffects.h"
#include "SpellScript.h"
#include <algorithm>
#include <cmath>
#include <random>

namespace DC::Combat::Wizard::Auras
{
    using namespace Shared;

    namespace
    {
        // The Wizard's buffs (generate_spells.py wizard_mechanics binds it):
        // the records keep their numbers in their slots, so only the slots
        // this file means to work carry an amount, and every other one reads
        // zero.
        class dc_wizard_buff final : public AuraScript
        {
            PrepareAuraScript(dc_wizard_buff);

            void Amount(AuraEffect const* effect, int32& amount, bool& canBeRecalculated)
            {
                canBeRecalculated = false;
                uint32 const id = GetId();
                Unit* owner = GetUnitOwner();
                int32 const misc = effect->GetMiscValue();
                switch (effect->GetAuraType())
                {
                    case SPELL_AURA_SCHOOL_ABSORB:
                        // "absorbing up to {absorb_capacity_life_pct} of your Life".
                        amount = owner ? int32(owner->GetMaxHealth() * Num(id, "absorb_capacity_life_pct") / 100 *
                                               ItemPowers::ShieldFactor(owner->ToPlayer()))
                                       : 0;
                        return;
                    case SPELL_AURA_MOD_MELEE_DAMAGE_TAKEN_PCT:
                        // Ice Armor: "reduces damage from melee attacks by".
                        amount = -int32(std::lround(Num(id, "damage_reduction_pct")));
                        return;
                    case SPELL_AURA_ADD_FLAT_MODIFIER:
                        // Prism, Power of the Storm: "Reduce the Arcane Power
                        // cost of all skills by {cost_reduction_resource}".
                        amount = misc == SPELLMOD_COST
                                     ? -int32(std::lround(Resources::ToUnits(Resources::ArcanePower,
                                                                             Num(id, "cost_reduction_resource"))))
                                     : 0;
                        return;
                    case SPELL_AURA_ADD_PCT_MODIFIER:
                        // Evocation: "Reduce all cooldowns by".
                        amount = misc == SPELLMOD_COOLDOWN && Numbers::Has(id, "cooldown_reduction_pct")
                                     ? -int32(std::lround(Num(id, "cooldown_reduction_pct")))
                                     : 0;
                        return;
                    case SPELL_AURA_DUMMY:
                    case SPELL_AURA_PERIODIC_DUMMY:
                        return;
                    default:
                        amount = 0;
                        return;
                }
            }

            void Tick(AuraEffect const* effect)
            {
                PreventDefaultAction();
                Player* player = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
                if (!player || !player->IsAlive())
                    return;
                uint32 const id = GetId();
                double const seconds = effect->GetAmplitude() / 1000.0;
                if (IsSkill(id, "Storm Armor"))
                    Armors::StormArmorTick(player, id);
                else if (IsRune(id, "Frozen Storm"))
                    Armors::FrozenStormTick(player, id, seconds);
                else if (Shells::HelperFor("Magic Missile - Conflagrate - burn") == id)
                    MagicMissile::BurnTick(player, id, seconds, GetUnitOwner(), GetStackAmount());
                else if (Shells::HelperFor("Arcane Orb - Scorch - wall") == id)
                    ArcaneOrb::WallTick(player, id, seconds);
                else if (IsRune(id, "Frozen Mist"))
                    FrostNova::MistTick(player, id, seconds);
            }

            void Applied(AuraEffect const*, AuraEffectHandleModes)
            {
                Player* player = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr;
                if (!player)
                    return;
                uint32 const id = GetId();
                // "Only one Armor may be active at a time": the spell_group the generator writes (the EXCLUSIVE rule over every
                // Armor shell), not a loop here (aura review row 9).
                if (IsSkill(id, "Familiar"))
                    Familiar::SummonFamiliar(player);
                if (IsSkill(id, "Archon"))
                    Archon::EnterArchon(player, id);
                Buffs::Refresh(player);
            }

            void Removed(AuraEffect const*, AuraEffectHandleModes)
            {
                Player* player = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr;
                if (!player)
                    return;
                uint32 const id = GetId();
                // "When Diamond Skin fades, diamond shards explode".
                if (IsRune(id, "Diamond Shards") && player->IsAlive())
                    Combat::StrikeArea(player, id, player->GetPosition(), Num(id, "radius_yards"));
                if (IsSkill(id, "Familiar"))
                {
                    std::lock_guard<std::recursive_mutex> guard(mutex);
                    State& state = StateOf(player);
                    Despawn(player, state.familiar);
                    state.familiar.Clear();
                }
                if (IsSkill(id, "Archon"))
                    Archon::LeaveArchon(player);
                Buffs::Refresh(player);
            }

            void Register() override
            {
                DoEffectCalcAmount += AuraEffectCalcAmountFn(dc_wizard_buff::Amount, EFFECT_ALL, SPELL_AURA_ANY);
                // GitHub #64: the core drops a handler whose effect index or aura
                // name the record does not carry, and logs an error for each.
                // The tick binds only on a record that has a periodic dummy
                // (Storm Armor, Frozen Storm, Frozen Mist, Conflagrate's burn);
                // every other buff has none, so binding it there was 42 errors.
                if (HasAuraEffect(m_scriptSpellId, SPELL_AURA_PERIODIC_DUMMY))
                    OnEffectPeriodic +=
                        AuraEffectPeriodicFn(dc_wizard_buff::Tick, EFFECT_ALL, SPELL_AURA_PERIODIC_DUMMY);
                AfterEffectApply +=
                    AuraEffectApplyFn(dc_wizard_buff::Applied, EFFECT_0, SPELL_AURA_ANY, AURA_EFFECT_HANDLE_REAL);
                AfterEffectRemove +=
                    AuraEffectRemoveFn(dc_wizard_buff::Removed, EFFECT_0, SPELL_AURA_ANY, AURA_EFFECT_HANDLE_REAL);
            }
        };
    } // namespace

    void RegisterScripts()
    {
        RegisterSpellScript(dc_wizard_buff);
    }
} // namespace DC::Combat::Wizard::Auras
