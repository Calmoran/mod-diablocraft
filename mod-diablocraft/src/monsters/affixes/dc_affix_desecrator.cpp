// World of DiabloCraft - the Desecrator elite affix: an escalating void pool under each player.

#include "dc_affix_internal.h"
#include "../dc_monster_ai.h"

#include "Creature.h"
#include "Map.h"
#include "Player.h"

#include <algorithm>

namespace DC::Rifts
{
void DesecratorTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Map* const map = t.map;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    if (n.Parameter("Desecrator|pool_lifetime") <= 0.0)
        return;
    // Desecrator, §10: a void directly beneath each player, arming
    // for 1 s, then ESCALATING - damage doubles every 0.5 s to ten
    // steps. That escalation is the affix; until now it was a flat
    // 1-second tick. Same code path as Plagued, other placement.
    double const stackMs = n.Parameter("Desecrator|damage_stack_interval");
    auto pool = [&](Unit* player)
    {
        if (!player || !player->IsAlive() || !elite->IsValidAttackTarget(player))
            return;
        Hazard hz = BaseHazard(elite, rift, affix.shell);
        hz.path = HazardPath::Static;
        hz.tag = TAG_POOL;
        hz.x = player->GetPositionX();
        hz.y = player->GetPositionY();
        hz.z = player->GetPositionZ();
        hz.radius = n.desecratorRadius;
        hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
        hz.escalating = true;
        hz.stackMultiplier = n.Parameter("Desecrator|damage_stack_multiplier");
        hz.stackIntervalMs = Ms(stackMs);
        hz.stackMax = static_cast<unsigned>(
            n.Parameter("Desecrator|damage_stack_max"));
        // Same 1 s as the entry delay, per §10.
        hz.stackEntryMs = n.desecratorArmMs;
        hz.stackResetMs = n.desecratorArmMs;
        hz.tickMs = std::max<std::uint32_t>(1, Ms(stackMs));
        hz.armUntil = now + n.desecratorArmMs;
        // Lifetime is a separate tunable; owner death cancels
        // this pool regardless of its remaining lifetime.
        hz.endsAt = now + n.desecratorArmMs
            + Ms(n.Parameter("Desecrator|pool_lifetime"));
        hz.nextTick = now + n.desecratorArmMs;
        SpawnHazard(std::move(hz));
    };
    map->DoForAllPlayers([&](Player* player) { pool(player); });
    // A charmed elite sinks a pool under each former ally within its reach.
    if (elite->IsCharmed())
        for (Unit* foe : AffixFoesOf(elite))
            if (elite->GetExactDist(foe) <= t.aiReach)
                pool(foe);
}
}
