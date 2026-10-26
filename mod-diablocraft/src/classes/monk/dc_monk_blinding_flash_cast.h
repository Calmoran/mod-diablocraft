#pragma once
// Blinding Flash: what dc_monk.cpp dispatches to. The pure rules are in
// dc_monk_blinding_flash.h.
#include "dc_monk.h"

namespace DC::Combat::Monk::BlindingFlash
{
    // Whether `spellId` is Blinding Flash or one of its runes.
    bool Is(std::uint32_t spellId);
    // The flash resolved: every enemy within the radius is blinded, and the rune does its part.
    void Cast(Player* player, std::uint32_t spellId);
    // The percent of its melee swings a blinded elite attacker misses now (the hit table, Combat's hook).
    double MissChance(Unit const* attacker);
} // namespace DC::Combat::Monk::BlindingFlash
