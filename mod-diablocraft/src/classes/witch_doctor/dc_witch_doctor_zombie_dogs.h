#pragma once
// Summon Zombie Dogs and its five runes (Burning Dogs, Life Link, Rabid Dogs, Chilled to the Bone, Leeching Beasts):
// the cast raises the dogs through the pets' piece (dc_witch_doctor_pets.h) and the rune on the bar shapes each dog it
// raises. The rules that need no core type are dc_witch_doctor_zombie_dogs_math.h.
#include "../../combat/dc_minions.h"

#include <cstdint>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::ZombieDogs
{
    // Whether `spellId` is Summon Zombie Dogs or one of its runes.
    bool Is(std::uint32_t spellId);
    // The cast: dogs raised with another rune than the bar's are sent away, then the dogs the Witch Doctor is short of
    // are raised.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The rune on the bar fills `kind`, a Zombie Dog about to be raised: Burning Dogs' aura, Rabid Dogs' bite, Chilled
    // to the Bone's chill, Leeching Beasts' heal. Called by the pets' piece for each dog.
    void Shape(Player* owner, Minions::Kind& kind);
    // Life Link: the dogs take their share of a blow of `damage` on `victim` and the rest is answered.
    double Reduce(Unit* victim, double damage);
} // namespace DC::Combat::WitchDoctor::ZombieDogs
