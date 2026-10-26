#ifndef DC_SALVAGE_RULE_H
#define DC_SALVAGE_RULE_H

// G8 (docs/security.md): one rule for single and bulk salvage. An equipped item
// is never salvaged, and neither is one in a trade. Pure, so the test compiles
// this very header.
#include <string>

namespace DC::Crafting
{
constexpr bool SalvageEligible(bool equipped, bool inTrade)
{
    return !equipped && !inTrade;
}

// Kanai's Cube: which dc_salvage_rule quality row an item pays. An Ancient or Primal item pays its
// own materials (3 Forgotten Souls, 55 Primordial Ashes); a crafted item, and anything else, pays by rarity alone.
inline std::string SalvageQuality(bool crafted, std::string const& qualityTier)
{
    return !crafted && (qualityTier == "ancient" || qualityTier == "primal") ? qualityTier : "normal";
}
}

#endif // DC_SALVAGE_RULE_H
