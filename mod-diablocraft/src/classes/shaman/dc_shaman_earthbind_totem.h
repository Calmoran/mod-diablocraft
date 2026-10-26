// The Earthbind Totem and its five runes: the totem's update, the more damage Glacial Ground's mark gives, and the
// immunity Tremor Totem gives the Shaman who stands in its radius.
#pragma once

#include "dc_shaman_totems.h"
#include "../../combat/dc_damage_buckets.h"

#include <optional>

class Unit;

namespace DC::Combat::Shaman::Earthbind
{
    // One look at a standing Earthbind Totem cast from `source` (the skill's record or a rune's), `diff` milliseconds
    // after the last.
    void Update(Player* player, Creature* totem, std::uint32_t source, Totems::State& state, std::uint32_t diff);
    // The upkeep of what depends on the Shaman standing in the totem's radius (Tremor Totem's immunity), from the
    // class's 250 ms upkeep.
    void Upkeep(Player* player);
    // The hit of one of the skill's records, for the shell loader (see Searing::BasePct). Nothing for a record of
    // another skill or one with no hit.
    std::optional<double> BasePct(std::uint32_t spellId);
    // Glacial Ground: the hit of `spellId` on a marked `target` takes the rune's percent more.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
    void Forget(Player* player);
} // namespace DC::Combat::Shaman::Earthbind
