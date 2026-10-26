// The ground zones (Earthquake, Avalanche's Volcano, Rumble, the tornado, the Devil's Anvil): their damage, control and tremors each update.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Zones
{
    using Shared::Row;
    using Shared::State;

    // The player's upkeep: each zone deals its share of damage for the time that passed, and ends when its time is up.
    void OnUpdate(Player* p, State& s, uint32 diff);
} // namespace DC::Combat::Abilities::Zones
