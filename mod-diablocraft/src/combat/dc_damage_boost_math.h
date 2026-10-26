#pragma once
// The rules of a timed damage boost that need no core type, header-only so tests/damage_boost compiles this exact code:
// a boost is a percent more damage dealt, from one source, until a moment; it is one multiplier of its own in the hit,
// and a second one from the same source replaces the first. The production half is dc_damage_boost.cpp. No class or
// skill is named here.
#include <cstdint>

namespace DC::Combat::DamageBoost
{
    struct Held
    {
        double pct = 0;
        std::uint64_t until = 0; // ms: the boost is over from this moment on
    };

    // A boost of `pct` percent that lasts `seconds` from `now`. No percent or no seconds, no boost.
    inline Held Given(double pct, std::uint64_t now, double seconds)
    {
        if (pct == 0 || seconds <= 0)
            return {};
        return {pct, now + static_cast<std::uint64_t>(seconds * 1000.0)};
    }

    inline bool Live(Held const& held, std::uint64_t now)
    {
        return held.pct != 0 && now < held.until;
    }

    // What the boost multiplies a hit by: 1 + pct / 100 while it stands, 1 after.
    inline double Multiplier(Held const& held, std::uint64_t now)
    {
        return Live(held, now) ? 1.0 + held.pct / 100.0 : 1.0;
    }
} // namespace DC::Combat::DamageBoost
