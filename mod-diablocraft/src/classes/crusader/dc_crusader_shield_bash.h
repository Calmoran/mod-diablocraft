#pragma once
// Shield Bash's rules that need no core type, header-only so tests/crusader_shield_bash compiles this exact code: which
// rune is which, where the charge stops, which enemies stand in the bash's cone, in the wider cone Shattered Shield
// reaches and on Shield Cross's arms. The production half is dc_crusader_shield_bash.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <utility>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::ShieldBash
{
    enum class Rune
    {
        None,
        Crumble,         // a heavier hit
        ShatteredShield, // fragments reach more enemies around the bash
        ShieldCross,     // additional shields in a cross
        Pound,           // a much heavier hit in a short, narrow reach
        OneOnOne         // the target stunned, the others knocked back
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Crumble")
            return Rune::Crumble;
        if (rune == "Shattered Shield")
            return Rune::ShatteredShield;
        if (rune == "Shield Cross")
            return Rune::ShieldCross;
        if (rune == "Pound")
            return Rune::Pound;
        if (rune == "One on One")
            return Rune::OneOnOne;
        return Rune::None;
    }

    // The runes whose damage_pct and block share are the bash's own hit. Shattered Shield's and Shield Cross's numbers
    // are the fragments' and the extra shields', and the bash itself stays the skill's.
    inline bool ReplacesHit(Rune rune)
    {
        return rune == Rune::Crumble || rune == Rune::Pound;
    }

    struct Point
    {
        double x = 0, y = 0;
    };

    // "Charge at your enemy": where the Crusader ends, on the line to the enemy and `stop` yards short of it; where it
    // stands when the enemy is already that near.
    inline Point Landing(Point from, Point to, double stop)
    {
        double const distance = std::hypot(to.x - from.x, to.y - from.y);
        if (distance <= stop || distance <= 0)
            return from;
        double const share = (distance - stop) / distance;
        return {from.x + (to.x - from.x) * share, from.y + (to.y - from.y) * share};
    }

    inline double ArcRadians(double degrees)
    {
        return degrees * 3.14159265358979323846 / 180.0;
    }

    // The angle between two headings, 0 to pi.
    inline double AngleOff(double a, double b)
    {
        double const pi = 3.14159265358979323846;
        double off = std::fmod(std::fabs(a - b), 2 * pi);
        return off > pi ? 2 * pi - off : off;
    }

    // The cone in front: an enemy `distance` yards away whose heading is `angleOff` radians off the bash's.
    inline bool InCone(double distance, double angleOff, double radius, double arc)
    {
        return radius > 0 && distance <= radius && angleOff <= arc / 2;
    }

    // Shattered Shield: "hitting more enemies": inside the wider cone and not in the bash's own.
    inline bool Fragment(double distance, double angleOff, double radius, double arc, double extraRadius,
                         double extraArc)
    {
        return InCone(distance, angleOff, radius + extraRadius, arc + extraArc) &&
               !InCone(distance, angleOff, radius, arc);
    }

    // Shield Cross: four arms from the Crusader at right angles, the first along the facing; an enemy at (dx, dy) from
    // the Crusader is on an arm when it is within `length` along it and within half the `width` across it. No length or
    // no width is no arm.
    inline bool OnCross(double dx, double dy, double facing, double length, double width)
    {
        if (length <= 0 || width <= 0)
            return false;
        for (int arm = 0; arm < 4; ++arm)
        {
            double const heading = facing + arm * 3.14159265358979323846 / 2;
            double const along = dx * std::cos(heading) + dy * std::sin(heading);
            double const across = -dx * std::sin(heading) + dy * std::cos(heading);
            if (along >= 0 && along <= length && std::fabs(across) <= width / 2)
                return true;
        }
        return false;
    }

    // The production half (dc_crusader_shield_bash.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The bash's own hit: its weapon damage percentage, Crumble's or Pound's where the rune replaces it.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The bash's own weapon damage and block share, for the hit's multiplier.
    std::optional<std::pair<double, double>> Main(std::uint32_t spellId);
    // Before the hits: the charge to the enemy aimed at.
    void Approach(Player* player, std::uint32_t spellId, Unit* target);
    // After the hit on `targets.front()`: the other enemies the bash reaches and what the rune adds.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Crusader::ShieldBash
