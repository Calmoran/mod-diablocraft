/*
 * World of DiabloCraft - the values a buff's tooltip line shows
 * (contract docs/contracts/buff-values-messages.md).
 *
 * A buff's record states what is fixed per stack and the client shows the total. What the record cannot state (a
 * number that depends on a gem's rank, a live amount such as Moratorium's debt) goes to the addon as a DCBUFFVAL
 * record, throttled per aura (combat.csv buff_values_push_ms). The throttle and the spelling are
 * dc_buff_values_math.h; this is the wire and the clock. The class buffs call the same two functions and Show.
 */

#pragma once

#include <cstdint>
#include <vector>

class Player;

namespace DC::Combat::BuffValues
{
    // `aura` (the spell id the buff bar shows) now has these values, in the order the contract's table gives. Sent
    // at once or held for the interval; values the addon already has send nothing.
    void Set(Player*, std::uint32_t aura, std::vector<double> const& values);

    // The aura is gone: the addon is told once, if it was ever told of it.
    void Clear(Player*, std::uint32_t aura);

    // The class buffs (data/class_buffs.csv): the aura a class effect wears on the player. `stacks` of `aura`, with
    // `seconds` left on its timer (0: no timer, it stays until Show takes it off), and the addon line's `values` when it
    // has any. No stacks, or a dead player, takes it off and tells the addon it is gone. Cheap to call every upkeep:
    // it touches the aura only when the stacks or the timer differ. Not called with a module mutex held that an aura
    // hook of the core takes.
    void Show(Player*, std::uint32_t aura, unsigned stacks, double seconds = 0, std::vector<double> const& values = {});

    void RegisterScripts();
} // namespace DC::Combat::BuffValues
