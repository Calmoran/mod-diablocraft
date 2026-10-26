// Arcane Orb: Scorch's wall of Fire, left along the orb's flight.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::ArcaneOrb
{
    // The cast of Scorch has resolved at `center`: the wall starts where the orb set off and runs the way it flew.
    void Cast(Player* player, Position const& center);
    // One tick of the wall: every enemy on the line the orb has flown so far, `seconds` being the period.
    void WallTick(Player* player, uint32 id, double seconds);
} // namespace DC::Combat::Wizard::ArcaneOrb
