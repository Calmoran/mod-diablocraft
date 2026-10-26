#pragma once
// How a cast of an ability record reaches its hits, with no core type, so tests/ground_missile compiles this exact
// code. The core delivers a missile (a record with a Speed, not channelled) to each unit its effects aim at, one impact
// apiece; a record whose effects aim at no unit but the caster (a ground point) has no unit to hit, so no impact ever
// comes and the module resolves the cast itself when the missile reaches the point. A record with no Speed resolves at
// the cast.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::GroundMissile
{
    enum class Path
    {
        AtCast,    // no missile: the cast resolves as it is made
        OnImpact,  // a missile aimed at units: each unit's impact resolves its own hit
        OnArrival, // a missile aimed at a point: the module resolves the cast when it arrives
    };

    inline Path PathOf(double speed, bool channeled, bool aimsAtAUnit)
    {
        if (speed <= 0 || channeled)
            return Path::AtCast;
        return aimsAtAUnit ? Path::OnImpact : Path::OnArrival;
    }

    // Milliseconds a missile of `speed` yards a second takes over `distance` yards; 0 for no distance or no speed.
    inline std::uint32_t ArrivalMs(double distance, double speed)
    {
        if (distance <= 0 || speed <= 0)
            return 0;
        return static_cast<std::uint32_t>(std::lround(distance / speed * 1000.0));
    }
} // namespace DC::Combat::GroundMissile
