#pragma once
// Big Bad Voodoo and its five runes (Slam Dance, Jungle Drums, Ghost Trance, Rain Dance, Boogie Man): a ritual laid on
// the ground for a time that gives the Witch Doctor and the party in it attack and movement speed, and the runes more.
// The rules that need no core type are dc_witch_doctor_big_bad_voodoo_math.h.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>

class Player;
class Unit;
struct Position;

namespace DC::Combat::WitchDoctor::BigBadVoodoo
{
    // Whether `spellId` is Big Bad Voodoo or one of its runes.
    bool Is(std::uint32_t spellId);
    // The cast on the ground: the ritual begins at `center` (the one before it ends).
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // Slam Dance: the factor on every hit of an ally the ritual holds.
    void Multipliers(Player* player, DC::Combat::Factors& out);
    // Ghost Trance: a blow of `damage` on `victim` after the ritual's reduction.
    double Reduce(Unit* victim, double damage);
    // The death of an enemy in the ritual (Boogie Man) and the Witch Doctor logging out; at startup.
    void RegisterScripts();
} // namespace DC::Combat::WitchDoctor::BigBadVoodoo
