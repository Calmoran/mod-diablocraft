#pragma once
// Decrepify and its five runes: the curse put on the enemies around the place aimed at, which slows them and makes them deal less
// damage. Enfeeblement starts the slow stronger; Opportunist and Borrowed Time give the Necromancer speed and cooldown reduction
// for the enemies cursed; Wither weakens more and slows nothing; Dizzying Curse stuns the cursed when hit. The rules that need no
// core type are dc_necromancer_decrepify_math.h.
#include <cstdint>
#include <optional>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer::Decrepify
{
    // A curse deals nothing of its own. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast was aimed at `center`.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // A hit of the Necromancer's landed on `target`: Dizzying Curse's stun.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The curse's way of lifting; at startup.
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::Decrepify
