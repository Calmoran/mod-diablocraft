// Offline harness for diablocraft-vucek (the Blacksmith-crafted rare follower relics). It compiles the two production headers
// src/items/dc_relic_rule.h (what a relic rolls) and src/items/dc_roll_class.h (which base items a drop can pick) and drives
// them with the values scripts/tests/items/test_rare_relics.py reads out of the sheets and the migration:
//
//   argv[1] primary_affixes  argv[2] secondary_affixes   (followers_rare_relics.csv, the rare relic's own counts)
//   argv[3] the rarity's primary affixes  argv[4] the rarity's secondary affixes (loot/full_roll_*_affixes)
//   argv[5] craft_only  (what followers_0007_rare_relics.sql writes into dc_base_item for the rare relics)
//   argv[6] the rare_relic_drops switch (followers_relic_rules.csv)
//
// It does NOT test the roller or the Blacksmith's craft themselves; those need a Player and a database and are the checks in
// docs/test-diablocraft-vucek.md.

#include "dc_relic_rule.h"
#include "dc_roll_class.h"

#include <cstdlib>
#include <iostream>
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
} // namespace

int main(int argc, char** argv)
{
    if (argc != 7)
    {
        std::cerr << "usage: rare_relic_tests primary secondary rarity_primary rarity_secondary craft_only drops\n";
        return 2;
    }
    DC::Relic::Roll const rare{static_cast<unsigned>(std::atoi(argv[1])), static_cast<unsigned>(std::atoi(argv[2]))};
    DC::Relic::Roll const rarity{static_cast<unsigned>(std::atoi(argv[3])), static_cast<unsigned>(std::atoi(argv[4]))};
    std::string const craftOnly = argv[5];
    bool const drops = std::atoi(argv[6]) != 0;
    DC::Relic::Roll const none;

    // A rare relic rolls a Rare's full budget (the sheet says 4 + 2, rarity_tiers.csv says the same), and it is still a relic:
    // the Templar's rolls block, an ordinary generic base does not.
    DC::Relic::Roll const rolled = DC::Relic::Counts(rare, rarity);
    Check(rolled.primary == rare.primary && rolled.secondary == rare.secondary, "a rare relic rolls its own counts");
    Check(rolled.primary == rarity.primary && rolled.secondary == rarity.secondary,
          "a rare relic rolls a Rare's full budget, as rarity_tiers.csv has it");
    // The same relic is not the rarity: it keeps its counts when the rarity asks for another budget, and any other base takes the
    // rarity's.
    DC::Relic::Roll const other{rarity.primary + 1, rarity.secondary + 1};
    Check(DC::Relic::Counts(rare, other).primary == rare.primary && DC::Relic::Counts(rare, other).secondary == rare.secondary,
          "a rare relic keeps its own counts whatever the rarity asks");
    Check(DC::Relic::Counts(none, rarity).primary == rarity.primary && DC::Relic::Counts(none, rarity).secondary == rarity.secondary,
          "any other base rolls its rarity's counts");
    Check(DC::Relic::IsRelic(rare) && !DC::Relic::IsRelic(none), "a rare relic has counts, so it is a relic");
    Check(DC::Relic::RollsBlock(false, rare) && !DC::Relic::RollsBlock(false, none),
          "block rolls on a relic and not on another generic base");
    // It is Rare, never Ancient: the base is a generic one, so the quality gate leaves it Legendary-less whatever the switch.
    Check(DC::Relic::Quality(rare, false, "normal") == "normal", "a rare relic asks for no quality");
    std::cout << "rare relic counts " << rolled.primary << "+" << rolled.secondary << "\n";

    // The drop pool: craft_only keeps the rare relic out of every drop; the switch is what turns it off.
    bool const inPool = DC::RollClass::InDropPool("", "yes", craftOnly, "no");
    Check(inPool == drops, "a rare relic is in the drop pool exactly when rare_relic_drops is 1");
    Check(!DC::RollClass::InDropPool("", "yes", "yes", "no"), "a craft_only base is never in the drop pool");
    Check(DC::RollClass::InDropPool("", "yes", "no", "no"), "a generic base that is not craft_only is in the drop pool");
    std::cout << "rare relic in drop pool " << (inPool ? "yes" : "no") << "\n";

    if (failures)
        return 1;
    std::cout << "rare relic rules OK\n";
    return 0;
}
