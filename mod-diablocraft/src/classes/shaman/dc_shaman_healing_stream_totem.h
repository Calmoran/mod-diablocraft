// The Healing Stream Totem and its five runes: the totem's update, the immunity Cleansing Stream gives for a short time, the death Ancestral
// Protection prevents.
#pragma once

#include "dc_shaman_totems.h"

#include <optional>

class Unit;

namespace DC::Combat::Shaman::HealingStream
{
    // One look at a standing Healing Stream Totem cast from `source` (the skill's record or a rune's), `diff` milliseconds after the last.
    void Update(Player* player, Creature* totem, std::uint32_t source, Totems::State& state, std::uint32_t diff);
    // The upkeep of what ends by time (Cleansing Stream's immunity), from the class's 250 ms upkeep.
    void Upkeep(Player* player);
    // The hit of one of the skill's records, for the shell loader (see Searing::BasePct). Riptide's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A blow of `damage` on the Shaman: Ancestral Protection prevents it when it would kill (the damage becomes 0).
    void Fatal(Player* player, std::uint32_t& damage);
    void Forget(Player* player);
} // namespace DC::Combat::Shaman::HealingStream
