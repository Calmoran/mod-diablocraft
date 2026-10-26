#pragma once
// The rules of the Earthbind Totem's runes with no core include, so tests/shaman_earthbind_totem compiles them alone: the enemies the totem has
// met (Earthgrab roots each once), how long a mark on an enemy holds and whether a point is within the totem's reach. The player and creature side
// is dc_shaman_earthbind_totem.cpp.
#include <cmath>
#include <cstdint>
#include <unordered_set>

namespace DC::Combat::Shaman::Earthbind
{
    // Earthgrab: "the first time they enter its radius". True the first time the totem meets the enemy, never again.
    inline bool FirstEntry(std::unordered_set<std::uint64_t>& seen, std::uint64_t enemy)
    {
        return seen.insert(enemy).second;
    }

    inline std::uint64_t Millis(double seconds)
    {
        return seconds > 0 ? std::uint64_t(std::llround(seconds * 1000.0)) : 0;
    }

    // A mark the totem puts on an enemy within its radius lasts `holdSeconds` from the look that put it: the time it ends.
    inline std::uint64_t HeldUntil(std::uint64_t nowMs, double holdSeconds)
    {
        return holdSeconds > 0 ? nowMs + Millis(holdSeconds) : 0;
    }

    inline bool Marked(std::uint64_t untilMs, std::uint64_t nowMs)
    {
        return untilMs > nowMs;
    }

    // Whether something `yards` from the totem is within its `radius` (the edge counts as within).
    inline bool Within(double yards, double radius)
    {
        return radius > 0 && yards <= radius;
    }

    // "Take N% more damage from all your skills": the percent more a mark gives, none for an enemy not marked or a negative percent.
    inline double MorePct(bool marked, double pct)
    {
        return marked && pct > 0 ? pct : 0.0;
    }
} // namespace DC::Combat::Shaman::Earthbind
