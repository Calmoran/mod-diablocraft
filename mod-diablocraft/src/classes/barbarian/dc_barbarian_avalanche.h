// Avalanche: the cooldown Fury spent takes off, the Tectonic Rift charges and the runes' effects.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Avalanche
{
    using Shared::Row;
    using Shared::State;

    // The cast: a Tectonic Rift charge spent, Glacier's freeze, Volcano's zone, Snow-Capped Mountain's slow and pull.
    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets, Position const* center, State& s);
    // Fury was spent: the cooldown comes down by what the skill states per Fury.
    void OnSpent(Player* p, State& s, double fury);
    // The player's upkeep: Tectonic Rift's charges recharge.
    void OnUpdate(Player* p, State& s, uint32 diff);
    // A hit of the shell `skill`/`rune` is being resolved: Volcano deals nothing at the cast, its zone does.
    std::optional<bool> OnResolve(std::string const& skill, std::string const& rune);
} // namespace DC::Combat::Abilities::Avalanche
