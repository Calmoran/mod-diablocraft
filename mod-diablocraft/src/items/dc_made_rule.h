/*
 * World of DiabloCraft - the made-by mark's one-worn rule (plan docs/research/kanais-cube.md 6.4:
 * a player may wear only one item made this way; dropped Primals have no limit).
 *
 * A made item is a Primal Ancient with a maker: the 3.3.5 creator field (ITEM_FIELD_CREATOR), which the Cube's Primal
 * upgrade sets and nothing else in Torment does. Any such item counts, whoever made it. The limit is the tunable
 * crafting/made_primal_worn_limit. The check refuses only a new equip, so a lowered limit leaves worn items worn.
 * What leaves with the equip does not count, as for Unique Equipped (dc_items_equip.cpp UniqueEquippedAllows): the item
 * itself, the item in the slot it takes, a two-hander's both hands. Pure, so scripts/tests/items/test_made_rule.py compiles it.
 */
#ifndef DC_MADE_RULE_H
#define DC_MADE_RULE_H

#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

namespace DC::Items
{
    inline bool MadePrimal(bool hasMaker, std::string const& qualityTier)
    {
        return hasMaker && qualityTier == "primal";
    }

    struct WornMade
    {
        std::uint64_t guid = 0;
        bool made = false;
    };

    // May `item` go on: always when it is not made; else when fewer than `limit` other made items stay worn.
    inline bool MadeAllows(bool itemMade, std::vector<WornMade> const& worn, std::vector<std::uint64_t> const& leaving,
                           double limit)
    {
        if (!itemMade)
            return true;
        unsigned staying = 0;
        for (auto const& w : worn)
            if (w.made && std::find(leaving.begin(), leaving.end(), w.guid) == leaving.end())
                ++staying;
        return staying < limit;
    }
} // namespace DC::Items

#endif
