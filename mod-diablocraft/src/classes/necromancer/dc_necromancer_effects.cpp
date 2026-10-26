/*
 * The Necromancer's holds on enemies, its heal and the Essence its skills generate: the small pieces more than one skill
 * of the class calls.
 */

#include "dc_necromancer_common.h"
#include "dc_necromancer_life_math.h"
#include "dc_necromancer_simulacrum.h"
#include "dc_necromancer_passives.h"
#include "../../combat/dc_item_powers.h"

#include "SpellAuraEffects.h"
#include "SpellMgr.h"

#include <cmath>

namespace DC::Combat::Necromancer
{
    namespace
    {
        // Stock "Ice Blast": one instant MOD_STUN effect, mechanic STUN - the hold the rift elites freeze a player with.
        constexpr std::uint32_t StunHold = 15878;
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, Snare mechanic; its amount is set to the slow.
        constexpr std::uint32_t SlowHold = 50259;
        // Stock "Slow" (10371): one MOD_MELEE_HASTE effect on an enemy; its amount is set to the attack speed it takes off.
        constexpr std::uint32_t WearyHold = 10371;
        // Stock "Fear" (5782): one MOD_FEAR effect, no other: an enemy Feared runs from the Necromancer.
        constexpr std::uint32_t FearHold = 5782;

        constexpr Resources::Resource const& Essence = *Resources::Find("Necromancer", "essence");

        // A stock control aura of `seconds` on `target`, a second one restarting it.
        bool Hold(Player* player, Unit* target, std::uint32_t aura, double seconds, int amount = 0)
        {
            if (!player || !target || seconds <= 0 || !target->IsAlive())
                return false;
            target->RemoveAurasDueToSpell(aura, player->GetGUID());
            Aura* hold = player->AddAura(aura, target);
            if (!hold)
                return false;
            if (amount)
                if (AuraEffect* effect = hold->GetEffect(EFFECT_0))
                    effect->ChangeAmount(amount);
            hold->SetMaxDuration(int32(seconds * 1000));
            hold->SetDuration(int32(seconds * 1000));
            return true;
        }
    } // namespace

    void Stun(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, StunHold, seconds);
    }

    void Slow(Player* player, Unit* target, double pct, double seconds)
    {
        if (pct > 0)
            Hold(player, target, SlowHold, seconds, -static_cast<int>(std::lround(pct)));
    }

    void Unslow(Player* player, Unit* target)
    {
        if (player && target)
            target->RemoveAurasDueToSpell(SlowHold, player->GetGUID());
    }

    void Fear(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, FearHold, seconds);
    }

    void Weary(Player* player, Unit* target, double pct, double seconds)
    {
        if (pct > 0)
            Hold(player, target, WearyHold, seconds, -static_cast<int>(std::lround(pct)));
    }

    void SpendLife(Player* player, double pct)
    {
        if (!player || !player->IsAlive())
            return;
        // Simulacrum's Blood Debt cuts every Life cost while it stands.
        if (double const cost = LifeCost(player->GetHealth(), player->GetMaxHealth(), pct * Simulacrum::LifeCostShare(player)); cost >= 1.0)
        {
            // Rathma's Shield: no Life is lost in its window; Blood for Blood: a globe's stack pays the cost.
            if (Passive::LifeLocked(player) || Passive::WaivesLifeCost(player))
                return;
            player->ModifyHealth(-int32(cost));
            Passive::LifeLost(player, cost);
        }
    }

    void Heal(Player* player, std::uint32_t spellId, double amount)
    {
        if (!player || !player->IsAlive() || amount <= 0)
            return;
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
        {
            HealInfo heal(player, player, uint32(std::min(amount, double(UINT32_MAX))), info, SPELL_SCHOOL_MASK_NORMAL);
            player->HealBySpell(heal);
        }
    }

    void PayEssence(Player* player, std::uint32_t spellId, double points)
    {
        auto const* row = Shells::FindAbility(spellId);
        if (!row || points <= 0 || Classes::ClassIdOf(player) != Essence.classId || !Resources::Displayed(player, Essence))
            return;
        Resources::Energize(player, Essence, spellId,
                            points * ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct") * ItemPowers::GenerationFactor(player));
    }
} // namespace DC::Combat::Necromancer
