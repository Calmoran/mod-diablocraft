// Sprint: the movement buff, its runes and the tornado Run Like the Wind leaves behind.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Sprint
{
    using Shared::Row;
    using Shared::State;

    // The buff's movement speed, a part of the player's refresh.
    void OnRefresh(Player* p);
    // The movement speed Forced March gives a player it was cast on.
    void OnRefreshAllied(Player* p);
    // Adds the dodge chance the buff gives.
    void OnDodge(Player const* p, double& chance);
    // The cast: the buff on the caster, and on the allies Forced March reaches. `r` is the cast rune's row, `b` the skill's base row.
    void OnCast(Player* p, Row const* r, Row const* b);
    // The player's upkeep: Run Like the Wind's tornado while the Barbarian runs.
    void OnUpdate(Player* p, State& s, uint32 diff);
} // namespace DC::Combat::Abilities::Sprint
