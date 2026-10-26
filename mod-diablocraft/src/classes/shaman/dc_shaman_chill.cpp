/*
 * The Shaman's chill: what the effects file's Slow puts on an enemy, and the look at whether it is there.
 */

#include "dc_shaman_chill.h"
#include "dc_shaman_effects.h"
#include "Player.h"
#include "Unit.h"

namespace DC::Combat::Shaman
{
    namespace
    {
        // The stock "Dazed" the effects file's Slow puts on (one MOD_DECREASE_SPEED effect).
        constexpr std::uint32_t SlowHold = 50259;
        // The stock stun the effects file's Stun and Freeze put on (one MOD_STUN effect).
        constexpr std::uint32_t StunHold = 15878;
    } // namespace

    void Chill(Player* player, Unit* target, double pct, double seconds)
    {
        Slow(player, target, pct, seconds);
    }

    bool Chilled(Player* player, Unit const* target)
    {
        return player && target && target->HasAura(SlowHold, player->GetGUID());
    }

    bool Held(Player* player, Unit const* target)
    {
        return player && target && target->HasAura(StunHold, player->GetGUID());
    }
} // namespace DC::Combat::Shaman
