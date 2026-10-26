// World of DiabloCraft - the Mortar elite affix: shells lobbed at players outside the dead zone.

#include "dc_affix_internal.h"
#include "../dc_monster_ai.h"

#include "Creature.h"
#include "Map.h"
#include "Player.h"

#include <vector>

namespace DC::Rifts
{
void MortarTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Map* const map = t.map;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    if (now < state->nextVolley)
        return;
    // "lobbed fireballs towards players outside melee range": 3 per
    // cast every 4-5 s, with a dead zone inside 25 yards.
    state->nextVolley = now + n.mortarVolleyMs;
    std::vector<Unit*> targets;
    map->DoForAllPlayers([&](Player* player)
    {
        if (player && player->IsAlive() && elite->IsValidAttackTarget(player)
            && elite->GetDistance(player) >= n.mortarDeadZone)
            targets.push_back(player);
    });
    if (elite->IsCharmed())
        for (Unit* foe : AffixFoesOf(elite))
            if (elite->GetExactDist(foe) <= t.aiReach && elite->GetDistance(foe) >= n.mortarDeadZone)
                targets.push_back(foe);
    for (unsigned fired = 0; fired < n.mortarShells && !targets.empty(); ++fired)
    {
        Unit* player = targets[fired % targets.size()];
        // A shell is a one-shot ring: a small direct hit inside
        // direct_radius and a wider, weaker splash out to
        // collateral_radius, both after the published warning window.
        // §10 says the two radii are the point; the shell itself is
        // the visual step's marker.
        Hazard hz = BaseHazard(elite, rift, affix.shell);
        hz.path = HazardPath::Ballistic;
        hz.tag = TAG_MORTAR;
        hz.originX = hz.x = elite->GetPositionX();
        hz.originY = hz.y = elite->GetPositionY();
        hz.originZ = hz.z = elite->GetPositionZ();
        hz.impactX = player->GetPositionX();
        hz.impactY = player->GetPositionY();
        hz.impactZ = player->GetPositionZ();
        hz.radius = n.mortarSplash;
        hz.innerRadius = static_cast<float>(
            n.Parameter("Mortar|direct_radius"));
        hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name, "base_collateral_damage");
        hz.innerDamage = AffixDamage(n, state->tier, state->grLevel, affix.name);       // direct hit
        hz.oneShot = true;
        hz.tickMs = 1;
        hz.armUntil = now + n.mortarArmMs;
        // Backstop only: a one-shot retires itself the moment it
        // fires, so a lagging map update cannot skip its damage.
        hz.endsAt = now + n.mortarArmMs + 5000;
        hz.nextTick = now + n.mortarArmMs;
        SpawnHazard(std::move(hz));
    }
}
}
