// Meteor: the fall that lands after the sheet's delay, Meteor Shower's seven meteors and Star Pact's spent Arcane Power.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::Meteor
{
    // The Wizard has cast Meteor at `center`: the impact and the molten ground are scheduled; `dynamo` is Arcane Dynamo's empowering of
    // this cast. Always true: the module has taken the cast over.
    bool Delayed(Player* player, uint32 id, Position const& center, bool dynamo);
} // namespace DC::Combat::Wizard::Meteor
