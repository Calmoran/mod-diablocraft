// World of DiabloCraft - the Knockback elite affix: a landed attack throws the player back and slows them.

#include "dc_affix_internal.h"
#include "../../combat/dc_pylons.h"

#include "Creature.h"
#include "Player.h"

namespace DC::Rifts
{
void KnockbackHit(Creature* elite, EliteState* state, Player* player, AffixNumbers const& n)
{
    // Shield Pylon: nothing knocks the wearer back (pylons.md 6.3), and a shielded hit spends no cooldown.
    if (DC::Combat::Pylons::Shielded(player))
        return;
    // Pack-shared cooldown (not published; a tunable) so three
    // champions cannot juggle the player between them.
    EliteState* pack = PackStateOf(elite, state);
    std::uint32_t const now = getMSTime();
    if (now < pack->nextCastFor["knockback"])
        return;
    pack->nextCastFor["knockback"] =
        now + Ms(n.Parameter("Knockback|cooldown"));
    // The speed pair that lands the tuned distance on the ground;
    // see AffixNumbers::knockbackSpeedXY for where it comes from.
    // "damage: none" - elite_affix_mechanics.csv.
    player->InterruptNonMeleeSpells(false);
    player->KnockbackFrom(elite->GetPositionX(), elite->GetPositionY(),
                          n.knockbackSpeedXY, n.knockbackSpeedZ);
    ApplySlow(elite, player, n.knockbackSlowSpell, n.knockbackSlow, n.knockbackMs);
}
}
