#pragma once
// Revive and its five runes: the cast revives up to ten of the Necromancer's corpses near the point aimed at as minions
// (their kind is dc_necromancer_pets.cpp, on the shared combat/dc_minions); this file takes the corpses, and holds
// Oblation's cost in Life for each corpse, Personal Army's reduction of the damage taken and Horrific Return's fear. The rules that
// need no core type are dc_necromancer_revive_math.h.
#include <cstdint>

#include "SharedDefines.h"

class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer::CorpseRevive
{
    // Whether the cast may begin: a corpse lies within reach of the point aimed at. SPELL_CAST_OK for every other
    // spell.
    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Position const* aim);
    // The cast was aimed at `center`: the corpses rise.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // Personal Army: the damage `victim` takes less for each revived minion standing.
    double Reduce(Unit* victim, double damage);
} // namespace DC::Combat::Necromancer::CorpseRevive
