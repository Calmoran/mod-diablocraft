// World of DiabloCraft - the Electrified elite affix: a struck monster throws piercing charged bolts outward.

#include "dc_affix_internal.h"

#include "Creature.h"

#include <algorithm>
#include <cmath>

namespace DC::Rifts
{
void ElectrifiedStruck(Creature* elite, EliteState* state, AffixNumbers const& n, std::uint32_t now,
                       Affix const& affix)
{
    // Electrified, §10: struck monsters throw charged bolts outward
    // that travel and pierce - not the instant discharge this used
    // to be. The count scales from bolts_full_life at full Life to
    // bolts_near_death near death, and the bolts are Linear hazards
    // so a second player in the path can be hit.
    std::uint32_t& next = state->nextCastFor["reflect"];
    if (now >= next)
    {
        next = now + std::max<std::uint32_t>(1,
            Ms(n.Parameter("Electrified|internal_cooldown")));
        Rift rift;
        if (RiftOf(elite, rift))
        {
            double const full = n.Parameter("Electrified|bolts_full_life");
            double const low = n.Parameter("Electrified|bolts_near_death");
            double const missing = 1.0 - elite->GetHealthPct() / 100.0;
            unsigned const bolts = std::max<unsigned>(1,
                static_cast<unsigned>(full + (low - full) * missing + 0.5));
            float const speed = static_cast<float>(
                n.Parameter("Electrified|bolt_speed"));
            // PLACEHOLDER rows: D3 publishes neither, so a blank is 0
            // and the bolts do not move or connect until set
            // (never a number invented here).
            float const boltRadius = static_cast<float>(
                n.Parameter("Electrified|bolt_radius"));
            float const boltLength = static_cast<float>(
                n.Parameter("Electrified|bolt_length"));
            if (speed <= 0.0f || boltRadius <= 0.0f || boltLength <= 0.0f)
                return;
            for (unsigned index = 0; index < bolts; ++index)
            {
                float const angle = static_cast<float>(index) / bolts
                                    * 2.0f * float(M_PI);
                Hazard hz = BaseHazard(elite, rift, affix.shell);
                hz.path = HazardPath::Linear;
                hz.tag = TAG_BOLT;
                hz.originX = hz.x = elite->GetPositionX();
                hz.originY = hz.y = elite->GetPositionY();
                hz.originZ = hz.z = elite->GetPositionZ();
                hz.contactX = hz.x;
                hz.contactY = hz.y;
                hz.dirX = std::cos(angle);
                hz.dirY = std::sin(angle);
                hz.speed = speed;
                hz.radius = boltRadius;
                hz.maxLength = boltLength;
                hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
                hz.tickMs = 50;
                hz.oncePerTarget = true;
                hz.armUntil = now;
                hz.endsAt = (speed > 0.0f && boltLength > 0.0f)
                    ? now + Ms(boltLength / speed) + 100
                    : now + 1000;
                hz.nextTick = now;
                SpawnHazard(std::move(hz));
            }
        }
    }
}
}
