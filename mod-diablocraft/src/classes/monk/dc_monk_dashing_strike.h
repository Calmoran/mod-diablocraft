#pragma once
// Dashing Strike's rules that need no core type (Barrage's ticks; the charges are Combat::ChargeStore), header-only so
// tests/monk_dashing_strike compiles this exact code. The game glue is dc_monk_dashing_strike.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::Monk::DashingStrike
{
    // "You gain a charge every {charge_recharge_seconds} seconds and can have up to {charge_count} charges stored at a
    // time" (Power/X1_Monk_DashingStrike.pow SF_2 'Charge Rate', SF_24 'Total: Max Charges'): the shared Combat::ChargeStore
    // (src/combat/dc_charge_store.h), one per Monk, in dc_monk_dashing_strike.cpp.

    // Barrage: "taking an additional {damage_pct} weapon damage as Physical over {dot_duration_seconds} seconds", dealt
    // in ticks of `tickSeconds` (the power file's SF_11 'A: Tick Rate'). The whole total is paid: `count` equal ticks.
    struct Ticks
    {
        unsigned count = 0;
        double pctEach = 0;
    };
    inline Ticks Split(double totalPct, double durationSeconds, double tickSeconds)
    {
        if (totalPct <= 0 || durationSeconds <= 0 || tickSeconds <= 0)
            return {};
        unsigned const count = std::max(1u, unsigned(std::lround(durationSeconds / tickSeconds)));
        return {count, totalPct / count};
    }
} // namespace DC::Combat::Monk::DashingStrike
