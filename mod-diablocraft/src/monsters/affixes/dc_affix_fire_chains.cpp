// World of DiabloCraft - the Fire Chains elite affix: burning links between every pair of champions.

#include "dc_affix_internal.h"

#include "Creature.h"
#include "Map.h"

#include <algorithm>
#include <mutex>
#include <vector>

namespace DC::Rifts
{
void FireChainsTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    Map* const map = t.map;
    Rift const& rift = t.rift;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    // Fire Chains, §10: every PAIR of living champions is joined by a
    // burning segment, and the burn is perpendicular distance to that
    // segment - not a blob at the midpoint.
    // The leader owns the links, so a pack
    // of three makes three chains rather than two, and a link whose
    // member dies is torn down by the subsystem on the next tick.
    if (!state->member)
    {
        std::vector<Creature*> members = PackMembers(elite, *state);
        if (members.size() >= n.chainsMembers)
        {
            std::uint32_t const tick = std::max<std::uint32_t>(1,
                static_cast<std::uint32_t>(1000.0
                    / std::max(0.001, n.Parameter("Fire Chains|tick_rate"))));
            // chain_width is the published full width; a player is
            // measured against half of it either side of the segment.
            float const half = n.chainsWidth * 0.5f;
            std::lock_guard<std::mutex> lock(workMutex);
            auto& hazards = hazardMaps[MapWorkKey(map)];
            for (std::size_t i = 0; i < members.size(); ++i)
                for (std::size_t j = i + 1; j < members.size(); ++j)
                {
                    ObjectGuid a = members[i]->GetGUID();
                    ObjectGuid b = members[j]->GetGUID();
                    if (a.GetRawValue() > b.GetRawValue())
                        std::swap(a, b);
                    bool present = false;
                    for (Hazard const& h : hazards)
                        if (h.tag == TAG_CHAIN && h.linkA == a && h.linkB == b)
                        {
                            present = true;
                            break;
                        }
                    if (present)
                        continue;
                    Hazard hz = BaseHazard(elite, rift, affix.shell);
                    hz.path = HazardPath::Link;
                    hz.tag = TAG_CHAIN;
                    hz.linkA = a;
                    hz.linkB = b;
                    hz.halfWidth = half;
                    hz.damage = AffixDamage(n, state->tier, state->grLevel, affix.name);
                    hz.tickMs = tick;
                    hz.armUntil = now;
                    // Until a member dies; MoveHazard tears it down.
                    hz.endsAt = 0xFFFFFFFFu;
                    hz.nextTick = now;
                    hazards.push_back(std::move(hz));
                }
        }
    }
}
}
