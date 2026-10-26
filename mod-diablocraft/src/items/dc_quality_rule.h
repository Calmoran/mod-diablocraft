/*
 * World of DiabloCraft - Ancient and Primal Ancient quality.
 *
 * Pure functions, so scripts/tests/loot/quality_tests.cpp compiles this exact header. The quality is
 * decided once, AT THE DROP, and travels with the item (the shell row, a held or ground drop's buffer
 * row, dc_item_instance.quality_tier); identify rolls inside that quality's bracket.
 */

#ifndef DC_QUALITY_RULE_H
#define DC_QUALITY_RULE_H

#include <algorithm>
#include <string>

namespace DC::Quality
{
    // Only a Legendary or Set item has an Ancient form (drop_rates.csv ancient_primal rows).
    inline bool Eligible(std::string const& rarity)
    {
        return rarity == "legendary" || rarity == "set";
    }

    struct Rule
    {
        double ancientPct = 0, primalPct = 0;   // loot/ancient_chance_pct, loot/primal_chance_pct
        unsigned minTier = 0, minItemLevel = 0; // loot/ancient_min_tier, loot/ancient_min_item_level
        unsigned gambleMinTier = 0;             // loot/ancient_min_tier_gamble: a gamble or craft needs the level only (D3)
    };

    // roll is uniform in [0, 1). Primal takes the first primalPct of it, Ancient the next ancientPct, so
    // each chance is exact and independent of the other (Primal 0.25% and Ancient 10% of legendary drops).
    // Both need the tier and item level; Primal also needs the account's solo Greater Rift unlock. A monster drop
    // needs minTier (Torment I); a gamble or craft (`gambled`: Kadala, the slot vendors, Kanai's Cube, artisan crafts)
    // needs gambleMinTier, D3's level 70 on any difficulty.
    inline std::string Decide(std::string const& rarity, Rule const& rule, unsigned tier, unsigned itemLevel,
                              bool primalUnlocked, double roll, bool gambled = false)
    {
        unsigned const minTier = gambled ? rule.gambleMinTier : rule.minTier;
        if (!Eligible(rarity) || tier < minTier || itemLevel < rule.minItemLevel)
            return "normal";
        double const primal = primalUnlocked ? std::clamp(rule.primalPct, 0.0, 100.0) : 0.0;
        double const ancient = std::clamp(rule.ancientPct, 0.0, 100.0);
        double const pct = roll * 100.0;
        if (pct < primal)
            return "primal";
        return pct < primal + ancient ? "ancient" : "normal";
    }

    // The statLimits bracket a roll reads. An Ancient reads the ancient rows, a Primal the primal rows
    // (D3Planner's primal = ancient); every other item keeps the old rarity-only choice.
    inline std::string Bracket(std::string const& rarity, std::string const& quality)
    {
        if (Eligible(rarity) && (quality == "ancient" || quality == "primal"))
            return quality;
        return (rarity == "legendary" || rarity == "set" || rarity == "ethereal") ? "legendary" : "rare";
    }

    // A Primal rolls every affix at the top of the ancient bracket (and every socket row at its
    // highest count); anything else rolls inside its range.
    inline bool AtTop(std::string const& quality)
    {
        return quality == "primal";
    }

    // A stored or passed tier that is not one of the three is the old default.
    inline std::string Clean(std::string const& quality)
    {
        return quality == "ancient" || quality == "primal" ? quality : "normal";
    }
} // namespace DC::Quality

#endif
