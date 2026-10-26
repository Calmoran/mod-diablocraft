/*
 * World of DiabloCraft - a legendary gem's numbers and its value at a rank.
 *
 * The numbers are the number columns of legendary_gems.csv (base value, amount per
 * rank, max rank, the rank-25 bonus values, the base effect's fixed numbers), generated into dc_legendary_gem and
 * checked against d3planner by scripts/test_legendary_gems.py. The gem's powers
 * (src/combat) and its tooltip both read the value at a rank through Value() here, so
 * neither carries a copy. Contract: docs/contracts/legendary-gems.md.
 *
 * The rank math has no core dependency, so the test compiles this exact function.
 */

#ifndef DC_LEGENDARY_GEM_H
#define DC_LEGENDARY_GEM_H

#include <cstdint>
#include <optional>
#include <string>

namespace DC::LegendaryGem
{
    // base + perRank * rank. A gem with a max rank stops levelling there: a higher
    // rank reads the max-rank value.
    inline double Scaled(double base, double perRank, std::optional<uint32_t> maxRank, uint32_t rank)
    {
        if (maxRank && rank > *maxRank)
            rank = *maxRank;
        return base + perRank * rank;
    }

    struct Row
    {
        std::string id, name;
        double base = 0, perRank = 0;
        std::optional<double> base2, perRank2; // the second scaling number (Zei's maximum at 50 yards)
        std::optional<uint32_t> maxRank;       // empty: no cap of its own
        std::optional<double> rank25[2];       // the numbers of the rank-25 bonus, in text order
        std::optional<double> fixed[3];        // the base effect's numbers that do not scale, in text order
    };

    // nullptr for a gem outside the 21 (not a row of dc_legendary_gem).
    Row const* Find(std::string const& gemId);

    // The first and second scaling number at a rank. Value2 is 0 for a gem with no second one.
    inline double Value(Row const& gem, uint32_t rank)
    {
        return Scaled(gem.base, gem.perRank, gem.maxRank, rank);
    }
    inline double Value2(Row const& gem, uint32_t rank)
    {
        return gem.base2 ? Scaled(*gem.base2, gem.perRank2.value_or(0), gem.maxRank, rank) : 0.0;
    }
} // namespace DC::LegendaryGem

#endif
