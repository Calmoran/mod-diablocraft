#pragma once
// Heaven's Fury's rules that need no core type, header-only so tests/crusader_heavens_fury compiles this exact code: which
// rune is which, which ray each deals, how a total is paid in ticks, where Split Fury's beams stand, and what the beam of
// Fires of Heaven reaches. The production half is dc_crusader_heavens_fury.cpp.
#include "dc_crusader_dot.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
struct Position;

namespace DC::Combat::Crusader::HeavensFury
{
    enum class Rune
    {
        None,
        Ascendancy,       // a wider ray with a heavier total
        BlessedGround,    // the ground the ray touched burns on
        SplitFury,        // three smaller beams
        ThouShaltNotPass, // the ground stops enemies
        FiresOfHeaven     // one beam through the Crusader, no cooldown
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Ascendancy")
            return Rune::Ascendancy;
        if (rune == "Blessed Ground")
            return Rune::BlessedGround;
        if (rune == "Split Fury")
            return Rune::SplitFury;
        if (rune == "Thou Shalt Not Pass")
            return Rune::ThouShaltNotPass;
        if (rune == "Fires of Heaven")
            return Rune::FiresOfHeaven;
        return Rune::None;
    }

    // The skill's own ray (its total over its seconds, in the area it names) is the ray of the skill and of the two runes
    // that add to it; Ascendancy and Split Fury put their own in its place, and Fires of Heaven is a beam instead.
    inline bool KeepsBaseRay(Rune rune)
    {
        return rune == Rune::None || rune == Rune::BlessedGround || rune == Rune::ThouShaltNotPass;
    }

    // "dealing {damage_pct} weapon damage over {dot_duration_seconds} seconds": the total paid in the ticks that fit the
    // seconds, whole. Nothing for a total, a time or a tick of 0.
    inline double PctPerTick(double totalPct, double seconds, double tickSeconds)
    {
        return totalPct > 0 ? Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds)) : 0.0;
    }

    // Split Fury: the smaller beams stand on a ring inside the ray's area, each wholly in it: the ring is the area's radius
    // less a beam's. Nothing negative.
    inline double RingYards(double areaRadius, double beamRadius)
    {
        return std::max(0.0, areaRadius - beamRadius);
    }

    // The heading of beam `index` of `count`, evenly round the circle from `start`.
    inline double BeamHeading(unsigned index, unsigned count, double start)
    {
        return count ? start + 2.0 * M_PI * index / count : start;
    }

    // Fires of Heaven: a point `dx`, `dy` from the Crusader, with the beam going out at `heading`, is `along` the beam and
    // `across` it by these.
    inline double Along(double dx, double dy, double heading)
    {
        return dx * std::cos(heading) + dy * std::sin(heading);
    }

    inline double Across(double dx, double dy, double heading)
    {
        return -dx * std::sin(heading) + dy * std::cos(heading);
    }

    // "focused through you in a beam across the battlefield": from the Crusader out to the distance, the radius to each side.
    inline bool InBeam(double along, double across, double distance, double radius)
    {
        return along >= 0 && along <= distance && std::fabs(across) <= radius;
    }

    // The production half (dc_crusader_heavens_fury.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The cast itself deals no hit: the ray is ticks, the beam is struck in Ground. 0 for the skill and every rune.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast was aimed at `center`: the ray, the ground, the beams or the beam.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::Crusader::HeavensFury
