// World of DiabloCraft - what a skill that purges takes off an elite: the affixes' empowered states (Shielding,
// Reflects Damage, Juggernaut, Illusionist).

#include "dc_affix_internal.h"
#include "../../rifts/dc_rifts.h"

#include "Creature.h"
#include "Map.h"
#include "Timer.h"

namespace DC::Rifts
{
    unsigned PurgeEmpowered(Creature* creature)
    {
        if (!creature || !creature->IsAlive())
            return 0;
        EliteState* const state = creature->CustomData.Get<EliteState>("DCRiftElite");
        if (!state)
            return 0;
        EliteState* const pack = PackStateOf(creature, state);
        std::uint32_t const now = getMSTime();
        unsigned removed = 0;

        // Shielding: the window this monster holds ends now; the next one comes at the affix's own cadence.
        if (HasAffix(*state, "shielding") && pack->shieldHolder == creature->GetGUID() && now < pack->shieldUntil)
        {
            pack->shieldUntil = 0;
            SetShieldImmunity(creature, state, false);
            ++removed;
        }

        // Reflects Damage: only a window that is reflecting now (its warning is over) is an empowered state; it ends,
        // and the affix arms a new one with its warning as it always does.
        if (HasAffix(*state, "reflects_damage") && pack->reflectHolder == creature->GetGUID() &&
            now >= pack->reflectFrom && now < pack->reflectUntil)
        {
            pack->reflectUntil = now;
            ++removed;
        }

        // Juggernaut: the immunity to crowd control and knockback comes off for good.
        if (HasAffix(*state, "juggernaut") && !state->juggernautPurged)
        {
            std::shared_ptr<AffixNumbers const> const numbers = Numbers();
            if (numbers && numbers->Parameter("Juggernaut|crowd_control_immune") > 0.0)
            {
                state->juggernautPurged = true;
                SetJuggernautImmunities(creature, false);
                ++removed;
            }
        }

        // Illusionist: the copies standing now are dismissed (it makes new ones the next time it is hurt, as it always
        // does).
        if (HasAffix(*state, "illusionist"))
        {
            bool dismissed = false;
            Map* const map = creature->GetMap();
            for (ObjectGuid const& guid : state->illusions)
                if (Creature* copy = map ? map->GetCreature(guid) : nullptr)
                    if (copy->IsAlive())
                    {
                        copy->DespawnOrUnsummon();
                        dismissed = true;
                    }
            state->illusions.clear();
            removed += dismissed;
        }
        return removed;
    }
} // namespace DC::Rifts
