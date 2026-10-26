// The buffs the Wizard wears: the sheet contributions the skills and passives give (armor, resistances, speed, crit) and the buff icons
// that show them.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::Buffs
{
    // Puts the Wizard's contributions on the sheet when they changed (or `force`), and updates the buff icons.
    void Refresh(Player* player, bool force = false);
} // namespace DC::Combat::Wizard::Buffs
