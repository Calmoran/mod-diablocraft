#pragma once
// Bone Spirit and its five runes: the spirit seeks the enemy aimed at and hits it (the engine's single hit); here: the charges the skill
// stores and the corpses that recharge them, Possession's charm and Life cost, Panic Attack's fear, Unfinished Business' explosion, Astral
// Projection's bonus for the enemies passed. The rules that need no core type are dc_necromancer_bone_spirit_math.h.
#include <cstdint>
#include <optional>
#include <vector>

#include "../../combat/dc_combat.h"

class Player;
class Unit;

namespace DC::Combat::Necromancer::BoneSpirit
{
    // Unfinished Business keeps the skill's number for the spirit's own hit. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast began: Possession takes its Life; Astral Projection counts the enemies on the way to the aimed target.
    void Casting(Player* player, std::uint32_t spellId);
    // The spirit's hit is worth more for the enemies it passed (Astral Projection).
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
    // The cast resolved on the enemy hit: the charge it spends, and what its rune adds.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The corpses a skill consumes shorten the recharge; at startup.
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::BoneSpirit
