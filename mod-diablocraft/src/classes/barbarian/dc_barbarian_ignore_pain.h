// Ignore Pain: the damage reduction buff, its runes and the allies Mob Rule reaches.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::IgnorePain
{
    using Shared::Row;
    using Shared::State;

    // The buff's damage reduction and movement speed, a part of the player's refresh.
    void OnRefresh(Player* p);
    // The cast: the buff on the caster, the heal of Contempt for Weakness, the allies Mob Rule reaches.
    void OnCast(Player* p, uint32 id, Row const* r, Row const* b);
    // Fury was spent: Ignorance is Bliss heals for it.
    void OnSpent(Player* p, double fury);
} // namespace DC::Combat::Abilities::IgnorePain
