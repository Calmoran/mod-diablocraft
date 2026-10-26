// World of DiabloCraft - the Illusionist elite affix: a damaged monster summons weaker copies of itself.

#include "dc_affix_internal.h"

#include "Creature.h"
#include "Map.h"
#include "TemporarySummon.h"

#include <algorithm>
#include <cmath>

namespace DC::Rifts
{
    // An Illusionist duplicate is not an elite and carries no EliteState,
    // but it has one rule of its own: it despawns when the monster that
    // made it is gone or it has been dragged past the tuned distance
    // (maxroll: about three screens). Copies never make copies because
    // nothing without an EliteState runs the damage path below.
void IllusionistCopyUpdate(Creature* elite, Map* map, IllusionLink const* link)
{
    Creature* summoner = map->GetCreature(link->summoner);
    std::shared_ptr<AffixNumbers const> const numbers = Numbers();
    if (!numbers || !numbers->Enabled("Illusionist"))
    {
        elite->DespawnOrUnsummon();
        return;
    }
    float const keep = static_cast<float>(numbers->Parameter("Illusionist|despawn_distance"));
    if (!summoner || !summoner->IsAlive() || elite->GetDistance(summoner) > keep)
        elite->DespawnOrUnsummon();
    return;
}

void IllusionistStruck(Creature* elite, EliteState* state, AffixNumbers const& n, std::uint32_t now)
{
    // Illusionist, §10: re-summon on EVERY cooldown-ready damage event, not
    // once per pack - the old illusionsSpawned flag made one batch and then
    // nothing for the rest of the fight.
    if (HasAffix(*state, "illusionist") && n.Enabled("Illusionist")
        && elite->GetHealthPct() < n.illusionTrigger * 100.0)
    {
        std::uint32_t& next = state->nextCastFor["illusionist"];
        if (now >= next)
        {
            next = now + std::max<std::uint32_t>(1,
                Ms(n.Parameter("Illusionist|cooldown")));
            Map* map = elite->GetMap();
            unsigned const copies = n.illusionMin +
                static_cast<unsigned>(Roll() * (n.illusionMax - n.illusionMin + 1));
            for (unsigned index = 0; index < copies && map; ++index)
            {
                float const angle = static_cast<float>(index) / copies * 2.0f * float(M_PI);
                Position spot(elite->GetPositionX() + n.minionSpread * std::cos(angle),
                              elite->GetPositionY() + n.minionSpread * std::sin(angle),
                              elite->GetPositionZ(), elite->GetOrientation());
                // Duplicates are not pack members: they are not real, so
                // Avenger must not count them dying and Health Link must not
                // soak on them. IllusionLink is only for the despawn range.
                if (Creature* copy = map->SummonCreature(elite->GetEntry(), spot))
                {
                    ScaleLife(copy, n.illusionLife);
                    state->illusions.push_back(copy->GetGUID());
                    copy->CustomData.GetDefault<IllusionState>("DCRiftIllusion");
                    copy->CustomData.GetDefault<IllusionLink>("DCRiftIllusionLink")->summoner =
                        elite->GetGUID();
                }
            }
        }
    }
}
}
