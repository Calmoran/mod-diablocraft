#pragma once
// Corpse Lance and its five runes: the lance flies from a corpse at the targeted enemy (the engine's projectile and
// hit); this file takes the corpse, and holds Ricochet, Brittle Touch, Blood Lance, Visceral Impact and Shredding
// Splinters. The rules that need no core type are dc_necromancer_corpse_lance_math.h.
#include <cstdint>
#include <optional>

#include "SharedDefines.h"

class Player;
class Unit;

namespace DC::Combat::Necromancer::CorpseLance
{
    // Blood Lance keeps the skill's number for the main lance. nullopt for every other spell.
    std::optional<double> BasePct(std::uint32_t spellId);
    // Whether the cast may begin: a corpse lies near the Necromancer or near the target. SPELL_CAST_OK for every other
    // spell.
    SpellCastResult CanCast(Player* player, std::uint32_t spellId, Unit* target);
    // The cast began: Blood Lance takes its Life.
    void Casting(Player* player, std::uint32_t spellId);
    // The lance reached `target`, the `index`th it met: the first takes the corpse it flew from; true when there was
    // none and the engine's hit is not to follow.
    bool Impact(Player* player, Unit* target, std::uint32_t spellId, unsigned index);
    // The lance's hit landed on `target`: the rune's part.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // Brittle Touch's chance to be crit on `target`, in percent.
    double CritBonus(Player* player, Unit* target);
} // namespace DC::Combat::Necromancer::CorpseLance
