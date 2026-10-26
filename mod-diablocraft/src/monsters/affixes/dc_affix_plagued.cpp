// World of DiabloCraft - the Plagued elite affix: escalating poison pools under the monster.

#include "dc_affix_internal.h"

#include "Creature.h"

#include <algorithm>

namespace DC::Rifts
{
void PlaguedTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    // Plagued, §10: the same escalating pool as Desecrator, under the
    // MONSTER rather than the player, so kiting leaves puddles behind
    // and standing in one stacks. The x2 was never blocked on §11
    // question 2 - that question is only whether a pool dies with its
    // caster; it does. Duration is a
    // separate tunable and this client waits until it is set.
    std::uint32_t& next = state->nextCastFor["pool"];
    if (now >= next)
    {
        next = now + Ms(n.Parameter("Plagued|cast_interval"));
        if (n.Parameter("Plagued|pool_lifetime") <= 0.0)
            return;
        double const stackMs = n.Parameter("Plagued|damage_stack_interval");
        Hazard hz = BaseHazard(elite, rift, affix.shell);
        hz.path = HazardPath::Static;
        hz.tag = TAG_POOL;
        hz.x = elite->GetPositionX();
        hz.y = elite->GetPositionY();
        hz.z = elite->GetPositionZ();
        hz.radius = n.plaguedRadius;
        hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
        hz.escalating = true;
        hz.stackMultiplier = n.Parameter("Plagued|damage_stack_multiplier");
        hz.stackIntervalMs = Ms(stackMs);
        hz.stackMax = static_cast<unsigned>(
            n.Parameter("Plagued|damage_stack_max"));
        // Plagued publishes no entry delay; §10 gives it Desecrator's
        // 1 s on leaving.
        hz.stackResetMs = n.desecratorArmMs;
        hz.tickMs = std::max<std::uint32_t>(1, Ms(stackMs));
        hz.armUntil = now;
        hz.endsAt = now + Ms(n.Parameter("Plagued|pool_lifetime"));
        hz.nextTick = now;
        SpawnHazard(std::move(hz));
    }
}
}
