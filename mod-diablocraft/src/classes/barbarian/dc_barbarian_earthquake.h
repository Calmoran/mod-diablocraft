// Earthquake: the cast of the ground zone; its ticks are the zones'.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Earthquake
{
    using Shared::Row;
    using Shared::State;

    // The cast: Cave-In pulls the enemies in, then the zone starts at `center`.
    void OnCast(Player* p, Row const* r, Row const* b, Position const* center);
    // Whether the rune keeps the sheet's damage: the tremors deal their own.
    bool KeepsSheetDamage(std::string const& skill, std::string const& rune);
    // Whether `skill` is Earthquake, whose ticks carry average crit.
    bool DamageOverTime(std::string const& skill);
    // Whether `skill` is Earthquake, whose cast deals nothing: the zone distributes the damage.
    bool LaunchesNoHit(std::string const& skill);
} // namespace DC::Combat::Abilities::Earthquake
