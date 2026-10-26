/*
 * World of DiabloCraft - an item's burning trail, Combat's side (N-AREA; Fire Walkers). The rules are
 * dc_item_trail_math.h.
 */

#ifndef DC_ITEM_TRAIL_H
#define DC_ITEM_TRAIL_H

#include <cstdint>
#include <string>

class Player;

namespace DC::Combat::ItemTrail
{
    // A `burn_trail` row fired on the `tick` clock (ItemPowers::Fire, outside its lock): drops a patch of fire under the
    // wearer of the item `owner` while they move, and burns every enemy standing in any live patch for `perSecondPct` percent
    // of weapon damage per second (the item's rolled number), paid for the time since the last pulse (`periodSeconds` is
    // the clock's period, the row's icd_seconds). The damage is the wearer's own under the item's `hit` record, not a hit of a skill.
    void Burn(Player* player, std::string const& owner, double perSecondPct, double periodSeconds);

    // The wearer's patches go with the player (logout).
    void Clear(std::uint64_t guid);
} // namespace DC::Combat::ItemTrail

#endif
