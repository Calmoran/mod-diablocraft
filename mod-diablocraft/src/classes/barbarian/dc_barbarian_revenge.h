// Revenge: the charges the Barbarian earns by being hit, and the heal their spend gives.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Revenge
{
    using Shared::Row;
    using Shared::State;

    // Best Served Cold's critical chance, a part of the player's refresh.
    void OnRefresh(Player* p);
    // The cast: a charge spent, the heal for each enemy hit, the runes' buff and knockback.
    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets, State& s);
    // The player took `damage`: a chance of a charge, up to the skill's cap.
    void OnTaken(Player* p, Unit* attacker, uint32 damage);
} // namespace DC::Combat::Abilities::Revenge
