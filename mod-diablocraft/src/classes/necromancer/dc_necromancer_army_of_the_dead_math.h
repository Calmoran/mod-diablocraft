#pragma once
// The rules of Army of the Dead's runes that need no core type, header-only so tests/necromancer_army_of_the_dead compiles
// this exact code: which rune is which, how a total is cut into blasts, ticks and attacks and when each comes, which enemies
// stand on Frozen Army's line, and how Death Valley's pull closes in. The production half is
// dc_necromancer_army_of_the_dead.cpp.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <string_view>

namespace DC::Combat::Necromancer::ArmyOfTheDead
{
    enum class Rune
    {
        None,
        BlightedGrasp,
        FrozenArmy,
        UnconventionalWarfare,
        DeathValley,
        DeadStorm
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Blighted Grasp")
            return Rune::BlightedGrasp;
        if (name == "Frozen Army")
            return Rune::FrozenArmy;
        if (name == "Unconventional Warfare")
            return Rune::UnconventionalWarfare;
        if (name == "Death Valley")
            return Rune::DeathValley;
        if (name == "Dead Storm")
            return Rune::DeadStorm;
        return Rune::None;
    }

    // A total weapon damage cut into `parts` equal blows; no parts, no blow.
    inline double Share(double totalPct, unsigned parts)
    {
        return parts ? totalPct / parts : 0.0;
    }

    // When the `index`th of `parts` blows that fill `seconds` comes, after the first at once. None for no parts.
    inline double OffsetSeconds(unsigned index, double seconds, unsigned parts)
    {
        return parts && seconds > 0 ? index * seconds / parts : 0.0;
    }

    // Whether an enemy at (ex, ey) stands on the line that leaves (px, py) along the unit direction (dx, dy), `length` long and
    // `width` wide (the edge counted).
    inline bool OnLine(double px, double py, double dx, double dy, double ex, double ey, double length, double width)
    {
        double const rx = ex - px, ry = ey - py;
        double const along = rx * dx + ry * dy;
        double const aside = std::fabs(rx * dy - ry * dx);
        return along >= 0 && along <= length && aside <= width / 2.0;
    }

    // Death Valley's pull closes from `start` yards to `end` in steps of `size` yards: how many steps, the radius after
    // each, and whether an enemy at `distance` is outside it and is drawn in.
    inline unsigned PullSteps(double start, double end, double size)
    {
        return size > 0 && start > end ? static_cast<unsigned>(std::ceil((start - end) / size - 1e-9)) : 0u;
    }

    inline double PullRadius(unsigned step, double start, double end, double size)
    {
        return std::max(end, start - step * size);
    }

    inline bool Drawn(double distance, double radius)
    {
        return distance > radius;
    }
} // namespace DC::Combat::Necromancer::ArmyOfTheDead
