// Ground Stomp: the stun, and the runes that pull or give Fury.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::GroundStomp
{
    using Shared::Row;
    using Shared::State;

    // The cast: Foot of the Mountain's Fury, Wrenching Smash's pull, the stun on each enemy.
    void OnCast(Player* p, Row const* r, Row const* b, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Abilities::GroundStomp
