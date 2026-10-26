// Offline harness for diablocraft-t3t8 (Ancient and Primal Ancient). It compiles the production header
// src/items/dc_quality_rule.h - the functions dc_items.cpp calls - and drives it with the loot tunables
// scripts/tests/items/test_ancient_primal.py reads out of the generated tunables SQL:
//
//   argv[1] ancient_chance_pct  argv[2] primal_chance_pct  argv[3] ancient_min_tier  argv[4] ancient_min_item_level
//   argv[5] ancient_min_tier_gamble (Kadala, slot vendors, the Cube and artisans: level 70 on any tier)
//
// It does NOT test the roller, delivery or the database; those need a Player and are the GM steps in
// docs/test-diablocraft-t3t8.md.

#include "dc_quality_rule.h"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <map>
#include <string>

namespace
{
    unsigned failures = 0;

    void Check(bool ok, std::string const& message)
    {
        if (!ok)
        {
            std::cerr << "FAILED: " << message << "\n";
            ++failures;
        }
    }

    // Every roll of a fine uniform sweep, so a chance is measured exactly rather than sampled.
    std::map<std::string, unsigned> Sweep(std::string const& rarity, DC::Quality::Rule const& rule, unsigned tier,
                                          unsigned level, bool unlocked, bool gambled = false)
    {
        constexpr unsigned steps = 1000000;
        std::map<std::string, unsigned> counts;
        for (unsigned i = 0; i < steps; ++i)
            ++counts[DC::Quality::Decide(rarity, rule, tier, level, unlocked, (i + 0.5) / steps, gambled)];
        return counts;
    }

    double Pct(unsigned n)
    {
        return n / 10000.0;
    }
} // namespace

int main(int argc, char** argv)
{
    if (argc != 6)
    {
        std::cerr << "usage: quality_tests ancient_pct primal_pct min_tier min_item_level min_tier_gamble\n";
        return 2;
    }
    DC::Quality::Rule rule;
    rule.ancientPct = std::atof(argv[1]);
    rule.primalPct = std::atof(argv[2]);
    rule.minTier = static_cast<unsigned>(std::atoi(argv[3]));
    rule.minItemLevel = static_cast<unsigned>(std::atoi(argv[4]));
    rule.gambleMinTier = static_cast<unsigned>(std::atoi(argv[5]));

    for (std::string rarity : {"legendary", "set"})
    {
        auto unlocked = Sweep(rarity, rule, rule.minTier, rule.minItemLevel, true);
        std::cout << rarity << " unlocked ancient=" << Pct(unlocked["ancient"])
                  << "% primal=" << Pct(unlocked["primal"]) << "%\n";
        Check(std::abs(Pct(unlocked["ancient"]) - rule.ancientPct) < 0.001, rarity + ": Ancient is exactly its chance");
        Check(std::abs(Pct(unlocked["primal"]) - rule.primalPct) < 0.001, rarity + ": Primal is exactly its chance");

        auto locked = Sweep(rarity, rule, rule.minTier, rule.minItemLevel, false);
        std::cout << rarity << " locked ancient=" << Pct(locked["ancient"]) << "% primal=" << Pct(locked["primal"])
                  << "%\n";
        Check(locked["primal"] == 0, rarity + ": no Primal before the solo Greater Rift unlock");
        Check(std::abs(Pct(locked["ancient"]) - rule.ancientPct) < 0.001,
              rarity + ": locked Primals leave Ancient at its chance");

        auto lowTier = Sweep(rarity, rule, rule.minTier - 1, rule.minItemLevel, true);
        Check(lowTier["ancient"] == 0 && lowTier["primal"] == 0, rarity + ": nothing Ancient below the minimum tier");
        auto lowLevel = Sweep(rarity, rule, rule.minTier, rule.minItemLevel - 1, true);
        Check(lowLevel["ancient"] == 0 && lowLevel["primal"] == 0,
              rarity + ": nothing Ancient below the minimum item level");
        auto high = Sweep(rarity, rule, rule.minTier + 5, rule.minItemLevel + 5, true);
        Check(high["ancient"] > 0 && high["primal"] > 0, rarity + ": higher tiers and levels still qualify");

        // A gamble or craft needs the level only; a monster drop keeps the tier.
        auto drop = Sweep(rarity, rule, 1, rule.minItemLevel, true);
        Check(drop["ancient"] == 0 && drop["primal"] == 0, rarity + ": a monster drop on Normal is never Ancient");
        auto gamble = Sweep(rarity, rule, 1, rule.minItemLevel, true, true);
        std::cout << rarity << " gamble on Normal ancient=" << Pct(gamble["ancient"]) << "% primal=" << Pct(gamble["primal"])
                  << "%\n";
        Check(std::abs(Pct(gamble["ancient"]) - rule.ancientPct) < 0.001,
              rarity + ": a gamble on Normal is Ancient at its chance");
        Check(std::abs(Pct(gamble["primal"]) - rule.primalPct) < 0.001,
              rarity + ": a gamble on Normal is Primal at its chance once unlocked");
        auto gambleLow = Sweep(rarity, rule, 1, rule.minItemLevel - 1, true, true);
        Check(gambleLow["ancient"] == 0 && gambleLow["primal"] == 0, rarity + ": a gamble below level 70 is never Ancient");
        auto gambleLocked = Sweep(rarity, rule, 1, rule.minItemLevel, false, true);
        Check(gambleLocked["primal"] == 0, rarity + ": a gamble is not Primal before the unlock");
    }

    // Only Legendary and Set have an Ancient form.
    for (std::string rarity : {"rare", "magic", "normal", "ethereal", ""})
    {
        auto counts = Sweep(rarity, rule, rule.minTier + 5, rule.minItemLevel + 5, true);
        Check(counts["ancient"] == 0 && counts["primal"] == 0, "'" + rarity + "' never rolls Ancient or Primal");
        auto gambled = Sweep(rarity, rule, 1, rule.minItemLevel + 5, true, true);
        Check(gambled["ancient"] == 0 && gambled["primal"] == 0, "'" + rarity + "' never gambles Ancient or Primal");
    }

    // A chance above 100 or below 0 is held inside the roll.
    DC::Quality::Rule wild = rule;
    wild.ancientPct = 250;
    wild.primalPct = -5;
    Check(DC::Quality::Decide("legendary", wild, 99, 99, true, 0.5) == "ancient",
          "chance above 100 means always Ancient");
    Check(DC::Quality::Decide("legendary", wild, 99, 99, true, 0.999999) == "ancient",
          "chance above 100 holds to the last roll");

    // The bracket the roller reads.
    Check(DC::Quality::Bracket("legendary", "ancient") == "ancient", "Ancient legendary reads the ancient bracket");
    Check(DC::Quality::Bracket("set", "ancient") == "ancient", "Ancient set reads the ancient bracket");
    Check(DC::Quality::Bracket("legendary", "primal") == "primal", "Primal legendary reads the primal bracket");
    Check(DC::Quality::Bracket("set", "primal") == "primal", "Primal set reads the primal bracket");
    Check(DC::Quality::Bracket("legendary", "normal") == "legendary", "a normal legendary keeps the legendary bracket");
    Check(DC::Quality::Bracket("rare", "ancient") == "rare", "a rare cannot read the ancient bracket");
    Check(DC::Quality::Bracket("ethereal", "normal") == "legendary", "an ethereal keeps the legendary bracket");
    Check(DC::Quality::Bracket("magic", "normal") == "rare", "a magic keeps the rare bracket");

    Check(DC::Quality::AtTop("primal") && !DC::Quality::AtTop("ancient") && !DC::Quality::AtTop("normal"),
          "only a Primal rolls at the top");
    Check(DC::Quality::Clean("primal") == "primal" && DC::Quality::Clean("ancient") == "ancient" &&
              DC::Quality::Clean("") == "normal" && DC::Quality::Clean("x'; DROP") == "normal",
          "a stored or passed tier outside the three reads as normal");

    if (failures)
        return 1;
    std::cout << "quality rules OK\n";
    return 0;
}
