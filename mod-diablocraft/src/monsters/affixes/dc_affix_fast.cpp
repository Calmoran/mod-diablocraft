// World of DiabloCraft - the Fast elite affix: faster movement, attacks and casts.

#include "dc_affix_internal.h"

#include "Creature.h"

namespace DC::Rifts
{
void FastPassive(Creature* elite, EliteState const& state, AffixNumbers const& n)
{
    if (HasAffix(state, "fast") && n.Enabled("Fast"))
    {
        // Faster attacks shorten the swing interval by the speed ratio.
        AddPace(elite, n.fastMove, n.fastAttack);
        elite->ApplyCastTimePercentMod(static_cast<float>(n.Parameter("Fast|cast_speed")), true);
    }
}
}
