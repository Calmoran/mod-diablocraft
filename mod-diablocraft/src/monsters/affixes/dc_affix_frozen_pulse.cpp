// World of DiabloCraft - the Frozen Pulse elite affix: a sphere that chases a player, settles and pulses cold.

#include "dc_affix_internal.h"

#include "Creature.h"

namespace DC::Rifts
{
void FrozenPulseTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    Unit* const victim = t.Aim(t.aiReach);
    if (!victim)
        return;
    // Frozen Pulse, §10: a sphere that chases the player, settles on
    // reaching him once, then pulses cold where it stopped for the
    // rest of its life. The chase is the affix - a zone that appears
    // where you already are is not this.
    Hazard hz = BaseHazard(elite, rift, affix.shell);
    hz.path = HazardPath::Tracking;
    hz.tag = TAG_PULSE;
    hz.originX = hz.x = elite->GetPositionX();
    hz.originY = hz.y = elite->GetPositionY();
    hz.originZ = hz.z = elite->GetPositionZ();
    hz.target = victim->GetGUID();
    // chase_speed comes from the sheet. An unset row disables this affix;
    // there is no substitute movement speed.
    float const chase = static_cast<float>(n.Parameter("Frozen Pulse|chase_speed"));
    hz.speed = chase;
    hz.radius = n.pulseRadius;
    hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
    hz.slow = n.pulseSlow;
    hz.slowSpell = n.pulseSlowSpell;
    hz.tickMs = n.tickMs;
    hz.armUntil = now + n.pulseArmMs;
    hz.endsAt = now + n.pulseArmMs + n.pulseMs;
    hz.nextTick = now + n.pulseArmMs;
    SpawnHazard(std::move(hz));
}
}
