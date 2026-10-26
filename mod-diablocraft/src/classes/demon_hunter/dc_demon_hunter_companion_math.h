#pragma once
// The Companion's rules that need no core type, header-only so tests/demon_hunter_companion compiles this exact code:
// which rune is which, how many pets a form has, which creature wears it, a pet's Life, whether an enemy stands in the
// cone of a pet's attack, who of a party is in range of the boar, and what the boar's regeneration is worth. The
// production half is dc_demon_hunter_companion.cpp.
#include <cmath>
#include <cstdint>
#include <string_view>

namespace DC::Combat::DemonHunter::Companion
{
    // The skill with no rune is the raven.
    enum class Rune
    {
        Raven,
        Spider,
        Boar,
        Wolf,
        Bat,
        Ferret
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Spider Companion")
            return Rune::Spider;
        if (name == "Boar Companion")
            return Rune::Boar;
        if (name == "Wolf Companion")
            return Rune::Wolf;
        if (name == "Bat Companion")
            return Rune::Bat;
        if (name == "Ferret Companion")
            return Rune::Ferret;
        return Rune::Raven;
    }

    // "Max Companion Pets" = 1 + the ferret's extra pet.
    inline unsigned Pets(Rune rune)
    {
        return rune == Rune::Ferret ? 2u : 1u;
    }

    // The creature of demon_hunter_summons.csv that wears the form.
    inline std::uint32_t EntryOf(Rune rune)
    {
        switch (rune)
        {
            case Rune::Raven:
                return 900160;
            case Rune::Spider:
                return 900161;
            case Rune::Boar:
                return 900162;
            case Rune::Wolf:
                return 900163;
            case Rune::Bat:
                return 900164;
            case Rune::Ferret:
                return 900165;
        }
        return 0;
    }

    // A pet's Life as a share of the Demon Hunter's maximum Life: the boar's own, every other form's.
    inline double LifePct(Rune rune, double formsPct, double boarPct)
    {
        return rune == Rune::Boar ? boarPct : formsPct;
    }

    // The spider's and the wolf's attacks reach every enemy in a cone in front of the pet.
    inline bool HasCone(Rune rune)
    {
        return rune == Rune::Spider || rune == Rune::Wolf;
    }

    // The smallest angle between two headings, radians in [0, pi].
    inline double AngleBetween(double a, double b)
    {
        double const twoPi = 6.283185307179586;
        double difference = std::fmod(std::fabs(a - b), twoPi);
        return difference > twoPi / 2 ? twoPi - difference : difference;
    }

    // Whether a point at `heading` from the pet is in the cone that is `degrees` wide and centred on `centre` (the end
    // inclusive) and within `yards` of the pet (the end inclusive). No width or no reach, nothing is in it.
    inline bool InCone(double heading, double centre, double distance, double yards, double degrees)
    {
        if (degrees <= 0 || yards <= 0 || distance < 0 || distance > yards)
            return false;
        double const half = degrees * 0.017453292519943295 / 2.0;
        return AngleBetween(heading, centre) <= half + 1e-9;
    }

    // Whether a member of the party stands within `yards` of the Demon Hunter (the end inclusive; no reach, nobody).
    inline bool InPartyRange(double distance, double yards)
    {
        return yards > 0 && distance >= 0 && distance <= yards;
    }

    // "Life Regeneration = 0.02 * Table(Healing, Effective_Level)": the boar's regeneration a second, from D3's Healing
    // table value at the level.
    inline double RegenPerSecond(double healingAtLevel, double share)
    {
        return healingAtLevel > 0 && share > 0 ? healingAtLevel * share : 0.0;
    }

    // Whole milliseconds of seconds, rounded to the nearest.
    inline std::uint32_t Millis(double seconds)
    {
        return seconds > 0 ? static_cast<std::uint32_t>(std::llround(seconds * 1000.0)) : 0u;
    }
} // namespace DC::Combat::DemonHunter::Companion
