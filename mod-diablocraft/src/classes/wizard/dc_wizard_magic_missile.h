// Magic Missile: Conflagrate's burn, its stacks and its tick.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::MagicMissile
{
    // Fire damage from another spell refreshes every stack of the burn on `target` to its full duration.
    void RefreshBurn(Player* player, Unit* target);
    // One tick of the burn on `target`, with `stacks` stacks, `seconds` being the period.
    void BurnTick(Player* player, uint32 id, double seconds, Unit* target, uint8 stacks);
} // namespace DC::Combat::Wizard::MagicMissile
