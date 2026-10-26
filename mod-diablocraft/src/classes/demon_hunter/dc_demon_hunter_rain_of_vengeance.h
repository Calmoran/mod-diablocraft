#pragma once
// Rain of Vengeance's rules that need no core type, header-only so tests/demon_hunter_rain_of_vengeance compiles this
// exact code: which rune is which, when each tick, storm, grenade, flyer and beast lands, where, and what share of the
// rune's total each carries. The production half is dc_demon_hunter_rain_of_vengeance.cpp.
#include "dc_demon_hunter_dot.h"
#include "dc_demon_hunter_pick.h"

#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
struct Position;

namespace DC::Combat::DemonHunter::RainOfVengeance
{
    enum class Rune
    {
        None,
        Shade,        // the base rain with a bigger total, Lightning
        DarkCloud,    // storms over random enemies for longer, Physical
        Anathema,     // a Shadow Beast drops grenades, Fire
        FlyingStrike, // Shadow Beasts crash down, Cold, and freeze
        Stampede      // a wave of Shadow Beasts across the ground, Fire, and knocks back
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Shade")
            return Rune::Shade;
        if (name == "Dark Cloud")
            return Rune::DarkCloud;
        if (name == "Anathema")
            return Rune::Anathema;
        if (name == "Flying Strike")
            return Rune::FlyingStrike;
        if (name == "Stampede")
            return Rune::Stampede;
        return Rune::None;
    }

    // A point on the ground.
    struct Spot
    {
        double x = 0;
        double y = 0;
    };

    // How many of an `intervalSeconds` fit `seconds`: the ticks of the rain, the storms of the cloud, the grenades of
    // the beast. None for no interval.
    inline unsigned Count(double seconds, double intervalSeconds)
    {
        return Dot::Ticks(seconds, intervalSeconds);
    }

    // "{damage_pct} ... over {dot_duration_seconds} seconds" and "{damage_pct} total": what one of `count` carries of
    // the rune's total. No count, none.
    inline double Share(double totalPct, unsigned count)
    {
        return Dot::TickPct(totalPct, count);
    }

    // The milliseconds after the cast the `index`th of a series lands: the delay all versions of the skill have, then
    // one interval apart.
    inline std::uint32_t StartMs(unsigned index, double delaySeconds, double intervalSeconds)
    {
        double const seconds =
            (delaySeconds > 0 ? delaySeconds : 0.0) + (intervalSeconds > 0 ? intervalSeconds : 0.0) * index;
        return std::uint32_t(seconds * 1000.0 + 0.5);
    }

    // A point within `radius` of (x, y), evenly over the disc: the first roll of 0 up to 1 picks the distance, the
    // second the heading.
    inline Spot DiscPoint(double x, double y, double radius, double distanceRoll, double headingRoll)
    {
        double const yards = radius * std::sqrt(distanceRoll < 0 ? 0.0 : (distanceRoll > 1 ? 1.0 : distanceRoll));
        double const heading = headingRoll * 2.0 * 3.14159265358979323846;
        return {x + std::cos(heading) * yards, y + std::sin(heading) * yards};
    }

    // Stampede: where the `index`th of `count` beasts is on the line of `heading` from (x, y) over `length` yards,
    // spread evenly to its end.
    inline Spot WavePoint(double x, double y, double heading, unsigned index, unsigned count, double length)
    {
        double const along = count ? length * double(index + 1) / double(count) : 0.0;
        return {x + std::cos(heading) * along, y + std::sin(heading) * along};
    }

    // Stampede: the milliseconds after the cast the wave reaches the `index`th of `count` beasts, spread evenly over
    // its `seconds`.
    inline std::uint32_t WaveMs(unsigned index, unsigned count, double delaySeconds, double seconds)
    {
        double const along = count ? (seconds > 0 ? seconds : 0.0) * double(index + 1) / double(count) : 0.0;
        return std::uint32_t(((delaySeconds > 0 ? delaySeconds : 0.0) + along) * 1000.0 + 0.5);
    }

    // The production half (dc_demon_hunter_rain_of_vengeance.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The cast hits nothing of its own: the rain falls after its delay.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved at `center`: the rain, the storms, the grenades or the beasts are scheduled.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::DemonHunter::RainOfVengeance
