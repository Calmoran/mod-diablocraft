// World of DiabloCraft - the Health Link elite affix: a hit on one champion is shared across the pack.

#include "dc_affix_internal.h"

#include "Creature.h"

#include <algorithm>
#include <vector>

namespace DC::Rifts
{
// The Life a member keeps: `fraction` of its max, in whole numbers.
static std::uint64_t LifeFloor(Creature const* creature, double fraction)
{
    return static_cast<std::uint64_t>(static_cast<long double>(creature->GetMaxHealth()) * fraction);
}

// `damage` is the exact hit (the exact-hit hook runs before any 32-bit consumer), changed to what the struck elite keeps.
void HealthLinkStruck(Creature* elite, EliteState* state, AffixNumbers const& n, std::uint64_t& damage)
{
    // "Damage dealt to any single Champion is distributed equally among all
    // living pack members" - so a hit on a member splits as well, and the
    // link itself lives on the leader, which is the only member that can
    // carry it: Health Link is champion-only and does not pass to minions.
    Creature* linkLeader = state->member ? PackLeaderOf(elite) : elite;
    EliteState* linkState = linkLeader == elite
        ? state
        : (linkLeader ? linkLeader->CustomData.Get<EliteState>("DCRiftElite") : nullptr);
    if (linkLeader && linkState && HasAffix(*linkState, "healthlink") && n.Enabled("Health Link"))
    {
        std::vector<Creature*> members = PackMembers(linkLeader, *linkState);
        double const range = n.Parameter("Health Link|link_range");
        members.erase(std::remove_if(members.begin(), members.end(),
            [&](Creature* member)
            {
                return member != elite && ((range > 0.0 && elite->GetDistance(member) > range)
                    || member->GetHealth() <= LifeFloor(member, n.healthLinkFloor));
            }), members.end());
        if (members.size() > 1)
        {
            // A plain whole-number split of the exact hit: every other member takes hit / count, and the struck one
            // keeps its share plus the remainder. Each member holds its own real Life.
            std::uint64_t const count = members.size();
            std::uint64_t const share = damage / count;
            for (Creature* member : members)
            {
                if (member == elite)
                    continue;
                // Taken off the member's health rather than run back through
                // the damage pipeline, which would re-enter this hook. A
                // member is left on low_life_threshold rather than killed
                // here; it dies to a real hit like anything else.
                std::uint64_t const floorHp = LifeFloor(member, n.healthLinkFloor);
                std::uint64_t const available = member->GetHealth() > floorHp
                    ? member->GetHealth() - floorHp : 0;
                member->SetHealth(member->GetHealth() - std::min(share, available));
            }
            damage = share + damage % count;
        }
    }
}
}
