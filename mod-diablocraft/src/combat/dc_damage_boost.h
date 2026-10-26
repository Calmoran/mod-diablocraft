/*
 * World of DiabloCraft - a timed boost to the damage a player deals, the shared piece: a skill, an item or a buff that
 * says "N% more damage for S seconds" to a player (and its allies) gives it here, and the hit reads it as a multiplier
 * of its own. A source is a key of the caller's; a second boost under the same key replaces the first, boosts under
 * different keys multiply. The rules are dc_damage_boost_math.h.
 */

#ifndef DC_DAMAGE_BOOST_H
#define DC_DAMAGE_BOOST_H

#include "dc_damage_buckets.h"

#include <cstdint>

class Player;

namespace DC::Combat::DamageBoost
{
    // `target` deals `pct` percent more damage for `seconds` from now, under `key`. No percent or no seconds takes the
    // key's boost off.
    void Hold(Player* target, std::uint32_t key, double pct, double seconds);
    // Adds one multiplier for each boost `player` holds now (Combat::ComputeHit, beside the other multipliers of their
    // own).
    void Multipliers(Player const* player, Factors& out);
    // Takes every boost of the player away.
    void Clear(Player const* player);
    void RegisterScripts();
} // namespace DC::Combat::DamageBoost

#endif
