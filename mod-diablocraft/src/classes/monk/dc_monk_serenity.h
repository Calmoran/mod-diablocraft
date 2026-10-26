#pragma once
// Serenity's rules that need no core type, header-only so tests/monk_serenity compiles
// this exact code: how many times Unwelcome Disturbance pulses while the shield lasts, what Peaceful Repose heals
// inside the sheet's range, and the cooldown that starts only after the shield ends.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::Monk::Serenity
{
    // "enemies within {radius_yards} yards take {damage_pct} weapon damage every second": whole pulses of
    // `intervalSeconds` (Power/Monk_Serenity.pow SF_15, 0.99) inside the shield's `durationSeconds`, the first one
    // interval after the cast.
    inline unsigned Pulses(double durationSeconds, double intervalSeconds)
    {
        return durationSeconds > 0 && intervalSeconds > 0
                   ? unsigned(std::floor(durationSeconds / intervalSeconds + 1e-9))
                   : 0;
    }

    // "heals you for {heal_min_life} - {heal_max_life} Life": `share` (0 to 1) of the way from the minimum to the
    // maximum.
    inline double HealRoll(double minLife, double maxLife, double share)
    {
        return minLife + (std::max(minLife, maxLife) - minLife) * std::clamp(share, 0.0, 1.0);
    }

    // "This ability does not start its cooldown until after its effects expire": the cooldown the core installed at the
    // cast is pushed back by the whole time the shield lasts, in milliseconds.
    inline std::uint64_t CooldownDelayMs(double shieldSeconds)
    {
        return std::uint64_t(std::max(0.0, shieldSeconds) * 1000.0 + 0.5);
    }
} // namespace DC::Combat::Monk::Serenity
