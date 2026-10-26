// World of DiabloCraft - the Teleporter elite affix: steps toward a player out of reach, away from one in melee.

#include "dc_affix_internal.h"

#include "Creature.h"
#include "PathGenerator.h"

#include <algorithm>
#include <cmath>

namespace DC::Rifts
{
void TeleporterTick(AffixTick const& t, Affix const&)
{
    Creature* const elite = t.elite;
    AffixNumbers const& n = t.n;
    Unit* const victim = t.Aim(t.aiReach);
    if (!victim)
        return;
    // Teleporter, §10: directional, not random. The wiki is explicit
    // - it closes when you are out of reach and escapes when you are
    // on top of it - so out of melee it steps toward the player, and
    // inside melee it steps the tuned range away; a random angle was
    // a different affix. The step is Teleporter|range, snapped to
    // land in melee rather than through the player.
    float dirX = victim->GetPositionX() - elite->GetPositionX();
    float dirY = victim->GetPositionY() - elite->GetPositionY();
    float const len = std::sqrt(dirX * dirX + dirY * dirY);
    if (len < 0.001f)
    {
        // Exactly on top of each other: any direction is "away".
        dirX = std::cos(elite->GetOrientation());
        dirY = std::sin(elite->GetOrientation());
    }
    else
    {
        dirX /= len;
        dirY /= len;
    }
    float const dist = elite->GetDistance(victim);
    float const melee = elite->GetMeleeRange(victim);
    float step = n.teleporterRange;
    if (dist > melee)
        step = std::min(step, dist - melee);   // toward, into reach
    else
        step = -step;                          // away, out of reach
    float px = elite->GetPositionX() + dirX * step;
    float py = elite->GetPositionY() + dirY * step;
    float pz = elite->GetPositionZ();
    elite->UpdateGroundPositionZ(px, py, pz);
    PathGenerator path(elite);
    path.SetUseRaycast(true);
    if (!elite->IsWithinLOS(px, py, pz) || !path.CalculatePath(px, py, pz)
        || path.GetPathType() != PATHFIND_NORMAL)
        return;
    elite->NearTeleportTo(px, py, pz, elite->GetOrientation());
}
}
