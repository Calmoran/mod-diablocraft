/*
 * The Demon Hunter's holds on enemies: the small pieces more than one skill of the class calls.
 */

#include "dc_demon_hunter_effects.h"
#include "dc_demon_hunter_passives.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>

namespace DC::Combat::DemonHunter
{
    namespace
    {
        // Stock "Ice Blast": one instant MOD_STUN effect, mechanic STUN.
        constexpr std::uint32_t StunHold = 15878;
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, Snare mechanic; its amount is set to the slow.
        constexpr std::uint32_t SlowHold = 50259;
        // Stock "Earthgrab": one MOD_ROOT effect, mechanic Root - the Immobilize.
        constexpr std::uint32_t RootHold = 64695;
        // Stock "Super Invis": one MOD_INVISIBILITY effect (general, amount 9999), infinite and broken by nothing.
        constexpr std::uint32_t InvisibleHold = 8149;

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

    void Slow(Player* player, Unit* target, double pct, double seconds)
    {
        if (pct > 0)
        {
            Hold(player, target, SlowHold, seconds, -static_cast<int>(std::lround(pct)));
            Passive::Slowed(player, target);
        }
    }

    void Unslow(Player* player, Unit* target)
    {
        if (player && target)
            target->RemoveAurasDueToSpell(SlowHold, player->GetGUID());
    }

    void Stun(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, StunHold, seconds);
    }

    void Vanish(Player* player, double seconds)
    {
        Hold(player, player, InvisibleHold, seconds);
    }

    void Root(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, RootHold, seconds);
    }

    void Heal(Player* player, std::uint32_t spellId, double amount)
    {
        if (!player || !player->IsAlive() || amount <= 0)
            return;
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
        {
            HealInfo heal(player, player, std::uint32_t(std::min(amount, double(UINT32_MAX))), info,
                          SPELL_SCHOOL_MASK_NORMAL);
            player->HealBySpell(heal);
        }
    }
} // namespace DC::Combat::DemonHunter
