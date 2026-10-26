// World of DiabloCraft - the Reflects Damage elite affix: a pack-held window in which a player's hit is answered.

#include "dc_affix_internal.h"
#include "../../combat/dc_combat.h"

#include "Creature.h"
#include "Player.h"

namespace DC::Rifts
{
void ReflectsDamageTick(AffixTick const& t, Affix const&)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    // One pack member claims the warning and active window.
    EliteState* pack = PackStateOf(elite, state);
    if (now >= pack->reflectUntil)
    {
        pack->reflectHolder = elite->GetGUID();
        pack->reflectFrom = now + n.reflectArmMs;
        pack->reflectUntil = pack->reflectFrom + n.reflectMs;
    }
}

void ReflectsDamageStruck(Creature* elite, EliteState* state, EliteState* pack, Player* player,
                          AffixNumbers const& n, std::uint32_t now, Affix const& affix,
                          DC::Combat::PreCritHit const* preCrit)
{
    if (!(preCrit && pack->reflectHolder == elite->GetGUID()
          && now >= pack->reflectFrom && now < pack->reflectUntil
          && now >= pack->nextCastFor["reflect-hit"]))
        return;
    pack->nextCastFor["reflect-hit"] = now + Ms(n.Parameter("Reflects Damage|internal_cooldown"));
    elite->CastSpell(player, affix.shell, true);
    // The player's hit only triggers it: the damage is the affix's own, in the hit's school.
    DC::Combat::DealMonsterHit(elite, player, affix.shell,
                               AffixDamage(n, state->tier, state->grLevel, affix.name), preCrit->school);
}

void ReflectsDamageDeath(Creature* elite, EliteState* pack)
{
    if (pack->reflectHolder == elite->GetGUID())
    {
        pack->reflectUntil = 0;
        pack->reflectHolder.Clear();
    }
}
}
