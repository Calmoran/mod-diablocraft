// World of DiabloCraft - the Shielding elite affix: one pack member at a time is immune to all damage.

#include "dc_affix_internal.h"

#include "Creature.h"
#include "Map.h"
#include "SpellAuraDefines.h"

namespace DC::Rifts
{
void ShieldingTick(AffixTick const& t, Affix const&)
{
    Creature* const elite = t.elite;
    EliteState* const state = t.state;
    AffixNumbers const& n = t.n;
    std::uint32_t const now = t.now;
    // "Only one monster in a pack can shield at a time." Shielding
    // passes to a Rare's minions, so the window can no longer be
    // kept per monster: the leader's state holds it and whoever
    // claims it first wears it.
    EliteState* pack = PackStateOf(elite, state);
    Creature* owner = state->member ? PackLeaderOf(elite) : elite;
    // Blizzard 2.4.3: the shield cancels immediately once its bearer
    // is the pack's last living monster, so a solo survivor cannot
    // stall the fight.
    if (!owner || PackMembers(owner, *pack).size() <= 1)
    {
        pack->shieldUntil = 0;
        return;
    }
    if (now >= pack->nextShield)
    {
        pack->nextShield = now + n.shieldingGapMs;
        pack->shieldUntil = now + n.shieldingMs;
        pack->shieldHolder = elite->GetGUID();
        SetShieldImmunity(elite, state, true);
    }
}

void ShieldingUpdate(Creature* elite, EliteState* state, AffixNumbers const& n)
{
    if (HasAffix(*state, "shielding"))
    {
        EliteState* pack = PackStateOf(elite, state);
        SetShieldImmunity(elite, state, n.Enabled("Shielding") && elite->IsAlive()
            && pack->shieldHolder == elite->GetGUID() && getMSTime() < pack->shieldUntil);
    }
}

// A hit on the pack's shield holder inside its window does nothing.
bool ShieldingAbsorbs(Creature* elite, EliteState* state, EliteState* pack, std::uint32_t now,
                      std::uint32_t& damage)
{
    if (HasAffix(*state, "shielding") && now < pack->shieldUntil
        && pack->shieldHolder == elite->GetGUID())
    {
        // Blizzard 2.4.3: a shield on the last living monster is cancelled.
        // Enforced here as well as on the tick so it cannot outlive the
        // pack by an update.
        Creature* owner = state->member ? PackLeaderOf(elite) : elite;
        if (!owner || PackMembers(owner, *pack).size() <= 1)
            pack->shieldUntil = 0;
        else
        {
            damage = 0;             // "completely immune to all damage" for 5 s
            return true;
        }
    }
    return false;
}

void ShieldingDeath(Creature* elite, Creature* leader, EliteState* pack)
{
    if (PackMembers(leader, *pack).size() <= 1 || pack->shieldHolder == elite->GetGUID())
    {
        if (Creature* bearer = elite->GetMap()->GetCreature(pack->shieldHolder))
            SetShieldImmunity(bearer, bearer->CustomData.Get<EliteState>("DCRiftElite"), false);
        pack->shieldUntil = 0;
        pack->shieldHolder.Clear();
    }
}

void SetShieldImmunity(Creature* creature, EliteState* state, bool active)
{
    if (!creature || !state || state->shieldApplied == active)
        return;
    state->shieldApplied = active;
    uint32 const spell = AffixShell(*state, "shielding");
    // Distinct spell ownership preserves Juggernaut's permanent immunities.
    creature->ApplySpellImmune(spell, IMMUNITY_DAMAGE, SPELL_SCHOOL_MASK_ALL, active);
    creature->ApplySpellImmune(spell, IMMUNITY_SCHOOL, SPELL_SCHOOL_MASK_ALL, active);
}
}
