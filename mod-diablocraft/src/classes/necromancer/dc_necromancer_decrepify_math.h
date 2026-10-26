#pragma once
// The rules of Decrepify's runes that need no core type, header-only so tests/necromancer_decrepify compiles this exact code: which
// rune is which, how Enfeeblement's slow decays, what the Necromancer gains for the enemies cursed (Opportunist, Borrowed Time) and
// whether Dizzying Curse's stun lands on a roll. The production half is dc_necromancer_decrepify.cpp.
#include <algorithm>
#include <cmath>
#include <string_view>

namespace DC::Combat::Necromancer::Decrepify
{
    enum class Rune
    {
        None,
        Enfeeblement,
        Opportunist,
        BorrowedTime,
        Wither,
        DizzyingCurse
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Enfeeblement")
            return Rune::Enfeeblement;
        if (name == "Opportunist")
            return Rune::Opportunist;
        if (name == "Borrowed Time")
            return Rune::BorrowedTime;
        if (name == "Wither")
            return Rune::Wither;
        if (name == "Dizzying Curse")
            return Rune::DizzyingCurse;
        return Rune::None;
    }

    // Enfeeblement: "the potency of the movement speed reduction ... decaying to normal potency": the slow `elapsed` seconds after
    // the cast, from `startPct` down by `perSecond` each second and no further than `basePct`.
    inline double DecayedSlow(double startPct, double basePct, double perSecond, double elapsed)
    {
        return std::max(basePct, startPct - std::max(0.0, perSecond) * std::max(0.0, elapsed));
    }

    // The whole seconds that fit `seconds` at `step`; no step, none.
    inline unsigned Steps(double seconds, double step)
    {
        return seconds > 0 && step > 0 ? static_cast<unsigned>(std::floor(seconds / step + 1e-9)) : 0u;
    }

    // Opportunist and Borrowed Time: "for every enemy cursed, up to a maximum": what `cursed` enemies give.
    inline double StackBonus(unsigned cursed, double perEnemy, double most)
    {
        return std::max(0.0, std::min(cursed * std::max(0.0, perEnemy), most));
    }

    // Dizzying Curse: a roll of 0 to 100 (exclusive of 100) lands the stun when it is under the chance.
    inline bool Procs(double roll, double chancePct)
    {
        return roll < chancePct;
    }
} // namespace DC::Combat::Necromancer::Decrepify
