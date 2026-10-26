#pragma once
// Devour and its five runes: the cast consumes the Necromancer's corpses within reach for Essence; Cannibalize heals,
// Ruthless consumes the minions too, Voracious cuts costs, Satiated raises maximum Life, Devouring Aura is an aura that
// consumes the corpses near it as they come. The corpses are the shared combat/dc_corpses. The rules that need no core
// type are dc_necromancer_devour_math.h.
#include <cstdint>
#include <vector>

#include "SharedDefines.h"

class Player;
class Unit;

namespace DC::Combat::Necromancer::Devour
{
    // Whether the cast may begin: a corpse (or for Ruthless a minion) to consume. SPELL_CAST_OK for every other spell,
    // and for the aura rune, which a cast turns off as well as on.
    SpellCastResult CanCast(Player* player, std::uint32_t spellId);
    // The cast resolved: the corpses go, or the aura turns on or off.
    void Cast(Player* player, std::uint32_t spellId);
    // The aura's sweeps (Combat::RegisterScripts).
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::Devour
