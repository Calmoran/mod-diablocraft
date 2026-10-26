#pragma once
// The rules of the Shaman's totems with no core include, so tests/shaman_totems compiles them alone: which creature the
// native totem slots hold, how long a totem lasts, when its pulses are due and which enemy a bolt goes to.
// dc_shaman_totems.cpp is the player and creature side around them.
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

namespace DC::Combat::Shaman::Totems
{
    // The core's totem slots (SharedDefines.h SUMMON_SLOT_TOTEM_FIRE to SUMMON_SLOT_TOTEM_AIR).
    inline constexpr unsigned FireSlot = 1;
    inline constexpr unsigned EarthSlot = 2;
    inline constexpr unsigned WaterSlot = 3;
    inline constexpr unsigned AirSlot = 4;

    // The creature a totem slot holds (data/d3/shaman_summons.csv), 0 for a slot that is no totem slot.
    inline std::uint32_t EntryOfSlot(unsigned slot)
    {
        switch (slot)
        {
            case FireSlot:
                return 900180;
            case EarthSlot:
                return 900181;
            case WaterSlot:
                return 900182;
            case AirSlot:
                return 900183;
            default:
                return 0;
        }
    }

    // How long a totem stands, in milliseconds: the skill's seconds, none for no seconds (a totem with no time is not
    // placed).
    inline std::uint32_t DurationMs(double seconds)
    {
        return seconds > 0 ? std::uint32_t(std::llround(seconds * 1000.0)) : 0;
    }

    // The pulses due after `diffMs` more, each `periodSeconds` long; the rest of the clock is kept. A totem with no
    // period never pulses.
    inline unsigned Pulses(std::uint32_t& clockMs, std::uint32_t diffMs, double periodSeconds)
    {
        std::uint32_t const period = DurationMs(periodSeconds);
        if (!period)
        {
            clockMs = 0;
            return 0;
        }
        clockMs += diffMs;
        unsigned due = 0;
        while (clockMs >= period)
        {
            clockMs -= period;
            ++due;
        }
        return due;
    }

    inline constexpr std::size_t None = std::numeric_limits<std::size_t>::max();

    // The nearest of the distances (the first of equals), None for no enemy.
    inline std::size_t Nearest(std::vector<double> const& distances)
    {
        std::size_t best = None;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (best == None || distances[i] < distances[best])
                best = i;
        return best;
    }
} // namespace DC::Combat::Shaman::Totems
