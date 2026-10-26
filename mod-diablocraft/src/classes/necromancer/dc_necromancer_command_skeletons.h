#pragma once
// Command Skeletons and its five runes: the active, which orders the skeletons at a target (the skeletons and the passive
// that raises them are dc_necromancer_pets.cpp, on the shared minions). Freezing Grasp holds the target, Kill Command
// sends the skeletons off in an explosion instead. The rules that need no core type are
// dc_necromancer_command_skeletons_math.h.
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Necromancer::CommandSkeletons
{
    // The active has no hit of its own: the skeletons strike. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets` (the enemy aimed at): the order, the freeze or the explosion.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Necromancer::CommandSkeletons
