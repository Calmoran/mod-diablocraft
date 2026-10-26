// World of DiabloCraft - the Vortex elite affix: pulls a player into melee range.

#include "dc_affix_internal.h"
#include "../../combat/dc_pylons.h"

#include "Creature.h"
#include "PathGenerator.h"

#include <cmath>

namespace DC::Rifts
{
void VortexTick(AffixTick const& t, Affix const&)
{
    Creature* const elite = t.elite;
    AffixNumbers const& n = t.n;
    Unit* const victim = t.Aim(n.vortexRange);
    if (!(victim && elite->GetDistance(victim) <= n.vortexRange))
        return;
    // "pulls the player directly into the monster's melee range": a
    // knockback away from the elite with a negative horizontal speed
    // is a pull towards it, which is how the core writes a pull
    // (boss_maexxna). The magnitude needs the same conversion the
    // Knockback affix needs (docs/research/knockback-speeds.md):
    // KnockbackFrom takes speeds, so the distance to cover -
    // everything but the elite's own melee range - goes through
    // speedXY = distance * gravity / (2 * speedZ) on the tuned arc.
    // Passing the distance itself with speedZ 0, as this did, gives
    // the parabola no flight time at all and moves nobody.
    float const travel = elite->GetDistance(victim) - elite->GetMeleeRange(victim);
    // Shield Pylon: nothing pulls the wearer (pylons.md 6.3: Vortex is a control effect).
    if (DC::Combat::Pylons::Shielded(victim))
        return;
    if (travel > 0.0f && n.knockbackSpeedZ > 0.0f)
    {
        float const dx = elite->GetPositionX() - victim->GetPositionX();
        float const dy = elite->GetPositionY() - victim->GetPositionY();
        float const distance = std::hypot(dx, dy);
        if (distance <= 0.0f)
            return;
        float const px = victim->GetPositionX() + dx / distance * travel;
        float const py = victim->GetPositionY() + dy / distance * travel;
        float pz = victim->GetPositionZ();
        victim->UpdateGroundPositionZ(px, py, pz);
        PathGenerator path(victim);
        path.SetUseRaycast(true);
        if (!victim->IsWithinLOS(px, py, pz) || !path.CalculatePath(px, py, pz)
            || path.GetPathType() != PATHFIND_NORMAL)
            return; // Reject walls, ledges and missing mesh; never pull on a shortcut.
        victim->InterruptNonMeleeSpells(false);
        victim->KnockbackFrom(elite->GetPositionX(), elite->GetPositionY(),
                              -travel * KNOCKBACK_GRAVITY / (2.0f * n.knockbackSpeedZ),
                              n.knockbackSpeedZ);
    }
}
}
