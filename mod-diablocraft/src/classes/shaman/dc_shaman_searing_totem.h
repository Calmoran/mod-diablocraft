// The Searing Totem and its five runes: the totem's update, the more Fire damage Searing Flames puts on its targets,
// and the less damage the Shaman takes while a Stoneclaw Totem stands.
#pragma once

#include "dc_shaman_totems.h"
#include <optional>
#include "../../combat/dc_damage_buckets.h"

class Unit;

namespace DC::Combat::Shaman::Searing
{
    // One look at a standing Searing Totem cast from `source` (the skill's record or a rune's), `diff` milliseconds
    // after the last.
    void Update(Player* player, Creature* totem, std::uint32_t source, Totems::State& state, std::uint32_t diff);
    // Searing Flames: the hit of `spellId` on `target` takes the stacks' more damage when it is a Fire skill's.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
    // Stoneclaw Totem: the factor on the damage `victim` takes (1 but for a Shaman whose Stoneclaw Totem stands).
    double TakenFactor(Unit* victim);
    void Forget(Player* player);
} // namespace DC::Combat::Shaman::Searing
