// World of DiabloCraft - the Poison Enchanted elite affix: a bomb whose four gas lines grow outward in a cross.

#include "dc_affix_internal.h"

#include "Creature.h"

#include <algorithm>
#include <cmath>

namespace DC::Rifts
{
void PoisonEnchantedTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    EliteState* pack = PackStateOf(elite, state);
    std::uint32_t& next = pack->nextCastFor["poison-pack"];
    if (now < next)
        return;
    next = now + std::max(Ms(n.Parameter("Poison Enchanted|cooldown")),
                          n.poisonArmMs + n.poisonMs);
    // Poison Enchanted, §10: a bomb arms, then four lines of gas
    // expand outward in a cross - not four static pools. A GrowLine
    // hazard is anchored at the bomb and its far end advances, so
    // the gap between the arms is the dodge.
    float const trailLength = static_cast<float>(
        n.Parameter("Poison Enchanted|trail_length"));
    if (trailLength <= 0.0f)
        return;
    for (unsigned index = 0; index < n.poisonPools; ++index)
    {
        float const angle = static_cast<float>(index) / n.poisonPools
                            * 2.0f * float(M_PI);
        Hazard hz = BaseHazard(elite, rift, affix.shell);
        hz.path = HazardPath::GrowLine;
        hz.tag = TAG_POISON;
        hz.originX = hz.x = elite->GetPositionX();
        hz.originY = hz.y = elite->GetPositionY();
        hz.originZ = hz.z = elite->GetPositionZ();
        hz.dirX = std::cos(angle);
        hz.dirY = std::sin(angle);
        // trail_width is the published full width.
        hz.halfWidth = n.poisonWidth * 0.5f;
        hz.maxLength = trailLength;
        hz.length = 0.0f;
        hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
        hz.tickMs = n.tickMs;
        hz.armUntil = now + n.poisonArmMs;
        hz.endsAt = now + n.poisonArmMs + n.poisonMs;
        hz.nextTick = now + n.poisonArmMs;
        SpawnHazard(std::move(hz));
    }
}
}
