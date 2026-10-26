// Whirlwind: the channel the module pays tick by tick, its dust devils and its runes.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Whirlwind
{
    using Shared::Row;
    using Shared::State;

    // The player's upkeep: the channel's ticks on the cadence of the swinging hand, the devils it leaves and their travel.
    void OnUpdate(Player* p, State& s, uint32 diff);
    // Whether `skill` is Whirlwind.
    bool PaysByTick(std::string const& skill);
    // Whether the rune keeps the sheet's damage: the devils' own damage is dealt by the devils.
    bool KeepsSheetDamage(std::string const& skill, std::string const& rune);
    // A press of `id` while the channel runs stops it.
    bool OnToggle(Player* p, uint32 id);
} // namespace DC::Combat::Abilities::Whirlwind
