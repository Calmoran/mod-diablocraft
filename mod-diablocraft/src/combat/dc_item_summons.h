/*
 * World of DiabloCraft - the allies a legendary item summons, Combat's side (N-SUMMON; Bovine Bardiche).
 *
 * World makes the creature and moves it (src/rifts/dc_ally.h; docs/contracts/legendary-world-pieces.md, N-SUMMON); this
 * summons it and owns its time, its Life and its damage. The rules are dc_item_summon_math.h.
 */

#ifndef DC_ITEM_SUMMONS_H
#define DC_ITEM_SUMMONS_H

class Player;

namespace DC::Combat::ItemSummons
{
    // Bovine Bardiche's `summon_herd` row, fired on a hit (ItemPowers::Fire, outside its lock): `cows` cows beside the
    // player when the internal cooldown is over and the chance falls. `coefficient` is the hit's proc coefficient (0:
    // none).
    void Herd(Player* player, unsigned cows, double coefficient);

    // The cows' swing (Rifts::Ally::OnSwing). At startup.
    void RegisterScripts();
} // namespace DC::Combat::ItemSummons

#endif
