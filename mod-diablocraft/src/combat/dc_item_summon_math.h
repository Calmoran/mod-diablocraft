/*
 * World of DiabloCraft - the rules of the allies a legendary item summons (N-SUMMON; Bovine Bardiche).
 *
 * No core dependency, so scripts/test_item_power_bovine_bardiche.py compiles this exact header and drives it. The
 * summon itself is dc_item_summons.cpp.
 */

#ifndef DC_ITEM_SUMMON_MATH_H
#define DC_ITEM_SUMMON_MATH_H

#include "dc_proc_math.h"

#include <cstdint>
#include <optional>

namespace DC::Combat::ItemSummon
{
    // Whether a hit calls the herd. Not while the internal cooldown since the last herd (`lastMs`, none before the
    // first) runs; then the chance, a percent scaled by the hit's proc coefficient like every chance on hit
    // (Proc::Rolls: a hit that states none never calls one; a blank chance reads 0, never). `roll` takes a percent and
    // answers whether it fell. The cooldown starts only when a herd comes (the caller records `nowMs` then): a hit that
    // called none starts nothing. The milliseconds are the core's getMSTime, which wraps; the unsigned difference does
    // too.
    template<class Roll>
    inline bool HerdComes(std::optional<std::uint32_t> lastMs, std::uint32_t nowMs, double cooldownSeconds,
                          double coefficient, double chancePct, Roll roll)
    {
        if (lastMs && nowMs - *lastMs < cooldownSeconds * 1000.0)
            return false;
        return Proc::Rolls(coefficient, chancePct, roll);
    }

    // The percent of weapon damage one swing of a cow deals. One attack is `pct` and `draw` (0 to 1) of `deltaPct`
    // above it; a cow attacks at its owner's attacks per second, as the Ancients do, and swings every `intervalMs`, so
    // a swing carries that many attacks.
    inline double SwingPct(double pct, double deltaPct, double draw, double attacksPerSecond, std::uint32_t intervalMs)
    {
        return (pct + deltaPct * draw) * attacksPerSecond * intervalMs / 1000.0;
    }
} // namespace DC::Combat::ItemSummon

#endif
