// World of DiabloCraft - the Arcane Enchanted elite affix: an orb that arms, then sweeps a beam through a full circle.

#include "dc_affix_internal.h"

#include "Creature.h"
#include "Map.h"

#include <algorithm>
#include <cmath>

namespace DC::Rifts
{
void ArcaneEnchantedTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    Unit* const victim = t.Aim(t.aiReach);
    if (!victim)
        return;
    // Arcane Enchanted: the orb arms for 2 s, then sweeps a 25-yard
    // beam through a full circle over its 10 s. Only the wedge is
    // hot, so standing where the beam is not is the whole dodge.
    Hazard hz = BaseHazard(elite, rift, affix.shell);
    hz.path = HazardPath::Sweep;
    hz.tag = TAG_BEAM;
    hz.originX = hz.x = victim->GetPositionX();
    hz.originY = hz.y = victim->GetPositionY();
    hz.originZ = hz.z = victim->GetPositionZ();
    hz.length = n.beamLength;                       // beam reach
    hz.angle = 0.0f;
    // Full circle over the published duration.
    hz.sweepRate = n.beamMs > 0 ? 2.0f * float(M_PI) / (n.beamMs / 1000.0f) : 0.0f;
    // wedge_width is the published full width; half of it is what a
    // player is measured against either side of the beam.
    hz.wedge = static_cast<float>(n.Parameter("Arcane Enchanted|wedge_width"))
               * float(M_PI) / 360.0f;
    hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
    // A full sweep contacts each player once. Sample every map
    // update instead of missing a narrow wedge between 1 s ticks.
    hz.tickMs = 1;
    hz.oncePerTarget = true;
    hz.armUntil = now + n.beamArmMs;
    hz.endsAt = now + n.beamArmMs + n.beamMs;
    state->nextCastFor[affix.behaviour] = std::max(state->nextCastFor[affix.behaviour], hz.endsAt);
    hz.nextTick = now + n.beamArmMs;
    SpawnHazard(std::move(hz));
}
}
