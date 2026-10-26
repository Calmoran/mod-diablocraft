// Leap: the jump, its landing effects and the armor Iron Impact leaves.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Leap
{
    using Shared::Row;
    using Shared::State;

    // Iron Impact's armor, a part of the player's refresh.
    void OnRefresh(Player* p);
    // The cast: Iron Impact's buff, Call of Arreat's pull and Toppling Impact's knockback.
    void OnCast(Player* p, Row const* r, std::vector<Unit*> const& targets);
    // A hit of the skill landed on `target`: the slow.
    void OnHit(Player* p, Unit* target, Row const* r, Row const* b);
    // The jump began (Launch): the enemies around the Barbarian are hit and slowed.
    void OnLaunch(Player* p, uint32 id);
} // namespace DC::Combat::Abilities::Leap
