// World of DiabloCraft - the Thunderstorm elite affix: lightning strikes that follow a player.

#include "dc_affix_internal.h"

#include "Creature.h"

#include <algorithm>

namespace DC::Rifts
{
void ThunderstormTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    Unit* const victim = t.Aim(t.aiReach);
    double const interval = n.Parameter("Thunderstorm|strike_interval");
    float const speed = static_cast<float>(n.Parameter("Thunderstorm|follow_speed"));
    if (!victim || interval <= 0.0 || speed <= 0.0f)
        return;
    Hazard hz = BaseHazard(elite, rift, affix.shell);
    hz.path = HazardPath::Following;
    hz.target = victim->GetGUID();
    hz.x = victim->GetPositionX(); hz.y = victim->GetPositionY(); hz.z = victim->GetPositionZ();
    hz.radius = n.thunderstormRadius;
    hz.speed = speed;
    hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
    hz.strikesRemaining = n.thunderstormStrikes;
    hz.tickMs = std::max<uint32>(1, Ms(interval));
    hz.armUntil = hz.nextTick = now;
    hz.endsAt = 0xFFFFFFFFu; // retires after the sourced strike count
    SpawnHazard(std::move(hz));
}
}
