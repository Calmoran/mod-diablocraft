#pragma once
// The rules of the Healing Stream Totem's runes with no core include, so tests/shaman_healing_stream_totem compiles
// them alone: what a tick heals, what Healing Tide heals at once, how long Cleansing Stream's immunity holds, and when
// Ancestral Protection saves and to how much Life. The player and creature side is dc_shaman_healing_stream_totem.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::Shaman::HealingStream
{
    // "heals you and allies for N% of maximum Life per second": a look every `tickSeconds` heals its share of a second.
    inline double TickHeal(double maxLife, double pctPerSecond, double tickSeconds)
    {
        return maxLife > 0 && pctPerSecond > 0 && tickSeconds > 0 ? maxLife * pctPerSecond / 100.0 * tickSeconds : 0.0;
    }

    // Healing Tide: "Also heals for N% of maximum Life when placed."
    inline double PlacedHeal(double maxLife, double pct)
    {
        return maxLife > 0 && pct > 0 ? maxLife * std::min(pct, 100.0) / 100.0 : 0.0;
    }

    // Maelstrom Spring: "restores N Maelstrom per second": a look's share of a second.
    inline double TickGain(double perSecond, double tickSeconds)
    {
        return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;
    }

    inline std::uint64_t Millis(double seconds)
    {
        return seconds > 0 ? std::uint64_t(std::llround(seconds * 1000.0)) : 0;
    }

    // Cleansing Stream's immunity ends `seconds` after the totem was placed.
    inline std::uint64_t ImmuneUntil(std::uint64_t placedMs, double seconds)
    {
        return seconds > 0 ? placedMs + Millis(seconds) : 0;
    }

    inline bool Immune(std::uint64_t untilMs, std::uint64_t nowMs)
    {
        return untilMs > nowMs;
    }

    // Ancestral Protection: "The first time you would die within its radius, the death is prevented": the blow takes
    // all the Life, the Shaman is within the radius, and the totem has not saved yet.
    inline bool Saves(double health, double damage, bool within, bool alreadySaved)
    {
        return !alreadySaved && within && damage > 0 && damage >= health;
    }

    // "... and you are healed to N% Life": the Life the Shaman is left with, never less than they had.
    inline double SavedHealth(double health, double maxLife, double floorPct)
    {
        return std::max(health, maxLife > 0 ? maxLife * std::clamp(floorPct, 0.0, 100.0) / 100.0 : 0.0);
    }

    // Whether something `yards` from the totem is within its `radius` (the edge counts as within).
    inline bool Within(double yards, double radius)
    {
        return radius > 0 && yards <= radius;
    }
} // namespace DC::Combat::Shaman::HealingStream
