// World of DiabloCraft - the Nightmarish elite affix: a landed attack can fear the player.

#include "dc_affix_internal.h"

#include "Creature.h"
#include "Player.h"

namespace DC::Rifts
{
void NightmarishHit(Creature* elite, Player* player, AffixNumbers const& n)
{
    ApplyHold(elite, player, FEAR_HOLD, n.nightmarishMs);
}
}
