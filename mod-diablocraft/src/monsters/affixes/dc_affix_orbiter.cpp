// World of DiabloCraft - the Orbiter elite affix: a focal point whose spheres spiral outward.

#include "dc_affix_internal.h"

#include "Creature.h"

#include <algorithm>
#include <cmath>

namespace DC::Rifts
{
void OrbiterTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    // D3 gives a champion a second, wider orbit (30 yd against a
    // rare's 15), so each rank reads its own outer radius; the
    // guard is the same for both.
    char const* const radiusKey = state->rare ? "Orbiter|max_radius"
                                              : "Orbiter|max_radius_champion";
    if (n.Parameter("Orbiter|orbit_speed") <= 0.0
        || n.Parameter(radiusKey) <= n.orbiterRadius)
        return;
    // Orbiter, §10: a central focal point releases spheres in an
    // expanding spiral and they orbit it. 5-9 spheres is the
    // published count; orbit_speed and max_radius are PLACEHOLDER
    // rows (D3 publishes neither). An unset row disables Orbiter;
    // stationary spheres are not a substitute for its spiral.
    Hazard core = BaseHazard(elite, rift, affix.shell);
    core.path = HazardPath::Static;
    core.tag = TAG_CORE;
    core.x = elite->GetPositionX();
    core.y = elite->GetPositionY();
    core.z = elite->GetPositionZ();
    core.radius = n.orbiterRadius;
    core.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
    core.tickMs = n.tickMs;
    core.armUntil = now;
    core.endsAt = now + n.orbiterMs;
    core.nextTick = now;
    SpawnHazard(std::move(core));

    double const minSpheres = n.Parameter("Orbiter|spheres_min");
    double const maxSpheres = n.Parameter("Orbiter|spheres_max");
    unsigned const spheres = static_cast<unsigned>(minSpheres)
        + static_cast<unsigned>(Roll() * std::max(1.0, maxSpheres - minSpheres + 1.0));
    float const orbitSpeed = static_cast<float>(n.Parameter("Orbiter|orbit_speed"))
                             * float(M_PI) / 180.0f;
    float const sphereRadius = static_cast<float>(
        n.Parameter("Orbiter|sphere_radius"));
    float const maxRadius = static_cast<float>(
        n.Parameter(radiusKey));
    for (unsigned index = 0; index < spheres; ++index)
    {
        Hazard sphere = BaseHazard(elite, rift, affix.shell);
        sphere.path = HazardPath::Orbital;
        sphere.tag = TAG_SPHERE;
        sphere.originX = elite->GetPositionX();
        sphere.originY = elite->GetPositionY();
        sphere.originZ = sphere.z = elite->GetPositionZ();
        sphere.angle = float(index) / spheres * 2.0f * float(M_PI);
        sphere.orbitStart = n.orbiterRadius;
        sphere.orbitRadius = sphere.orbitStart;
        sphere.orbitMax = std::max(maxRadius, n.orbiterRadius);
        sphere.orbitSpeed = orbitSpeed;
        sphere.radius = sphereRadius;
        sphere.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
        sphere.tickMs = n.tickMs;
        sphere.armUntil = now;
        sphere.endsAt = now + n.orbiterMs;
        sphere.nextTick = now;
        SpawnHazard(std::move(sphere));
    }
}
}
