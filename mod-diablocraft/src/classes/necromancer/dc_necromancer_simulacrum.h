#pragma once
// Simulacrum and its five runes: the copies of the Necromancer (the minions' kind in dc_necromancer_pets.cpp) that repeat its
// Secondary skills, and what the runes add while one stands: Reservoir's Essence, Cursed Form's three curses, Blood Debt's cheaper
// Life, Blood and Bone's second copy, Self Sacrifice's second chance. The rules that need no core type are
// dc_necromancer_simulacrum_math.h.
#include <cstdint>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer::Simulacrum
{
    // The cast began: the Life it costs.
    void Casting(Player* player, std::uint32_t spellId);
    // The cast resolved: the copies rise, Reservoir adds its Essence; or, a Secondary skill cast, the copies repeat it.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // A curse skill was aimed at `center`, the Necromancer still where it began: Cursed Form adds the other two curses there.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // What a Life cost is multiplied by now (Blood Debt).
    double LifeCostShare(Player* player);
    // Self Sacrifice: a blow that would be fatal does nothing, the copies end and the Life is full. The damage that goes on.
    double Reduce(Unit* victim, double damage);
    // A copy is repeating a skill now: the repeat costs nothing and is not repeated.
    bool Repeating();
    // At startup.
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::Simulacrum
