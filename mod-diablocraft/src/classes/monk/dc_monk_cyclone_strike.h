#pragma once
// Cyclone Strike's rules that need no core type, header-only so
// tests/monk_cyclone_strike compiles this exact code. "Pull up to {target_count} enemies within {radius_yards} yards
// towards you, followed by a furious blast": which enemies are pulled (the nearest), where each lands
// (Power/Monk_CycloneStrike.pow SF_0 + SF_6: between 1 and 9 yards from the Monk, on the line it came along) and who
// the blast then reaches (SF_3 radius 10).
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <numeric>
#include <vector>

namespace DC::Combat::Monk::CycloneStrike
{
    struct Point
    {
        double x = 0, y = 0;
    };

    // The indices of the `count` nearest of the distances, nearest first (a tie keeps the earlier one first).
    inline std::vector<std::size_t> Nearest(std::vector<double> const& distances, unsigned count)
    {
        std::vector<std::size_t> order(distances.size());
        std::iota(order.begin(), order.end(), std::size_t(0));
        std::stable_sort(order.begin(), order.end(),
                         [&](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        order.resize(std::min<std::size_t>(order.size(), count));
        return order;
    }

    // How far from the Monk a pulled enemy lands: SF_0 plus a share (0 to 1) of SF_6.
    inline double LandingYards(double minYards, double spreadYards, double share)
    {
        return minYards + spreadYards * std::clamp(share, 0.0, 1.0);
    }

    // The landing point: `yards` from the Monk on the line towards the enemy (straight ahead along +x if it stands on
    // the Monk).
    inline Point Landing(Point monk, Point enemy, double yards)
    {
        double const dx = enemy.x - monk.x, dy = enemy.y - monk.y, length = std::hypot(dx, dy);
        if (length < 1e-6)
            return {monk.x + yards, monk.y};
        return {monk.x + dx / length * yards, monk.y + dy / length * yards};
    }

    // Whether the blast reaches a point: inside `radiusYards` of the Monk.
    inline bool InBlast(Point monk, double radiusYards, Point at)
    {
        return std::hypot(at.x - monk.x, at.y - monk.y) <= radiusYards;
    }
} // namespace DC::Combat::Monk::CycloneStrike
