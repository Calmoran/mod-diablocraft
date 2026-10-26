// Wrath of the Berserker: the berserk buff and its runes.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::Wrath
{
    using Shared::Row;
    using Shared::State;

    // The buff's critical chance, speeds and its runes' contributions, a part of the player's refresh.
    void OnRefresh(Player* p);
    // Insanity's multiplier of its own.
    void OnMultipliers(Player* p, DC::Combat::Factors& out);
    // Adds the dodge chance the buff gives.
    void OnDodge(Player const* p, double& chance);
    // The cast: the buff on the caster and Arreat's Wail's blast.
    void OnCast(Player* p, Row const* r, Row const* b);
    // Fury was spent: Thrive on Chaos heals for it.
    void OnSpent(Player* p, double fury);
    // A critical hit landed: Slaughter's blast, if the hit's proc coefficient rolls. Called with the module lock held.
    void OnCritical(Player* p, Unit* target, uint32 spellId);
} // namespace DC::Combat::Abilities::Wrath
