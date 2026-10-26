#pragma once
// The Witch Doctor's pets' rules that need no core type, header-only so tests/witch_doctor_pets compiles this exact
// code: how many dogs may stand, what a pet's Life and blow are after the passives, where a Fetish of the Army appears
// on its ring, whether an enemy stands in the arc of the Gargantuan's cleave, and whether a Fetish Sycophant may be
// summoned. The production half is dc_witch_doctor_pets.cpp.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace DC::Combat::WitchDoctor::Pets
{
    // The minion groups that are the Witch Doctor's pets: the Zombie Dogs, the Gargantuan, the Army's daggers, casters and hunters, the Sycophants'
    // Fetishes.
    inline constexpr std::string_view PetGroups[] = {"dog", "gargantuan", "fetish", "fetish_caster", "fetish_hunter", "sycophant"};

    // "Max Dogs" = the skill's pet_count and what the chosen passives add (one each: Zombie Handler, Fierce Loyalty,
    // Midnight Feast).
    inline unsigned DogCap(double skillCount, double passivesAdd)
    {
        double const count = std::max(0.0, skillCount) + std::max(0.0, passivesAdd);
        return static_cast<unsigned>(std::llround(count));
    }

    // A pet's Life as a share of the Witch Doctor's maximum Life, raised by Zombie Handler's percent ("Your Life, and
    // that of your Zombie Dogs and Gargantuan are increased by 20%"): 35% of the Life becomes 42%.
    inline double LifePct(double sharePct, double handlerPct)
    {
        return std::max(0.0, sharePct) * (1.0 + std::max(0.0, handlerPct) / 100.0);
    }

    // A pet's blow in percent of weapon damage, raised by Midnight Feast's percent ("The damage of your Zombie Dogs and
    // Gargantuan is increased by 50%").
    inline double BlowPct(double damagePct, double feastPct)
    {
        return std::max(0.0, damagePct) * (1.0 + std::max(0.0, feastPct) / 100.0);
    }

    struct Offset
    {
        double x = 0;
        double y = 0;
    };

    // Where a Fetish of the Army appears: on a ring `minYards` to `maxYards` round the Witch Doctor ("Spawn Radius
    // Min/Max"). `angleUnit` and `radiusUnit` are draws in [0, 1): the angle is a turn of the circle, the radius is
    // chosen so that the ring's area is covered evenly.
    inline Offset RingPoint(double minYards, double maxYards, double angleUnit, double radiusUnit)
    {
        double const low = std::max(0.0, minYards), high = std::max(low, maxYards);
        double const radius =
            std::sqrt(low * low + std::min(1.0, std::max(0.0, radiusUnit)) * (high * high - low * low));
        double const angle = 2.0 * 3.141592653589793 * std::min(1.0, std::max(0.0, angleUnit));
        return {radius * std::cos(angle), radius * std::sin(angle)};
    }

    // The smallest angle between two headings, radians in [0, pi].
    inline double AngleBetween(double a, double b)
    {
        double const twoPi = 6.283185307179586;
        double const difference = std::fmod(std::fabs(a - b), twoPi);
        return difference > twoPi / 2 ? twoPi - difference : difference;
    }

    // Whether a point at `heading` from the Gargantuan, `distance` yards off, is in its cleave: within `yards` (the end
    // inclusive) and within half of `degrees` of `centre`, the heading to the enemy it struck (the end inclusive). No
    // reach or no arc, nothing is in it.
    inline bool InCleave(double heading, double centre, double distance, double yards, double degrees)
    {
        if (degrees <= 0 || yards <= 0 || distance < 0 || distance > yards)
            return false;
        return AngleBetween(heading, centre) <= degrees * 0.017453292519943295 / 2.0 + 1e-9;
    }

    // "Max Sycophants": a Fetish is summoned only while fewer than `cap` stand (none at no cap).
    inline bool MaySummonSycophant(unsigned standing, unsigned cap)
    {
        return cap > 0 && standing < cap;
    }

    // Whole milliseconds of seconds, rounded to the nearest.
    inline std::uint32_t Millis(double seconds)
    {
        return seconds > 0 ? static_cast<std::uint32_t>(std::llround(seconds * 1000.0)) : 0u;
    }
} // namespace DC::Combat::WitchDoctor::Pets
