// World of DiabloCraft - the Molten elite affix: a lava trail behind the monster and a blast where it dies.

#include "dc_affix_internal.h"

#include "Creature.h"

#include <algorithm>

namespace DC::Rifts
{
void MoltenTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    // Molten, §10: a trail of lava behind the monster, not the ground
    // it is standing on. A static segment is dropped every
    // trail_interval while it is actually moving - half its own trail
    // radius since the last one, so a stationary elite does not stack
    // pools under itself - and each segment lives trail_lifetime.
    std::uint32_t const interval = std::max<std::uint32_t>(1,
        Ms(n.Parameter("Molten|trail_interval")));
    std::uint32_t& next = state->nextCastFor["trail"];
    if (now >= next)
    {
        float const x = elite->GetPositionX(), y = elite->GetPositionY();
        bool const moved = state->trailPositionKnown && (x != state->trailX || y != state->trailY);
        state->trailPositionKnown = true;
        state->trailX = x;
        state->trailY = y;
        next = now + interval;
        if (moved)
        {
            next = now + interval;
            Hazard hz = BaseHazard(elite, rift, affix.shell);
            hz.path = HazardPath::Static;
            hz.tag = TAG_TRAIL;
            hz.x = elite->GetPositionX();
            hz.y = elite->GetPositionY();
            hz.z = elite->GetPositionZ();
            hz.radius = n.moltenTrailRadius;
            hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
            hz.tickMs = n.tickMs;
            hz.armUntil = now;
            hz.endsAt = now + Ms(n.Parameter("Molten|trail_lifetime"));
            hz.nextTick = now;
            SpawnHazard(std::move(hz));
        }
    }
}

// The update comes round at least as often as the trail is laid.
std::uint32_t MoltenUpdateMs(EliteState const& state, AffixNumbers const& n)
{
    return HasAffix(state, "trail") && n.Enabled("Molten")
        ? std::min(n.tickMs, std::max<std::uint32_t>(1, Ms(n.Parameter("Molten|trail_interval"))))
        : n.tickMs;
}

void MoltenDeath(Creature* elite, Rift const& rift, EliteState const* state, AffixNumbers const& n)
{
    for (Affix const& affix : state->affixes)
        if (affix.behaviour == "trail" && n.Enabled(affix.name))
            // Molten's body "explode[s] after 3 seconds" over maxroll's
            // published 18 yards - dodgeable, and it has to be.
            QueueBurst(elite, rift, elite->GetPositionX(), elite->GetPositionY(),
                       elite->GetPositionZ(), n.moltenBlastRadius, affix.shell,
                       AffixDamage(n, state->tier, state->grLevel, affix.name, "base_explosion_damage"), n.moltenFuseMs);
}
}
