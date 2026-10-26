#pragma once
// Skeletal Mage and its five runes: the cast that raises the mage (the mage itself is dc_necromancer_pets.cpp, on the
// shared minions) and the Life or Essence a rune takes for it. The rules that need no core type are
// dc_necromancer_skeletal_mage_math.h.
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Necromancer::SkeletalMage
{
    // The cast has no hit of its own: the mage strikes. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast began: Life Support takes its Life, Singularity its Essence.
    void Casting(Player* player, std::uint32_t spellId);
    // The cast resolved: the mage rises beside the Necromancer.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Necromancer::SkeletalMage
