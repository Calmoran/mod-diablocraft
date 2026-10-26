// World of DiabloCraft - the Frozen elite affix: ice crystals around a player that burst and freeze.

#include "dc_affix_internal.h"

#include "Creature.h"

#include <cmath>

namespace DC::Rifts
{
void FrozenTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    Unit* victim = now >= state->nextCastFor[affix.behaviour] ? t.Aim(t.aiReach) : nullptr;
    if (victim && t.Due(affix))
    {
        float const spread = static_cast<float>(n.Parameter("Frozen|crystal_spread"));
        if (spread <= 0.0f)
            return;
        unsigned const crystals = static_cast<unsigned>(n.Parameter("Frozen|orbs_per_cast"));
        for (unsigned i = 0; i < crystals; ++i)
        {
            float const angle = float(i) / crystals * 2.0f * float(M_PI);
            Hazard hz = BaseHazard(elite, rift, affix.shell);
            hz.x = victim->GetPositionX() + spread * std::cos(angle);
            hz.y = victim->GetPositionY() + spread * std::sin(angle);
            hz.z = victim->GetPositionZ();
            hz.radius = n.frozenRadius;
            hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
            hz.freezeMs = Ms(n.Parameter("Frozen|freeze_duration"));
            hz.oneShot = true;
            hz.tickMs = 1;
            hz.armUntil = hz.nextTick = now + n.frozenArmMs;
            hz.endsAt = hz.armUntil;
            SpawnHazard(std::move(hz));
        }
    }
}
}
