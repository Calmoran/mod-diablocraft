// Slow Time: the bubble dropped at the target and the bubble that follows the Wizard when an item gives it that.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::SlowTime
{
    // The cast has resolved: the bubble at `center`, or on the Wizard when the item makes it follow, and Time Shell's cooldown.
    void Cast(Player* player, uint32 id, Position const& center);
    // Whether `unit` wears a bubble that follows its caster.
    bool Following(Unit const* unit);
    void RemoveFollow(Player* player);
    // Whether `unit` stands in the follow bubble of a Wizard to whom an item gives Slow Time's `rune`.
    bool GivenFollow(Unit const* unit, char const* rune);
    // Registers the bubble's aura script.
    void RegisterScripts();
} // namespace DC::Combat::Wizard::SlowTime
