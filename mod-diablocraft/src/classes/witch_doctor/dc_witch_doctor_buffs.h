#pragma once
// The Witch Doctor's timed sheet numbers (Soul Harvest's Intelligence, speed, armor and Mana): the rule that needs no
// core type, header-only so the harness of the skills that use it compiles this exact code. The sheet half is
// dc_witch_doctor_sheet_buffs.cpp.
#include <algorithm>
#include <cstdint>

namespace DC::Combat::WitchDoctor::Buffs
{
    // One buff on one player. A cast adds stacks up to the cap and restarts the whole time; a buff that ran out starts
    // again from nothing.
    struct Held
    {
        unsigned stacks = 0;
        std::uint64_t until = 0; // ms: the buff is over from this moment on
    };

    inline unsigned Add(Held& held, std::uint64_t now, std::uint64_t ms, unsigned maxStacks, unsigned adds)
    {
        if (held.until <= now)
            held.stacks = 0;
        held.stacks = std::min(held.stacks + adds, std::max(1u, maxStacks));
        held.until = now + ms;
        return held.stacks;
    }

    inline bool Over(Held const& held, std::uint64_t now)
    {
        return held.until <= now;
    }

    // What the buff puts on the sheet: its number for every stack, nothing once it is over.
    inline double Worth(Held const& held, std::uint64_t now, double perStack)
    {
        return Over(held, now) ? 0.0 : perStack * held.stacks;
    }

    // "increase maximum Mana by {pct} for each enemy harvested": the points one stack adds to a pool whose own points
    // (without the buff) are `basePoints`.
    inline double PoolPerStack(double basePoints, double pct)
    {
        return basePoints > 0 && pct > 0 ? basePoints * pct / 100.0 : 0.0;
    }

    // `perEnemy` for each of `enemies`, for a number that is not on the sheet (Siphon's Life).
    inline double PerEnemy(unsigned enemies, double perEnemy)
    {
        return perEnemy > 0 ? perEnemy * enemies : 0.0;
    }
} // namespace DC::Combat::WitchDoctor::Buffs
