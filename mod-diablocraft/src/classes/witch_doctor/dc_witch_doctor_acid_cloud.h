#pragma once
// Acid Cloud's rules that need no core type, header-only so tests/witch_doctor_acid_cloud compiles this exact code:
// which rune is which, which element each part takes, when the impact lands, which enemies a burst reaches, which stand
// in Kiss of Death's cone and what a pool tick deals. The production half is dc_witch_doctor_acid_cloud.cpp.
#include "../../combat/dc_periodic_strike.h"

#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::WitchDoctor::AcidCloud
{
    enum class Rune
    {
        None,
        CorpseBomb,  // a corpse explodes in place of the impact, Fire
        AcidRain,    // a wider impact, the outer ring a little later, Poison
        LobBlobBomb, // the pool is a slime that lasts longer and reaches further, Poison
        SlowBurn,    // the pool is frost that lasts longer, Cold
        KissOfDeath  // a cone of acid in place of the cloud, Poison
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Corpse Bomb")
            return Rune::CorpseBomb;
        if (name == "Acid Rain")
            return Rune::AcidRain;
        if (name == "Lob Blob Bomb")
            return Rune::LobBlobBomb;
        if (name == "Slow Burn")
            return Rune::SlowBurn;
        if (name == "Kiss of Death")
            return Rune::KissOfDeath;
        return Rune::None;
    }

    // Slow Burn names Cold for its pools, so its impact stays the skill's Poison.
    inline bool ImpactTakesRuneElement(Rune rune)
    {
        return rune != Rune::SlowBurn;
    }

    // Corpse Bomb names Fire for its explosion, so its pool stays the skill's Poison.
    inline bool PoolTakesRuneElement(Rune rune)
    {
        return rune != Rune::CorpseBomb;
    }

    // The seconds from the cast to the impact: the skill's, Corpse Bomb's later, Kiss of Death's own.
    inline double ImpactDelaySeconds(Rune rune, double base, double corpse, double barf)
    {
        return rune == Rune::CorpseBomb ? corpse : rune == Rune::KissOfDeath ? barf : base;
    }

    // Whether an enemy `distance` yards from the impact is in the band `inner` (outside it) to `outer` (inside it): a
    // burst reaches the band; the first has no inner edge (a negative one).
    inline bool InBand(double distance, double inner, double outer)
    {
        return distance > inner && distance <= outer;
    }

    // Whether a point `dx`, `dy` yards from where the cone starts (east and north) stands in it: it reaches `length`
    // yards along `heading` (radians) and is `degrees` wide, half on each side.
    inline bool InCone(double dx, double dy, double heading, double length, double degrees)
    {
        double const distance = std::hypot(dx, dy);
        if (distance > length)
            return false;
        if (distance < 1e-9)
            return true;
        constexpr double Pi = 3.14159265358979323846;
        double off = std::fabs(std::atan2(dy, dx) - heading);
        off = std::fmod(off, 2 * Pi);
        if (off > Pi)
            off = 2 * Pi - off;
        return off <= degrees * Pi / 360.0 + 1e-9;
    }

    // "{damage_pct} weapon damage over {dot_duration_seconds} seconds" in ticks of `tickSeconds`: the percent of one
    // tick.
    inline double TickPct(double totalPct, double seconds, double tickSeconds)
    {
        return PeriodicStrike::TickPct(totalPct, PeriodicStrike::Ticks(seconds, tickSeconds));
    }

    // The production half (dc_witch_doctor_acid_cloud.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The cast's own hit: none; the impact and the pool strike for themselves.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast went off at `center`: the impact, and the pool, slime or cone after it.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::WitchDoctor::AcidCloud
