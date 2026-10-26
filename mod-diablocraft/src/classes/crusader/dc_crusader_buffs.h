#pragma once
// The Crusader's timed, stacking sheet numbers (Celerity's attack speed, Zeal's stacks, Guard's armor, Hardened Senses'
// block): the rule that needs no core type, header-only so tests/crusader_buffs compiles this exact code. The sheet
// half is dc_crusader_buffs.cpp.
#include <algorithm>
#include <cstdint>

class Player;

namespace DC::Combat::Crusader::Buffs
{
    // One buff on one player. Casting it again adds a stack up to the cap and restarts the whole time (d3planner
    // buffs.js addBuff: refresh true, maxstacks); a buff that ran out starts again from one stack.
    struct Held
    {
        unsigned stacks = 0;
        std::uint64_t until = 0; // ms: the buff is over from this moment on
    };

    // `adds` stacks at once: a skill that gives one for each enemy it hit.
    inline unsigned Add(Held& held, std::uint64_t now, std::uint64_t ms, unsigned maxStacks, unsigned adds = 1)
    {
        if (held.until <= now)
            held.stacks = 0;
        held.stacks = std::min(held.stacks + std::max(1u, adds), std::max(1u, maxStacks));
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
} // namespace DC::Combat::Crusader::Buffs
