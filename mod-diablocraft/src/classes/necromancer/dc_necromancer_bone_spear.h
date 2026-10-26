#pragma once
// Bone Spear and its five runes: Crystallization's slow and speed, Shatter's detonation, Blighted Marrow's bonus for
// each enemy passed through, Blood Spear's cost in Life and Teeth's shorter reach. The spear itself is the engine's
// projectile (a spell record and the sheet's numbers) that pierces the line; this file holds what the record cannot
// say. The rules that need no core type are dc_necromancer_bone_spear_math.h.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::Necromancer::BoneSpear
{
    // The cast began: Blood Spear takes its Life.
    void Casting(Player* player, std::uint32_t spellId);
    // The spear reached `target`, the `index`th enemy it met (0 for the first): true when this file dealt with the
    // impact and the engine's own hit is not to follow (Shatter's detonation, Teeth's far enemies).
    bool Impact(Player* player, Unit* target, std::uint32_t spellId, unsigned index);
    // The spear's hit landed on `target`: Crystallization's effects.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The hit being computed: Blighted Marrow's bonus for the enemies passed through.
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
} // namespace DC::Combat::Necromancer::BoneSpear
