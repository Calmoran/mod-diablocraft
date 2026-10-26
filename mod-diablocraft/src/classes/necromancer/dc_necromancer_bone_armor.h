#pragma once
// Bone Armor and its five runes: the cast rips bones from the enemies around the Necromancer (the engine's area hit) and the armor it
// makes cuts the damage taken for each enemy hit. Limited Immunity absorbs everything for a few seconds instead, Dislocation stuns the
// enemies hit, Thy Flesh Sustained costs Life and raises Life regeneration for each, Harvest of Anguish raises movement speed. The rules
// that need no core type are dc_necromancer_bone_armor_math.h.
#include <cstdint>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Necromancer::BoneArmor
{
    // The cast began: Thy Flesh Sustained takes its Life.
    void Casting(Player* player, std::uint32_t spellId);
    // The cast resolved on the enemies it hit: the armor, and what its rune gives.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The damage `victim` takes with the armor on.
    double Reduce(Unit* victim, double damage);
} // namespace DC::Combat::Necromancer::BoneArmor
