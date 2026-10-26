/*
 * World of DiabloCraft - which eligible base item a drop rolls.
 *
 * Pure functions, so scripts/tests/loot/pick_tests.cpp compiles this exact header. Every eligible base item has a
 * weight and a lowest difficulty tier it drops at. The weight of an ordinary base is the tunable loot/ordinary_drop_weight
 * (D3's 100, d3planner dropData: the common weight); the follower relics carry 33 (data/d3/followers_relic_rolls.csv), a
 * third of an ordinary legendary, and drop from Torment I.
 */

#ifndef DC_PICK_RULE_H
#define DC_PICK_RULE_H

#include <cstdint>
#include <vector>

namespace DC::Loot::Pick
{
    struct Candidate
    {
        std::uint32_t entry = 0;
        unsigned weight = 0;
        unsigned minTier = 0; // the lowest difficulty tier id that drops it; 0 for any
    };

    // A pick with no tier of its own (Kadala's gamble, the Cube) passes 0 and so never reaches an item with a tier
    // gate.
    inline bool Open(Candidate const& candidate, unsigned tier)
    {
        return tier >= candidate.minTier;
    }

    // roll is uniform in [0, 1): the candidate whose weight span holds it; 0 when there is none.
    inline std::uint32_t Choose(std::vector<Candidate> const& open, double roll)
    {
        unsigned long long total = 0;
        for (Candidate const& candidate : open)
            total += candidate.weight;
        if (total == 0)
            return 0;
        double const target = roll * static_cast<double>(total);
        unsigned long long below = 0;
        for (Candidate const& candidate : open)
        {
            below += candidate.weight;
            if (target < static_cast<double>(below))
                return candidate.entry;
        }
        return open.back().entry;
    }
} // namespace DC::Loot::Pick

#endif
