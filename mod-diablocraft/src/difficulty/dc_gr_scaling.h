/*
 * World of DiabloCraft - Greater Rift monster scaling.
 *
 * The arithmetic only, no core: a level-1 Greater Rift monster has the base tier's Life and
 * damage (greater_rifts.csv equivalent_tier_gr1, Hard); each level above 1 multiplies Life by
 * one number and damage by the number of the band that level falls in; each party member beyond
 * the first adds a share of Life. Every number is a rifts tunable and arrives in GrNumbers.
 * Used by dc_difficulty.cpp (the creature scaling) and the elite affix damage.
 */

#ifndef DC_GR_SCALING_H
#define DC_GR_SCALING_H

#include <algorithm>
#include <cmath>

namespace DC::Difficulty
{
    // The level whose monsters are the base tier's (Greater Rift levels start at 1).
    constexpr unsigned GR_BASE_LEVEL = 1;

    struct GrNumbers
    {
        double lifePerLevel = 1.0;
        // Damage per level in three bands: low up to lowLast, mid up to midLast, high above.
        double damageLow = 1.0, damageMid = 1.0, damageHigh = 1.0;
        unsigned lowLast = 0, midLast = 0;
        double partyLifePctPerExtraMember = 0.0;
    };

    // False when a number would make the factors meaningless (bands out of order, a factor
    // at or below zero); the caller then refuses the level instead of scaling by it.
    inline bool GrNumbersValid(GrNumbers const& n)
    {
        return n.lifePerLevel >= 1.0 && n.damageLow >= 1.0 && n.damageMid >= 1.0 && n.damageHigh >= 1.0 &&
               n.lowLast >= GR_BASE_LEVEL && n.midLast >= n.lowLast && n.partyLifePctPerExtraMember >= 0.0 &&
               std::isfinite(n.lifePerLevel + n.damageLow + n.damageMid + n.damageHigh + n.partyLifePctPerExtraMember);
    }

    // Life of a level, relative to level 1.
    inline double GrLifeFactor(GrNumbers const& n, unsigned level)
    {
        return std::pow(n.lifePerLevel, static_cast<double>(std::max(level, GR_BASE_LEVEL) - GR_BASE_LEVEL));
    }

    // Damage of a level, relative to level 1: every level from 2 up multiplies by its own band's number.
    inline double GrDamageFactor(GrNumbers const& n, unsigned level)
    {
        unsigned const low = std::clamp(level, GR_BASE_LEVEL, n.lowLast) - GR_BASE_LEVEL;
        unsigned const mid = std::clamp(level, n.lowLast, n.midLast) - n.lowLast;
        unsigned const high = std::max(level, n.midLast) - n.midLast;
        return std::pow(n.damageLow, low) * std::pow(n.damageMid, mid) * std::pow(n.damageHigh, high);
    }

    // Life of the run's party, relative to a solo run; `players` is the headcount at the open.
    inline double GrPartyLifeFactor(GrNumbers const& n, unsigned players)
    {
        return 1.0 + n.partyLifePctPerExtraMember / 100.0 * (std::max(players, 1u) - 1);
    }
} // namespace DC::Difficulty

#endif // DC_GR_SCALING_H
