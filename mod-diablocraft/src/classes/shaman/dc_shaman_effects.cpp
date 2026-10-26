/*
 * World of DiabloCraft - the Shaman's holds on enemies and its heal: the small pieces more than one skill of the class
 * calls.
 */

#include "dc_shaman_effects.h"
#include "../../combat/dc_combat.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"

#include <algorithm>
#include <cmath>

namespace DC::Combat::Shaman
{
    namespace
    {
        // Stock "Ice Blast": one instant MOD_STUN effect, mechanic STUN - the hold the rift elites freeze a player
        // with.
        constexpr std::uint32_t StunHold = 15878;
        // Stock "Dazed" (50259): one MOD_DECREASE_SPEED effect, Snare mechanic; its amount is set to the slow.
        constexpr std::uint32_t SlowHold = 50259;

        // Stock "Earthgrab": one MOD_ROOT effect, mechanic Root.
        constexpr std::uint32_t RootHold = 64695;

        // A stock aura of `seconds` on `target`, its first effect set to `amount` (0 keeps the record's); a second one
        // of the Shaman's restarts it.
        void Hold(Player* player, Unit* target, std::uint32_t aura, double seconds, int amount = 0)
        {
            if (!player || !target || seconds <= 0 || !target->IsAlive())
                return;
            target->RemoveAurasDueToSpell(aura, player->GetGUID());
            Aura* hold = player->AddAura(aura, target);
            if (!hold)
                return;
            if (amount)
                if (AuraEffect* effect = hold->GetEffect(EFFECT_0))
                    effect->ChangeAmount(amount);
            hold->SetMaxDuration(int32(seconds * 1000));
            hold->SetDuration(int32(seconds * 1000));
        }
    } // namespace

    void Stun(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, StunHold, seconds);
    }

    void Root(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, RootHold, seconds);
    }

    void Freeze(Player* player, Unit* target, double seconds)
    {
        Hold(player, target, StunHold, seconds);
    }

    void Slow(Player* player, Unit* target, double pct, double seconds)
    {
        if (pct > 0)
            Hold(player, target, SlowHold, seconds, -static_cast<int>(std::lround(pct)));
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

    bool IsElite(Unit const* enemy)
    {
        return enemy && !Combat::IsLesser(enemy);
    }
} // namespace DC::Combat::Shaman
