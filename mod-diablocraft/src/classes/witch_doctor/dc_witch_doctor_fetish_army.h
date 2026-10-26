#pragma once
// Fetish Army and its five runes (Fetish Ambush, Legion of Daggers, Tiki Torchers, Devoted Following, Head Hunters):
// the cast raises the Fetishes through the pets' piece (dc_witch_doctor_pets.h); the runes add more daggers, casters or
// hunters, or make each dagger land on an enemy. The rules that need no core type are
// dc_witch_doctor_fetish_army_math.h.
#include <cstdint>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::FetishArmy
{
    // Whether `spellId` is Fetish Army or one of its runes.
    bool Is(std::uint32_t spellId);
    // The cast: the Fetishes the rune says are raised.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The kinds of the casters and the hunters; at startup.
    void RegisterScripts();
} // namespace DC::Combat::WitchDoctor::FetishArmy
