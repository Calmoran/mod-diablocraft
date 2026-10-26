#pragma once
// Hex and its five runes: the Fetish Shaman that hexes groups of enemies into chickens (and, by rune, the toad, the
// explosion of the hexed, the heal and the extra damage they take), and the Angry Chicken, which is the Witch Doctor
// turned into the chicken. The rules that need no core type are dc_witch_doctor_hex_math.h; the creature is
// witch_doctor_hex_summons.csv.
#include <cstdint>

class Player;
struct Position;

namespace DC::Combat::WitchDoctor::Hex
{
    // Whether `spellId` is Hex or one of its runes.
    bool Is(std::uint32_t spellId);
    // A cast of Hex or a rune resolved at `center`, the point it was aimed at: the Shaman is raised there and starts
    // its cycles, or (the Angry Chicken) the Witch Doctor turns into the chicken.
    void Cast(Player* player, std::uint32_t spellId, Position const& center);
    // A press of `spellId` while the Angry Chicken lasts: true when it sets the explosion off (the press is spent).
    bool Press(Player* player, std::uint32_t spellId);
    // The kind of the Shaman and the death hook of Unstable Form; at startup.
    void Register();
} // namespace DC::Combat::WitchDoctor::Hex
