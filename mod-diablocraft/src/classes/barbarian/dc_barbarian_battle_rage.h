// Battle Rage: the critical chance buff, its runes and the recent-crits bloodshed.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::BattleRage
{
    using Shared::Row;
    using Shared::State;

    // Adds the damage bonus the buff gives.
    void OnDamageBonus(Player* p, double& result);
    // The buff's critical chance and its runes' contributions, a part of the player's refresh. `frayEnemies` is the enemies Into the Fray counts.
    void OnRefresh(Player* p, std::size_t& frayEnemies);
    // The cast: the buff on the caster.
    void OnCast(Player* p, uint32 id, Row const* r, Row const* b);
    // A critical hit of `damage` was dealt: Swords to Ploughshares heals, Bloodshed remembers the hit. Called with the module lock held.
    void OnCritical(Player* p, double damage);
    // The player's upkeep: Bloodshed's pulse of the recent critical hits.
    void OnUpdate(Player* p, State& s, uint32 diff);
    // Mixes the enemies Into the Fray counts into the signature that tells the upkeep to refresh.
    void OnSignature(Player* p, uint64& signature);
} // namespace DC::Combat::Abilities::BattleRage
