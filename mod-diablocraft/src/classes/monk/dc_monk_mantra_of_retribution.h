#pragma once
// Mantra of Retribution's rules that need no core type, header-only so
// tests/monk_mantra_of_retribution compiles this exact code. The skill is an aura: its passive is always on while the
// skill is slotted ("deal {damage_pct:passive} of your weapon damage as Holy to attackers"), its activation raises the
// damage for {duration_seconds} seconds, and only one Mantra may be active at a time.
#include <algorithm>
#include <cstdint>

namespace DC::Combat::Monk
{
    // The weapon damage one reflected hit deals: the passive (the rune's own damage when it states one - Retaliation's
    // 202 - else the skill's 101), plus the activation's increase (active 202 less passive 101) inside its window. Pct
    // is never negative.
    inline double MantraReflectPct(double passive, double boost, bool boosted)
    {
        return std::max(0.0, passive + (boosted && boost > 0 ? boost : 0.0));
    }

    // A chance in percent against a roll in [0, 100): the roll must land under it. A blank or zero chance never procs.
    inline bool MantraProcs(double chancePct, double rollPct)
    {
        return chancePct > 0 && rollPct < chancePct;
    }
} // namespace DC::Combat::Monk
