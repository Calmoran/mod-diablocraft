// Ancient Spear: the pull, the flip and the knockback of its runes.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::AncientSpear
{
    using Shared::Row;
    using Shared::State;

    // A hit of the skill landed on `target`: Harpoon, Rage Flip and Ranseur move it.
    void OnHit(Player* p, Unit* target, Row const* r);
    // Whether the rune spends the whole pool at the cast.
    bool SpendsEveryPoint(std::string const& skill, std::string const& rune);
    // A cast begins with `fury` in the pool: Boulder Toss turns it into damage.
    void OnBegin(std::string const& skill, std::string const& rune, uint32 id, double fury, double& damagePct);
    // Whether the rune deals its damage once, to everything around the first enemy the spear reaches.
    bool BurstsAtFirstImpact(std::string const& skill, std::string const& rune);
} // namespace DC::Combat::Abilities::AncientSpear
