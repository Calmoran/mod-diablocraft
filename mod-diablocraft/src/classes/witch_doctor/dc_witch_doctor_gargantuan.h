#pragma once
// The Gargantuan and its five runes (Restless Giant, Humongoid, Big Stinker, Wrathful Protector, Bruiser): the cast
// raises it through the pets' piece (dc_witch_doctor_pets.h) at the ground it was aimed at, and the rune on the bar
// shapes the one it raises. The rules that need no core type are dc_witch_doctor_gargantuan_math.h.
#include "../../combat/dc_minions.h"

#include <cstdint>

class Player;
struct Position;

namespace DC::Combat::WitchDoctor::GargantuanRunes
{
    // Whether `spellId` is Gargantuan or one of its runes.
    bool Is(std::uint32_t spellId);
    // The cast on the ground: the Gargantuan is raised at `center`.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // The record and the weapon damage of the Gargantuan's blow with the rune on the bar: the rune's own for Humongoid
    // and Wrathful Protector, the skill's otherwise.
    struct Blow
    {
        std::uint32_t record = 0;
        double pct = 0;
    };
    Blow BlowOf(Player* owner);
    // The rune on the bar fills `kind`, the Gargantuan about to be raised; `feastPct` is Midnight Feast's raise of its
    // damage.
    void Shape(Player* owner, Minions::Kind& kind, double feastPct);
} // namespace DC::Combat::WitchDoctor::GargantuanRunes
