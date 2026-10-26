#pragma once
// Leech and its five runes: the curse on the enemies around the place aimed at, which heals the Necromancer when they are struck.
// Osmosis gives life regeneration for the enemies cursed, Transmittable spreads the curse when a cursed enemy dies, Sanguine End
// heals with the Life per Kill, Cursed Ground heals every second for the enemies in the patch, Blood Flask shortens the potion
// cooldown. The rules that need no core type are dc_necromancer_leech_math.h.
#include <cstdint>
#include <optional>

class Player;
class Unit;
struct Position;

namespace DC::Combat::Necromancer::Leech
{
    // A curse deals nothing of its own. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast was aimed at `center`.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // A hit of the Necromancer's landed on `target`: the heal of the curse on it.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The kill hook of the runes that answer the death of a cursed enemy; at startup.
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::Leech
