#pragma once
// Army of the Dead and its five runes: the army that pummels the place aimed at after a short delay. The skill's own blasts
// and Death Valley's pull land on the place; Blighted Grasp's hands stay for a time; Frozen Army sweeps a line; Unconventional
// Warfare strikes random enemies; Dead Storm surrounds the Necromancer and takes Life. The rules that need no core type are
// dc_necromancer_army_of_the_dead_math.h.
#include <cstdint>
#include <optional>

class Player;
struct Position;

namespace DC::Combat::Necromancer::ArmyOfTheDead
{
    // The army strikes for itself on a delay: the engine's own hit is none. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast began: Dead Storm takes its Life.
    void Casting(Player* player, std::uint32_t spellId);
    // The cast was aimed at `center`.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
} // namespace DC::Combat::Necromancer::ArmyOfTheDead
