#pragma once
// Earth Elemental's rules that need no core type, header-only so tests/shaman_earth_elemental compiles this exact code:
// which rune is which, how many stomps fit its seconds, which damage reduction a rune states, what a zone deals each
// tick and who stands outside the stomp's reach. The production half is dc_shaman_earth_elemental.cpp.
#include "../../combat/dc_periodic_strike.h"

#include <cmath>
#include <cstdint>
#include <string_view>

class Player;
struct Position;

namespace DC::Combat::Shaman::EarthElemental
{
    enum class Rune
    {
        None,
        Bedrock,              // you take more less damage
        PrimalEarthElemental, // each stomp makes a small Earthquake, Physical
        MagmaColossus,        // each stomp leaves a lava pool, Fire
        ThunderColossus,      // each stomp stuns and arcs to enemies outside the reach, Lightning
        GlacialColossus       // each stomp freezes and marks, Cold
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Bedrock")
            return Rune::Bedrock;
        if (name == "Primal Earth Elemental")
            return Rune::PrimalEarthElemental;
        if (name == "Magma Colossus")
            return Rune::MagmaColossus;
        if (name == "Thunder Colossus")
            return Rune::ThunderColossus;
        if (name == "Glacial Colossus")
            return Rune::GlacialColossus;
        return Rune::None;
    }

    // "You take {damage_reduction_pct:new} less damage instead of {damage_reduction_pct:base}": the qualifier of the
    // number a rune's record states for the damage reduction. Bedrock states the new one; every other rune the skill's
    // plain one.
    inline std::string_view ReductionQualifier(Rune rune)
    {
        return rune == Rune::Bedrock ? "new" : "";
    }

    // How many stomps fit `seconds` at one every `intervalSeconds`. None for no interval.
    inline unsigned Stomps(double seconds, double intervalSeconds)
    {
        return DC::Combat::PeriodicStrike::Ticks(seconds, intervalSeconds);
    }

    // Primal Earth Elemental and Magma Colossus: the weapon damage percent of one tick of a zone whose sheet number is
    // per second.
    inline double ZoneTickPct(double perSecondPct, double tickSeconds)
    {
        return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;
    }

    // Thunder Colossus: whether an enemy at (`ex`, `ey`) stands outside the stomp's reach of `radius` yards about
    // (`cx`, `cy`).
    inline bool Outside(double cx, double cy, double ex, double ey, double radius)
    {
        return std::hypot(ex - cx, ey - cy) > radius;
    }

    // Whether an elemental that ends at `untilMs` still stands at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // The production half (dc_shaman_earth_elemental.cpp), called from dc_shaman.cpp.
    bool Is(std::uint32_t spellId);
    // The cast of an Earth Elemental resolved at `center`: it rises there, replacing the one that stood.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // Defines the creature the elemental shows as (at startup).
    void RegisterScripts();
} // namespace DC::Combat::Shaman::EarthElemental
