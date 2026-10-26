/*
 * World of DiabloCraft - the follower relics' roll rules.
 *
 * Pure functions, so scripts/tests/items/relic_tests.cpp compiles this exact header. A relic is a legendary base item
 * (dc_follower_relic_roll, data/d3/followers_relic_rolls.csv) that rolls D3's own number of affixes, 4 primary and 1
 * secondary, from its own pool (data/d3/followers_relic_pools.csv); whether it can be Ancient or Primal Ancient is the
 * one switch of data/d3/followers_relic_rules.csv.
 */

#ifndef DC_RELIC_RULE_H
#define DC_RELIC_RULE_H

#include <string>

namespace DC::Relic
{
    struct Roll
    {
        unsigned primary = 0, secondary = 0; // 0 and 0: not a relic
    };

    inline bool IsRelic(Roll const& roll)
    {
        return roll.primary + roll.secondary > 0;
    }

    // The affix counts of a roll: a relic's own, else the rarity's.
    inline Roll Counts(Roll const& relic, Roll const& rarity)
    {
        return IsRelic(relic) ? relic : rarity;
    }

    // Whether a base may roll Ancient or Primal Ancient: every base but a relic, and a relic only once the switch is on.
    inline bool MayBeAncient(Roll const& relic, bool ancientPrimal)
    {
        return !IsRelic(relic) || ancientPrimal;
    }

    // The quality a base rolls in: a relic is Legendary (normal) while the switch is off, whatever was asked.
    inline std::string Quality(Roll const& relic, bool ancientPrimal, std::string const& asked)
    {
        return MayBeAncient(relic, ancientPrimal) ? asked : "normal";
    }

    // A relic rolls "+X% Chance to Block" (the Templar Relic's own affix, slots.js blockRelic) like a shield does.
    inline bool RollsBlock(bool shield, Roll const& relic)
    {
        return shield || IsRelic(relic);
    }
} // namespace DC::Relic

#endif
