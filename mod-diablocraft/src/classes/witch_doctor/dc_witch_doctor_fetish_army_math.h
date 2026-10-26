#pragma once
// The rules of Fetish Army's runes that need no core type, header-only so tests/witch_doctor_fetish_army compiles this
// exact code: whether a Fetish of Fetish Ambush appears on an enemy and which one. The cone the casters and hunters hit
// is the pets' (Pets::InCleave). The production half is dc_witch_doctor_fetish_army.cpp.
#include <algorithm>
#include <cstddef>

namespace DC::Combat::WitchDoctor::FetishArmy
{
    // Fetish Ambush: "Chance to apparate on enemy": a roll of 0 to 100 against the chance.
    inline bool Apparates(double roll, double chancePct)
    {
        return chancePct > 0 && roll < chancePct;
    }

    // The enemy a Fetish appears on among `count` of them, from a draw `unit` in [0, 1): every enemy equally, never
    // past the last.
    inline std::size_t Pick(std::size_t count, double unit)
    {
        return count == 0
                   ? 0
                   : std::min(count - 1, static_cast<std::size_t>(std::max(0.0, unit) * static_cast<double>(count)));
    }
} // namespace DC::Combat::WitchDoctor::FetishArmy
