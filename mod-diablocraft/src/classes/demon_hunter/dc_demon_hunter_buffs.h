#pragma once
// The Demon Hunter's timed sheet numbers (Evasive Fire - Hardened's armor): the rule that needs no core type,
// header-only so the harness of the skills that use it compiles this exact code. The sheet half is
// dc_demon_hunter_buffs.cpp.
#include <algorithm>
#include <cstdint>

class Player;

namespace DC::Combat::DemonHunter::Buffs
{
    // One buff on one player. Casting it again adds a stack up to the cap and restarts the whole time; a buff that ran
    // out starts again from one stack.
    struct Held
    {
        unsigned stacks = 0;
        std::uint64_t until = 0; // ms: the buff is over from this moment on
    };

    inline unsigned Add(Held& held, std::uint64_t now, std::uint64_t ms, unsigned maxStacks)
    {
        if (held.until <= now)
            held.stacks = 0;
        held.stacks = std::min(held.stacks + 1u, std::max(1u, maxStacks));
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
} // namespace DC::Combat::DemonHunter::Buffs
