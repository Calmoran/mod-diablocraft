#pragma once
// The picks of enemies several Demon Hunter skills make (Strafe's shots, Multishot's and Cluster Arrow's rockets), header-only so the harnesses of
// the skills that use it compile this exact code.
#include <algorithm>
#include <cstddef>
#include <numeric>
#include <vector>

namespace DC::Combat::DemonHunter
{
    // "at random nearby enemies": the enemy a roll of 0 up to 1 picks among `count`, evenly and never past the last. None to pick, none picked.
    inline std::size_t PickAt(double roll, std::size_t count)
    {
        return count ? std::min(count - 1, std::size_t(std::max(0.0, roll) * double(count))) : 0;
    }

    // "rockets at nearby enemies": the places in `distances` of the `count` nearest, nearest first, a tie keeping its order.
    inline std::vector<std::size_t> NearestFirst(std::vector<double> const& distances, std::size_t count)
    {
        std::vector<std::size_t> order(distances.size());
        std::iota(order.begin(), order.end(), std::size_t(0));
        std::stable_sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        order.resize(std::min(order.size(), count));
        return order;
    }
} // namespace DC::Combat::DemonHunter
