/*
 * World of DiabloCraft - the rules of a block an item changes (N-BLOCK; Blood Brother).
 *
 * No core dependency, so scripts/tests/legendaries/test_item_power_blood_brother.py compiles this exact header and
 * drives it. The block roll and the aura of the armed attack are dc_combat.cpp Mitigate and dc_item_powers.cpp.
 */

#ifndef DC_ITEM_BLOCK_MATH_H
#define DC_ITEM_BLOCK_MATH_H

#include <algorithm>
#include <string>

namespace DC::Combat::ItemBlock
{
    // The chance a hit on the wearer is blocked, in percent: the sheet's Block Chance (already held to the total cap)
    // plus what the worn items add, held to the same cap. An item that adds nothing leaves the sheet's number as it is.
    inline double Chance(double sheetChance, double itemBonus, double totalCap)
    {
        return itemBonus > 0 ? std::clamp(sheetChance + itemBonus, 0.0, totalCap) : sheetChance;
    }

    // What a blocked hit of `damage` (already through every percentage layer) lets through: the items' cut of blocked
    // hits first
    // (`cutFactor`, 1 with none), then the shield's flat Block Amount, never below 0 (mitigation.csv Shield Block is
    // the last layer).
    inline double Blocked(double damage, double flat, double cutFactor)
    {
        return std::max(0.0, damage * cutFactor - flat);
    }

    // The attack an armed block bonus was spent on: a cast carries the bonus on every hit it still deals after the
    // first one connected. `pct` 0: none. The skill is the cast's base skill (every rune of it).
    struct Spent
    {
        double pct = 0;
        std::string skill;
    };

    // The multiplier a hit of `skill` gets: the armed bonus (`armedPct`, the aura on the player) on any hit, else the
    // bonus the cast of this skill already spent on its first connected hit; 1 when neither.
    inline double NextAttackFactor(double armedPct, Spent const& spent, std::string const& skill)
    {
        if (armedPct > 0)
            return 1.0 + armedPct / 100.0;
        return spent.pct > 0 && spent.skill == skill ? 1.0 + spent.pct / 100.0 : 1.0;
    }

    // An attack of `skill` connected: the armed bonus is spent on it and rides the rest of that cast; with none armed
    // the cast in progress keeps what it had.
    inline Spent Connect(double armedPct, Spent const& spent, std::string const& skill)
    {
        return armedPct > 0 ? Spent{armedPct, skill} : spent;
    }

    // The player pressed a skill: the attack before it is over, so what it spent is gone.
    inline Spent Press(Spent const&)
    {
        return {};
    }

    // A block while a bonus is armed keeps the larger one: the bonus does not stack.
    inline double Arm(double armedPct, double pct)
    {
        return std::max(armedPct, pct);
    }
} // namespace DC::Combat::ItemBlock

#endif
