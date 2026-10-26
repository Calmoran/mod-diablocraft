#pragma once
// Mantra of Conviction's rules that need no core type, header-only so tests/monk_mantra_of_conviction compiles this exact
// code. Sources: the sheets (monk_skills.csv, monk_runes.csv, monk_skill_values.csv),
// Power/X1_Monk_MantraOfConviction_v2.pow (SF_ numbers) and d3planner's simulator monk.js:1176-1210 @898918b. The entry
// points are dc_monk_mantras_cast.h's.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::Monk::Conviction
{
    // "Enemies within {radius_yards} yards of you take {damage_taken_pct:passive} increased damage" (Overawe's own row
    // replaces the passive: 12 = SF_15 0.08 + SF_1 0.04); the activation adds what active (16) adds over the skill's
    // passive (8) for its seconds - the simulator's +8 buff over the aura (monk.js:1184), so Overawe's is 20.
    inline double TakenPct(double passive, double active, double skillPassive, bool boosted)
    {
        return std::max(0.0, passive) + (boosted ? std::max(0.0, active - skillPassive) : 0.0);
    }

    // Submission's "{damage_pct} weapon damage per second", paid every aura tick (SF_4): a tick's share of it.
    inline double TickPct(double perSecond, double tickSeconds)
    {
        return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;
    }
} // namespace DC::Combat::Monk::Conviction
