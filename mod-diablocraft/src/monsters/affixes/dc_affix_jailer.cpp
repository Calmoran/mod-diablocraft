// World of DiabloCraft - the Jailer elite affix: roots a player and hits them, on a pack-shared cooldown.

#include "dc_affix_internal.h"
#include "../../combat/dc_combat.h"

#include "Creature.h"
#include "Player.h"

namespace DC::Rifts
{
void JailerTick(AffixTick const& t, Affix const& affix)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    // Jailer, §10: the reach is the tuned 30 and the hold the
    // published 2.5 s; the cooldown is pack-shared (the wiki confirms
    // one, no value) so three champions cannot chain-root.
    EliteState* pack = PackStateOf(elite, state);
    Player* victim = now >= pack->nextCastFor["jailer"] ? t.Pick(n.jailerReach) : nullptr;
    if (victim && elite->GetDistance(victim) <= n.jailerReach
        && now >= pack->nextCastFor["jailer"])
    {
        pack->nextCastFor["jailer"] =
            now + Ms(n.Parameter("Jailer|cooldown"));
        // The visible root (13 §10) is the hold itself: a stock root aura cast by the elite, the tuned root
        // length on its duration, refused if the player is immune to roots.
        ApplyHold(elite, victim, JAILER_DEBUFF, n.jailerRootMs);
        elite->CastSpell(victim, affix.shell, true);
        DC::Combat::DealMonsterHit(elite, victim, affix.shell, AffixDamage(n, state->tier, state->grLevel, affix.name));
    }
    else if (elite->IsCharmed() && now >= pack->nextCastFor["jailer"])
    {
        // A charmed elite jails a former ally the same way.
        if (Unit* foe = PickFoe(elite, n.jailerReach))
        {
            pack->nextCastFor["jailer"] = now + Ms(n.Parameter("Jailer|cooldown"));
            HoldFoe(elite, foe, JAILER_DEBUFF, n.jailerRootMs);
            elite->CastSpell(foe, affix.shell, true);
            HitFoe(elite, foe, affix.shell, AffixDamage(n, state->tier, state->grLevel, affix.name));
        }
    }
}
}
