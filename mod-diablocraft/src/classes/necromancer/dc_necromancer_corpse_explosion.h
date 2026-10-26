#pragma once
// Corpse Explosion and its five runes: the skill explodes up to five of the Necromancer's corpses near the point aimed
// at, each striking the enemies around it. The corpses are the shared combat/dc_corpses; the engine's own hit on the
// ground area is none. The rules that need no core type are dc_necromancer_corpse_explosion_math.h.
#include <cstdint>
#include <optional>

#include "SharedDefines.h"

class Player;
struct Position;

namespace DC::Combat::Necromancer::CorpseExplosion
{
    // The engine's hit is none: the corpses strike. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // Whether the cast may begin: there is a corpse to explode within reach of the point aimed at (or of the
    // Necromancer, for Close Quarters). SPELL_CAST_OK for every other spell.
    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Position const* aim);
    // The cast was aimed at `center`: the corpses explode.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::Necromancer::CorpseExplosion
