#pragma once
// Command Golem and its five runes: the active, which commands the Golem to the place aimed at (the Golem itself and the
// passive that raises it are dc_necromancer_pets.cpp, on the shared minions). The skill and Flesh Golem collapse it into a
// pile of corpses; Bone Golem carries enemies to the place as a tornado and stuns them; Blood Golem is sacrificed and rebuilt
// there; Decay Golem eats the corpses lying there; Ice Golem freezes the enemies around the place. The rules that need no
// core type are dc_necromancer_command_golem_math.h.
#include <cstdint>
#include <optional>

#include "SharedDefines.h"

class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer::CommandGolem
{
    // The active has no hit of its own: the Golem strikes. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // Whether the cast may begin: the Golem stands. SPELL_CAST_OK for every other spell.
    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Position const* aim);
    // The cast was aimed at `center`.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // Ice Golem's chance to be crit on `target`, in percent.
    double CritBonus(Player* player, Unit* target);
} // namespace DC::Combat::Necromancer::CommandGolem
