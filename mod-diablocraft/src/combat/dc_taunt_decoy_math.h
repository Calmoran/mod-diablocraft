#pragma once
// The rules of a taunting decoy with no core type, so tests/taunt_decoy compiles this exact code: when a decoy is built
// at all, who it taunts, how long it holds the taunt, and what its explosion deals. The production half is
// dc_taunt_decoy.cpp.
#include <algorithm>
#include <cstdint>

namespace DC::Combat::TauntDecoy
{
    // A decoy is built only with all three of its numbers set (each above 0): a blank tunable reads 0 and builds none.
    inline bool Built(double tauntRadius, double delaySeconds, double blastRadius)
    {
        return tauntRadius > 0 && delaySeconds > 0 && blastRadius > 0;
    }

    // Whether an enemy `distance` yards from the decoy is within `radius` of it (on the edge counts).
    inline bool Within(double distance, double radius)
    {
        return radius > 0 && distance >= 0 && distance <= radius;
    }

    // The explosion's weapon-damage percent: the item's percent for each stack the owner's effect holds when it goes
    // off.
    inline double BlastPct(double perStackPct, unsigned stacks)
    {
        return std::max(0.0, perStackPct) * stacks;
    }

    // Seconds as the event queue's milliseconds, rounded.
    inline std::uint32_t Millis(double seconds)
    {
        return seconds > 0 ? static_cast<std::uint32_t>(seconds * 1000.0 + 0.5) : 0u;
    }
} // namespace DC::Combat::TauntDecoy
