#pragma once
// Blood Rush and its five runes: the Necromancer sheds its flesh and reappears up to 50 yards away (the engine's charge to the point
// aimed at); here: the Life the cast costs, Metabolism's second charge, Transfusion's heal for the enemies passed through, Potency's
// armor and Molting's corpse where the Necromancer stood. The rules that need no core type are dc_necromancer_blood_rush_math.h.
#include <cstdint>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer::BloodRush
{
    // The cast began: the Life it costs.
    void Casting(Player* player, std::uint32_t spellId);
    // The cast resolved: Metabolism's charge, Potency's armor.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The rush was aimed at `destination`, the Necromancer still where it began: Transfusion's heal, Molting's corpse.
    void Ground(Player* player, std::uint32_t spellId, Position const& destination);
} // namespace DC::Combat::Necromancer::BloodRush
