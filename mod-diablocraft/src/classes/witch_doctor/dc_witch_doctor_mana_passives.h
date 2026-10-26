#pragma once
// The Witch Doctor's passives that give Mana over time: Rush of Essence and Vision Quest. The rules that need no core
// type are dc_witch_doctor_passive_rules.h; the numbers are witch_doctor_passive_values.csv, read through each
// passive's record.
#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::Passive::ManaOverTime
{
    // A cast of `spellId` resolved (Combat::ResolveCast): a spirit spell starts a Rush of Essence stream.
    void Cast(Player* player, std::uint32_t spellId);
    // A hit of `spellId` landed (Combat's ResolveHit and Strike): damage by a Vision Quest skill raises the
    // regeneration.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::WitchDoctor::Passive::ManaOverTime
