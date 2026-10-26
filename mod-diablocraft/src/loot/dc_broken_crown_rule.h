/*
 * World of DiabloCraft - Broken Crown's gem drop (D3: "Whenever a gem drops, a gem of the type
 * socketed into your helmet also drops. This effect does not apply to Legendary Gems.").
 *
 * The type is the gem's colour (dc_gem_item.colour); the bonus gem is that colour at the grade of the gem that
 * dropped (the same dc_gem_item.tier). A helm with no gem, or with a legendary gem (no dc_gem_item row), gives
 * nothing, and so does a dropped gem that is not in the table. Pure, so scripts/tests/legendaries/test_broken_crown.py compiles it.
 */
#ifndef DC_BROKEN_CROWN_RULE_H
#define DC_BROKEN_CROWN_RULE_H

#include <cstdint>
#include <string>
#include <vector>

namespace DC::Loot::BrokenCrown
{
    // The Crown's dc_base_item.d3_id (the P2 item; the older Unique_Helm_001_x1 has another power).
    inline constexpr char const* BaseId = "P2_Unique_Helm_001";

    struct Gem
    {
        std::uint32_t entry = 0;
        std::string colour, tier;
    };

    // The entry of the extra gem, 0 for none. helmGem is the entry socketed in the worn Crown (0 for none).
    inline std::uint32_t BonusGem(std::uint32_t helmGem, std::uint32_t dropped, std::vector<Gem> const& gems)
    {
        std::string colour, tier;
        for (Gem const& gem : gems)
        {
            if (gem.entry == helmGem)
                colour = gem.colour;
            if (gem.entry == dropped)
                tier = gem.tier;
        }
        for (Gem const& gem : gems)
            if (gem.colour == colour && gem.tier == tier)
                return gem.entry;
        return 0;
    }
} // namespace DC::Loot::BrokenCrown

#endif // DC_BROKEN_CROWN_RULE_H
