// Black Hole: the pull on the enemies it reaches, Blazar's explosion and the stacks Spellsteal and Absolute Zero leave on the Wizard.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::BlackHole
{
    // The cast has resolved over `targets` at `center`.
    void Cast(Player* player, uint32 id, std::vector<Unit*> const& targets, Position const& center);
} // namespace DC::Combat::Wizard::BlackHole
