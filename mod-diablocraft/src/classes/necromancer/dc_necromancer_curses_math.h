#pragma once
// The rule of which curse a new curse takes off an enemy, header-only so a harness compiles this exact code. The production half is
// Put in dc_necromancer_curses.cpp.
#include <cstdint>

namespace DC::Combat::Necromancer::Curses
{
    // Whether a curse already on an enemy comes off when another is put on it. An enemy bears one curse of a skill at a time, the newest
    // of the skill replacing the old; a curse of another skill is replaced too, unless the Necromancer's curses stand together
    // (Simulacrum's Cursed Form: "your curse skills now apply all three curses").
    inline bool Lifts(bool together, bool sameSkill, bool live, std::uint32_t heldSpell, std::uint32_t newSpell)
    {
        if (!live || !heldSpell)
            return false;
        return sameSkill ? heldSpell != newSpell : !together;
    }
} // namespace DC::Combat::Necromancer::Curses
