// Threatening Shout: the shout that weakens enemies, and its runes.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::ThreateningShout
{
    using Shared::Row;
    using Shared::State;

    // The damage bonus an enemy under Falter takes, 0 for any other unit.
    double OnTargetBonus(Unit* u);
    // The factor on the damage an enemy under the shout deals, 1 for any other unit.
    double OnIncomingFactor(Unit* attacker);
    // The cast: the shout on each enemy it reaches and the control its runes add.
    void OnCast(Player* p, uint32 id, Row const* r, Row const* b, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Abilities::ThreateningShout
