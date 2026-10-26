/*
 * World of DiabloCraft - the `resource` preset (Stone of Jordan, Lidless Wall).
 *
 * Pure functions only, so scripts/tests/items/test_resource_affix.py compiles this exact header. Which classes and
 * resources exist is data (class_resources.csv through dc_resource_data.h); no class or resource is named here.
 *
 * D3's `resource` preset is "Maximum <the wearer's resource>": the item lists one Maximum <resource> range per
 * class (reference/d3planner/item_finger.js:714-720, item_offhand.js:94-100; data_stats.js:129-137 names each stat).
 * The item carries one item_preset_ranges.csv row per class, under the stat's own code (maxfury, maxap, maxspirit
 * ...), each named as data_stats.js names it ("Maximum Fury"). The roller takes the row named after the roll class's
 * resource, as `mainstat` takes the roll class's main stat: its primary resource first, then its second (a Demon
 * Hunter's Stone of Jordan rolls Maximum Discipline, item_finger.js:714, since D3 lists no Maximum Hatred there).
 */

#ifndef DC_RESOURCE_AFFIX_RULE_H
#define DC_RESOURCE_AFFIX_RULE_H

#include <string>
#include <vector>

namespace DC::ResourceAffix
{
    inline constexpr char const* Preset = "resource";

    // The affix id the preset rolls as: the first of the class's resource names (primary first) that one of the
    // item's own rows carries as "Maximum <name>". Empty when none does (a class with no row for this item):
    // then nothing is rolled rather than another class's resource.
    template<class Row>
    std::string For(std::vector<std::string> const& resourceNames, std::vector<Row> const& itemRows)
    {
        for (std::string const& name : resourceNames)
            for (Row const& row : itemRows)
                if (row.name == "Maximum " + name)
                    return row.affixId;
        return {};
    }
} // namespace DC::ResourceAffix

#endif
