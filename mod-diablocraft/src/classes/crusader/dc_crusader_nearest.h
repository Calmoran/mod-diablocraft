#pragma once
// Which enemies a skill reaches for among the ones around: the rule that needs no core type, header-only so the
// harnesses of the skills that use it (tests/crusader_smite) compile this exact code.
#include <algorithm>
#include <cstddef>
#include <vector>

namespace DC::Combat::Crusader
{
    // Of the candidates' distances from a centre, the indices of the nearest `count` inside the radius, nearest first
    // (a tie keeps the candidate order).
    inline std::vector<std::size_t> Nearest(std::vector<double> const& distances, double radius, std::size_t count)
    {
        std::vector<std::size_t> inside;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (distances[i] <= radius)
                inside.push_back(i);
        std::stable_sort(inside.begin(), inside.end(),
                         [&distances](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        if (inside.size() > count)
            inside.resize(count);
        return inside;
    }
} // namespace DC::Combat::Crusader
