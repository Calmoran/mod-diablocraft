// Sprint's Gangway and Ignore Pain's Bravado: the enemies pushed aside by a running Barbarian.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Collisions
{
    using Shared::Row;
    using Shared::State;

    // The player's upkeep: while a running Barbarian wears either rune, the enemies it touches are knocked back once each.
    void OnUpdate(Player* p, State& s);
} // namespace DC::Combat::Abilities::Collisions
