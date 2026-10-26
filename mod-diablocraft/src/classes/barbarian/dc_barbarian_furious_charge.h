// Furious Charge: the charges, their recharge and the knockback of the charge itself.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::FuriousCharge
{
    using Shared::Row;
    using Shared::State;

    // The cast: a charge spent, the recharge started, the runes' Fury, freeze, knockback and recharge reduction.
    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets, State& s);
    // The player's upkeep: the charges recharge, and the client is told when the count changes.
    void OnUpdate(Player* p, State& s, uint32 diff);
} // namespace DC::Combat::Abilities::FuriousCharge
