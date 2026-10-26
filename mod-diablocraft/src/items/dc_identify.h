/*
 * World of DiabloCraft - identification of unidentified items.
 *
 * A legendary or set drop arrives as an unrolled
 * shell and is ROLLED AT IDENTIFY, for the player who identifies it. Two ways
 * in: right-click the item (one item, identify_item_cast_seconds) and the hub
 * Tome of Identification (every shell in the bags, identify_tome_cast_seconds).
 *
 * Public surface of the identify half of the items folder.
 */

#ifndef DC_IDENTIFY_H
#define DC_IDENTIFY_H

#include <cstdint>
#include <string>

class Item;
class Player;

namespace DC::Identify
{
    // Rolls one shell for this player and puts the result in the shell's own bag
    // slot. `error` is set and false returned when the item is not a shell, the row
    // is missing, or the roll could not be committed - never a partial result.
    bool IdentifyOne(Player* player, Item* shell, std::string& error);

    // Every shell in the player's bags, D3's tome behaviour. Returns how many were
    // identified; a failure on one is logged and the rest continue.
    unsigned IdentifyAll(Player* player);

    void RegisterScripts();
} // namespace DC::Identify

#endif // DC_IDENTIFY_H
