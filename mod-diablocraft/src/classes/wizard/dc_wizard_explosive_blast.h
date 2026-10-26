// Explosive Blast: the fuse and Chain Reaction's explosions one attack apart.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::ExplosiveBlast
{
    // The Wizard has cast Explosive Blast: the explosions are scheduled; `dynamo` is Arcane Dynamo's empowering of this cast. Always true.
    bool Delayed(Player* player, uint32 id, bool dynamo);
} // namespace DC::Combat::Wizard::ExplosiveBlast
