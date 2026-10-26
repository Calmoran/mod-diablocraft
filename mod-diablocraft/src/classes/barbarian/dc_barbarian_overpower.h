// Overpower: the axe strike, its runes and the spell script of Storm of Steel's axes.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Overpower
{
    using Shared::Row;
    using Shared::State;

    // A melee hit of `damage` reached the player: Crushing Advance sends part of it back at the attacker.
    void OnReflect(Player* p, Unit* attacker, uint32& damage);
    // Killing Spree's critical chance, a part of the player's refresh.
    void OnRefresh(Player* p);
    // The cast: the buff of Killing Spree and Crushing Advance, Momentum's Fury, Storm of Steel's axes.
    void OnCast(Player* p, uint32 id, Row const* r, std::vector<Unit*> const& targets);
    // A critical hit landed: the hit's proc coefficient may cut Overpower's cooldown.
    void OnCritical(Player* p, uint32 spellId);
    // The spell script of Storm of Steel's axes.
    void RegisterScripts();
} // namespace DC::Combat::Abilities::Overpower
