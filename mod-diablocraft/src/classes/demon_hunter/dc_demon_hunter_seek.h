#pragma once
// Which enemies a Demon Hunter skill reaches for among the ones around the enemy it struck: the rule that needs no core
// type, header-only so the harnesses of the skills that use it compile this exact code.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

namespace DC::Combat::DemonHunter
{
    // A cone of `coneDegrees` centred on `heading` (radians) takes a `bearing` (radians) within half the cone to either
    // side; 360 degrees or more is every direction.
    inline bool InCone(double heading, double bearing, double coneDegrees)
    {
        if (coneDegrees >= 360.0)
            return true;
        constexpr double Pi = 3.14159265358979323846;
        return std::fabs(std::remainder(bearing - heading, 2.0 * Pi)) <= coneDegrees * Pi / 360.0;
    }

    // Of the enemies around the one a skill struck last (their distances from it and their bearings from it, in
    // radians, and whether the skill struck them already), the indices of the nearest `count` not struck yet, inside
    // `radius` and inside the cone, nearest first (a tie keeps the candidate order). A cone of 360 degrees is every
    // direction.
    inline std::vector<std::size_t> Seek(std::vector<double> const& distances, std::vector<double> const& bearings,
                                         std::vector<bool> const& struck, double radius, double heading,
                                         double coneDegrees, std::size_t count)
    {
        std::vector<std::size_t> inside;
        for (std::size_t i = 0; i < distances.size() && i < bearings.size() && i < struck.size(); ++i)
            if (!struck[i] && distances[i] <= radius && InCone(heading, bearings[i], coneDegrees))
                inside.push_back(i);
        std::stable_sort(inside.begin(), inside.end(),
                         [&distances](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        if (inside.size() > count)
            inside.resize(count);
        return inside;
    }

    // Whether a point `dx`, `dy` yards from where a line starts (east and north) stands on the line: the line runs
    // `length` yards along `heading` (radians) and is `width` yards wide, half on each side. A line with no width takes
    // nobody.
    inline bool OnLine(double dx, double dy, double heading, double length, double width)
    {
        double const along = dx * std::cos(heading) + dy * std::sin(heading);
        double const across = -dx * std::sin(heading) + dy * std::cos(heading);
        return width > 0 && along >= 0 && along <= length && std::fabs(across) <= width / 2;
    }
} // namespace DC::Combat::DemonHunter
