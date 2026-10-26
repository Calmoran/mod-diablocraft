#pragma once
// Blessed Hammer's rules that need no core type, header-only so tests/crusader_blessed_hammer compiles this exact code:
// which rune is which, how far the hammer reaches, which enemies lie in the ring Limitless adds, and how many fire
// pools may burn at once. The production half is dc_crusader_blessed_hammer.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::BlessedHammer
{
    enum class Rune
    {
        None,
        BurningWrath,  // fire pools where it hits
        Thunderstruck, // arcs between you and the hammer
        Limitless,     // a heavier hit over a larger area
        BruteForce,    // a slow, and an explosion that stuns
        Dominion       // the hammer orbits you as you move
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Burning Wrath")
            return Rune::BurningWrath;
        if (rune == "Thunderstruck")
            return Rune::Thunderstruck;
        if (rune == "Limitless")
            return Rune::Limitless;
        if (rune == "Brute Force")
            return Rune::BruteForce;
        if (rune == "Dominion")
            return Rune::Dominion;
        return Rune::None;
    }

    // "increase its area of effect by {radius_yards} yards": the skill's reach, and Limitless's with the increase.
    inline double Reach(Rune rune, double base, double increase)
    {
        return rune == Rune::Limitless ? base + increase : base;
    }

    // Limitless: the hammer also lasts longer (the power file's SF_38).
    inline double Lifetime(Rune rune, double base, double factor)
    {
        return rune == Rune::Limitless ? base * factor : base;
    }

    struct Offset
    {
        double x = 0, y = 0;
    };

    // The hammer's path: a spiral out from the Crusader, its distance growing evenly from nothing to the reach over its life and
    // its heading turning `loops` times, from the heading the Crusader faced when it was cast. Past its life it stays at the end.
    inline Offset Orbit(double elapsed, double lifetime, double reach, double loops, double heading)
    {
        double const share = lifetime > 0 ? std::clamp(elapsed / lifetime, 0.0, 1.0) : 1.0;
        double const angle = heading + 2 * 3.14159265358979323846 * loops * share, distance = reach * share;
        return {distance * std::cos(angle), distance * std::sin(angle)};
    }

    // The hammer touches an enemy when it is within its hit radius; no radius, no touch.
    inline bool Touches(double distance, double hitRadius)
    {
        return hitRadius > 0 && distance <= hitRadius;
    }

    // An enemy is hit as the hammer reaches it, once for each pass: when it touches it and did not at the last look.
    inline bool Enters(bool touchedBefore, bool touchingNow)
    {
        return touchingNow && !touchedBefore;
    }

    // The distance from a point to the segment between two others: Thunderstruck's arc runs from the Crusader to the hammer, and
    // an enemy within its width of that segment is caught.
    inline double SegmentDistance(double px, double py, double ax, double ay, double bx, double by)
    {
        double const dx = bx - ax, dy = by - ay, length = dx * dx + dy * dy;
        double const along = length > 0 ? std::clamp(((px - ax) * dx + (py - ay) * dy) / length, 0.0, 1.0) : 0.0;
        return std::hypot(px - (ax + along * dx), py - (ay + along * dy));
    }

    // The looks the hammer takes over its life, one every `step` seconds.
    inline unsigned Steps(double lifetime, double step)
    {
        return lifetime > 0 && step > 0 ? static_cast<unsigned>(lifetime / step + 1e-9) : 0u;
    }

    // "Max # Pools at a time": a new pool may be laid while fewer than the most are burning.
    inline bool PoolRoom(std::size_t burning, std::size_t most)
    {
        return burning < most;
    }

    // The ticks of a pool: "{damage_pct} weapon damage as Fire per second" over its seconds, one a `tickSeconds`.
    inline unsigned PoolTicks(double seconds, double tickSeconds)
    {
        return seconds > 0 && tickSeconds > 0 ? static_cast<unsigned>(seconds / tickSeconds + 1e-9) : 0u;
    }

    // The schedule of a pool: a tick fires while any are left, and each leaves one fewer. A pool of N ticks fires N times.
    inline bool PoolFires(unsigned left)
    {
        return left > 0;
    }

    inline unsigned PoolLeftAfter(unsigned left)
    {
        return left > 0 ? left - 1 : 0;
    }

    // The production half (dc_crusader_blessed_hammer.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The engine's own hit of the cast: none. The hammer hits where it spirals (Cast), so the instant hit of the area the record
    // targets would be a second one.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast begins the hammer's spiral: 320% (Limitless's 640%) to the enemies it touches, and what the rune does about them.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Crusader::BlessedHammer
