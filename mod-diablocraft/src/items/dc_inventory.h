/*
 * World of DiabloCraft - the inventory screen's server half
 * (12-ui §2).
 *
 * The Diablocraft addon draws D3's inventory panel in place of WoW's character
 * sheet. Two things reach it from here and nothing else decides anything:
 *
 *   the intent   .dc inventory equip <bag index> / unequip <equipment slot>,
 *                run by lua/aio/dc_inventory.lua on the player's right-click.
 *                Every rule is the core's own CanEquipItem/SwapItem path, plus
 *                alive and out of combat (12-ui §3).
 *
 *   the stats    .dc inventory sheet pushes the 22 stats and the three D3
 *                summary values to the addon as a DCSHEET addon whisper, the
 *                same channel DCPARAGON and DCECON already use. They are stat
 *                maths, so they are computed in C++ and never in Lua
 *                (00 §5, 12-ui §2), and Eluna cannot call into this module.
 *
 * Index encoding is the stash's, unchanged (dc_stash.cpp:229):
 *   bag index   = container * 100 + slot, container 255 being the backpack
 *   equip index = the WoW equipment slot, 0-18; potion uses virtual slot 100
 */

#ifndef DC_INVENTORY_H
#define DC_INVENTORY_H

#include <cstdint>
#include <optional>

class Player;

namespace DC::Inventory
{
    std::uint32_t ActivePotionSpell(Player* player);
    // The power roll the slotted potion keeps; none when the slot is empty or its potion has no roll.
    std::optional<double> ActivePotionRoll(Player* player);
    // Sends the DCSHEET block to this player's addon. Called by the .dc
    // inventory sheet command that the screen's Lua runs immediately before it
    // pushes its own AIO snapshot, so the block is always on the wire first.
    void PushSheet(Player* player);

    void RegisterScripts();
} // namespace DC::Inventory

#endif // DC_INVENTORY_H
