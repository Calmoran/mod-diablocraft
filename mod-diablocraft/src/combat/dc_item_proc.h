/*
 * World of DiabloCraft - an item's weapon-damage proc, Combat's side (N-WPROC; Storm Crow's fiery ball). The rules are
 * dc_item_proc_math.h.
 */

#ifndef DC_ITEM_PROC_H
#define DC_ITEM_PROC_H

#include <string>

class Player;
class Unit;

namespace DC::Combat::ItemProc
{
    // A `proc_damage` row fired on a hit (ItemPowers::Fire, outside its lock): the item `owner`'s ball at `target`, the
    // enemy the hit struck, when the item's chance falls (`chancePct`, scaled by the hit's proc coefficient
    // `coefficient`, 0: none) and the item's damage tunable is set. The ball is the wearer's own damage under the
    // item's `hit` record, not a hit of a skill.
    void Damage(Player* player, Unit* target, std::string const& owner, double chancePct, double coefficient);
} // namespace DC::Combat::ItemProc

#endif
