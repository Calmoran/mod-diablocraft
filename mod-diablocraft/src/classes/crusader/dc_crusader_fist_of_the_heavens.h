#pragma once
// Fist of the Heavens' rules that need no core type, header-only so tests/crusader_fist_of_the_heavens compiles this
// exact code: which rune is which, the headings of the bolts, which enemies a bolt reaches, and how far an enemy is
// from the ray a bolt flies along. The production half is dc_crusader_fist_of_the_heavens.cpp.
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Crusader::FistOfTheHeavens
{
    enum class Rune
    {
        None,
        HeavensTempest, // a storm cloud over the place
        Reverberation,  // the bolts' impact knocks away and slows
        Fissure,        // a fissure that burns, and arcs between fissures
        DivineWell,     // the bolts zap the enemies near them
        Retribution     // a fist that pierces on the way, a different explosion and bolts
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Heaven's Tempest")
            return Rune::HeavensTempest;
        if (rune == "Reverberation")
            return Rune::Reverberation;
        if (rune == "Fissure")
            return Rune::Fissure;
        if (rune == "Divine Well")
            return Rune::DivineWell;
        if (rune == "Retribution")
            return Rune::Retribution;
        return Rune::None;
    }

    // "The explosion creates {projectile_count} piercing charged bolts that arc outward": the heading of bolt `index`
    // of `count`, evenly round the circle from `first`.
    inline double BoltHeading(unsigned index, unsigned count, double first)
    {
        return count ? first + 2 * 3.14159265358979323846 * index / count : first;
    }

    // An enemy `along` yards down a bolt's ray and `across` yards off it is struck when it is within the ray's length
    // and half its width. No width, no strike.
    inline bool OnBolt(double along, double across, double length, double width)
    {
        return width > 0 && along >= 0 && along <= length && std::fabs(across) <= width / 2;
    }

    // The distance from a point (`along`, `across` the ray) to the ray from its start to `length`: Divine Well's bolts
    // "zap enemies within {radius_yards} yards as they travel".
    inline double RayDistance(double along, double across, double length)
    {
        if (along < 0)
            return std::hypot(along, across);
        if (along > length)
            return std::hypot(along - length, across);
        return std::fabs(across);
    }

    // The production half (dc_crusader_fist_of_the_heavens.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The explosion's hit, the engine's: 545%, Retribution's 435% (the other runes' damage_pct is the cloud's, the
    // fissure's and the zaps').
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast landed at `center`: the bolts, and what the rune adds.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::Crusader::FistOfTheHeavens
