// Offline harness for diablocraft-3gjoe (the follower relics' affix rolls and drop sources). It compiles the two
// production headers src/items/dc_relic_rule.h (what a relic rolls and the Ancient switch) and src/loot/dc_pick_rule.h
// (the weighted, tier-gated pick of a drop's base item) and drives them with the values
// scripts/tests/items/test_follower_relics.py reads out of the sheets:
//
//   argv[1] primary_affixes  argv[2] secondary_affixes  (followers_relic_rolls.csv)
//   argv[3] drop_weight      argv[4] min_tier            (followers_relic_rolls.csv)
//   argv[5] the rarity's primary affixes  argv[6] the rarity's secondary affixes (loot/full_roll_*_affixes)
//   argv[7] the ordinary drop weight (loot/ordinary_drop_weight in data/tunables/loot.csv)
//
// It does NOT test the roller or the loot roll themselves; those need a Player and a database and are the checks in
// docs/test-diablocraft-3gjoe.md.

#include "dc_pick_rule.h"
#include "dc_relic_rule.h"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <map>
#include <string>
#include <vector>

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
} // namespace

int main(int argc, char** argv)
{
    if (argc != 8)
    {
        std::cerr << "usage: relic_tests primary secondary weight min_tier rarity_primary rarity_secondary ordinary_weight\n";
        return 2;
    }
    DC::Relic::Roll const relic{static_cast<unsigned>(std::atoi(argv[1])), static_cast<unsigned>(std::atoi(argv[2]))};
    unsigned const weight = static_cast<unsigned>(std::atoi(argv[3]));
    unsigned const minTier = static_cast<unsigned>(std::atoi(argv[4]));
    DC::Relic::Roll const rarity{static_cast<unsigned>(std::atoi(argv[5])), static_cast<unsigned>(std::atoi(argv[6]))};
    unsigned const ordinaryWeight = static_cast<unsigned>(std::atoi(argv[7]));
    DC::Relic::Roll const none;

    // What it rolls: a relic its own counts, any other base the rarity's.
    DC::Relic::Roll const rolled = DC::Relic::Counts(relic, rarity);
    Check(rolled.primary == relic.primary && rolled.secondary == relic.secondary, "a relic rolls its own affix counts");
    DC::Relic::Roll const plain = DC::Relic::Counts(none, rarity);
    Check(plain.primary == rarity.primary && plain.secondary == rarity.secondary,
          "any other base rolls its rarity's counts");
    Check(DC::Relic::IsRelic(relic) && !DC::Relic::IsRelic(none), "only a base with counts is a relic");
    std::cout << "relic counts " << rolled.primary << "+" << rolled.secondary << " rarity counts " << plain.primary
              << "+" << plain.secondary << "\n";

    // The Ancient switch: off, a relic is Legendary whatever was asked; on, it takes the quality asked; no other base
    // is touched.
    for (std::string asked : {"normal", "ancient", "primal"})
    {
        Check(DC::Relic::Quality(relic, false, asked) == "normal",
              "a relic is Legendary only while the switch is off (" + asked + ")");
        Check(DC::Relic::Quality(relic, true, asked) == asked,
              "a relic takes the asked quality once the switch is on (" + asked + ")");
        Check(DC::Relic::Quality(none, false, asked) == asked,
              "the switch does not touch any other base (" + asked + ")");
        Check(DC::Relic::Quality(none, true, asked) == asked,
              "the switch does not touch any other base, on (" + asked + ")");
    }
    Check(!DC::Relic::MayBeAncient(relic, false) && DC::Relic::MayBeAncient(relic, true) &&
              DC::Relic::MayBeAncient(none, false),
          "MayBeAncient is the switch for a relic and open for everything else");

    // The Templar Relic rolls block like a shield; nothing else does.
    Check(DC::Relic::RollsBlock(true, none) && DC::Relic::RollsBlock(false, relic) &&
              !DC::Relic::RollsBlock(false, none),
          "block rolls on a shield and a relic only");

    // The pick: three ordinary bases and one relic, every roll of a fine sweep, so the share is measured exactly.
    using DC::Loot::Pick::Candidate;
    std::vector<Candidate> open{{1, ordinaryWeight, 0}, {2, ordinaryWeight, 0}, {3, ordinaryWeight, 0},
                                {9, weight, minTier}};
    constexpr unsigned steps = 1000000;
    std::map<std::uint32_t, unsigned> counts;
    for (unsigned i = 0; i < steps; ++i)
        ++counts[DC::Loot::Pick::Choose(open, (i + 0.5) / steps)];
    double const total = 3.0 * ordinaryWeight + weight;
    double const relicShare = counts[9] / double(steps);
    double const ordinaryShare = counts[1] / double(steps);
    std::cout << "relic share " << relicShare * 100 << "% ordinary share " << ordinaryShare * 100 << "%\n";
    Check(std::abs(relicShare - weight / total) < 1e-5, "a relic drops in proportion to its weight");
    Check(std::abs(ordinaryShare - ordinaryWeight / total) < 1e-5,
          "an ordinary base drops in proportion to its weight");
    Check(std::abs(double(counts[1]) - double(counts[2])) <= 1 && std::abs(double(counts[2]) - double(counts[3])) <= 1,
          "ordinary bases are as likely as each other");
    Check(DC::Loot::Pick::Choose(open, 0.0) == 1 && DC::Loot::Pick::Choose(open, 0.999999999) == 9,
          "the ends of the roll reach the first and the last candidate");
    Check(DC::Loot::Pick::Choose({}, 0.5) == 0, "nothing open picks nothing");

    // The tier gate: nothing below minTier, the relic from minTier up, an ordinary base at any tier, and a pick with no
    // tier (0) never.
    Check(!DC::Loot::Pick::Open(open.back(), minTier - 1), "a relic does not drop below its tier");
    Check(DC::Loot::Pick::Open(open.back(), minTier) && DC::Loot::Pick::Open(open.back(), minTier + 5),
          "a relic drops from its tier up");
    Check(!DC::Loot::Pick::Open(open.back(), 0), "a pick with no tier never reaches a relic");
    Check(DC::Loot::Pick::Open(open.front(), 0) && DC::Loot::Pick::Open(open.front(), 9),
          "an ordinary base drops at any tier");

    if (failures)
        return 1;
    std::cout << "relic rules OK\n";
    return 0;
}
