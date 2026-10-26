#pragma once
// The Witch Doctor's passives that change what a hit or a cast deals or costs: Pierce the Veil and Confidence Ritual. The rules that need no
// core type are dc_witch_doctor_passive_rules.h; the numbers are witch_doctor_passive_values.csv, read through each
// passive's record.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::Passive::Damage
{
    // The multipliers of a hit of `spellId` on `target` (Combat's ComputeHit, beside the other classes'): Pierce the
    // Veil's.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
    // A cast of `spellId` resolved (Combat::ResolveCast): the Mana Pierce the Veil costs on top of the record's.
    void Cast(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::WitchDoctor::Passive::Damage
