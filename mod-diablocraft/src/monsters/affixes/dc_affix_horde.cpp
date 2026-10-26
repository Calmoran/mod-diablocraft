// World of DiabloCraft - the Horde elite affix: a rare's minion count, multiplied.

#include "dc_affix_internal.h"

#include "Creature.h"

namespace DC::Rifts
{
    // Horde "doubles the amount of minions" and publishes no absolute count:
    // the base is rolled first and then multiplied, so 2-4 becomes 4-8 and
    // it follows the base if that is ever retuned. The 6-10 we
    // had was invented and is gone.
unsigned HordeMinions(EliteState const& state, AffixNumbers const& n, unsigned count)
{
    return HasAffix(state, "horde") ? count * n.hordeMultiplier : count;
}
}
