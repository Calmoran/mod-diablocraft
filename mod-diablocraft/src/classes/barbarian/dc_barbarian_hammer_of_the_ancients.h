// Hammer of the Ancients: the zone of the Devil's Anvil, the stun of Thunderstrike and the heal of Birthright.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Hammer
{
    using Shared::Row;
    using Shared::State;

    // A hit of the skill landed on `target`: the Devil's Anvil's zone, Thunderstrike's stun.
    void OnHit(Player* p, Unit* target, Row const* r);
    // A critical hit landed: Birthright heals when it was this skill's.
    void OnCritical(Player* p, uint32 spellId);
    // The critical chance, in percent, the skill gets from the `fury` in the pool.
    double OnCritBonus(std::string const& skill, double fury);
} // namespace DC::Combat::Abilities::Hammer
