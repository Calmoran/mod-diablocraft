#pragma once
// The pick of an enemy several Witch Doctor skills make (Corpse Spiders' bites, Haunt's and Locust Swarm's jumps), header-only so the harnesses of
// the skills that use it compile this exact code.
#include <algorithm>
#include <cstddef>
#include <optional>
#include <vector>

namespace DC::Combat::WitchDoctor
{
    // "attack nearby enemies": the enemy a roll of 0 up to 1 picks among `count`, evenly and never past the last. None
    // to pick, none picked.
    inline std::size_t PickAt(double roll, std::size_t count)
    {
        return count ? std::min(count - 1, std::size_t(std::max(0.0, roll) * double(count))) : 0;
    }

    // The nearest of `distances` (to the spot a spirit or a swarm jumps from): its index, none when there is no enemy.
    inline std::optional<std::size_t> Nearest(std::vector<double> const& distances)
    {
        if (distances.empty())
            return std::nullopt;
        return static_cast<std::size_t>(std::min_element(distances.begin(), distances.end()) - distances.begin());
    }
} // namespace DC::Combat::WitchDoctor
