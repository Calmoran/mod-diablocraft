// World of DiabloCraft - the Juggernaut elite affix: slower, immune to crowd control, takes more damage.

#include "dc_affix_internal.h"

#include "Creature.h"
#include "SpellAuraDefines.h"

#include <cmath>
#include <cstdint>

namespace DC::Rifts
{
// `damage` is the exact hit (the exact-hit hook runs before any 32-bit consumer). The multiplier is the sheet's percent as a
// whole-number ratio and the product is LifeMulDiv's 128-bit one, so a hit past 3.3 billion neither wraps nor loses digits to a
// double, and one the product cannot hold saturates at 2^64 - 1.
void JuggernautStruck(EliteState const* state, AffixNumbers const& n, std::uint64_t& damage)
{
    // Blizzard 2.4.3 says a Juggernaut takes 30% MORE damage.
    // Ours multiplied by 0.70, which made it about twice as tanky as D3's.
    constexpr std::uint64_t scale = 1000000000;
    if (HasAffix(*state, "juggernaut") && n.Enabled("Juggernaut"))
        damage = LifeMulDiv(damage, static_cast<std::uint64_t>(std::llround(n.juggernautTaken * scale)), scale);
}

void SetJuggernautImmunities(Creature* elite, bool on)
{
    for (uint32 mechanic : {MECHANIC_CHARM, MECHANIC_DISORIENTED, MECHANIC_FEAR, MECHANIC_ROOT, MECHANIC_SLEEP, MECHANIC_SNARE,
                            MECHANIC_STUN, MECHANIC_FREEZE, MECHANIC_KNOCKOUT, MECHANIC_HORROR, MECHANIC_DAZE, MECHANIC_SAPPED,
                            MECHANIC_POLYMORPH, MECHANIC_BANISH})
        elite->ApplySpellImmune(0, IMMUNITY_MECHANIC, mechanic, on);
    elite->ApplySpellImmune(0, IMMUNITY_EFFECT, SPELL_EFFECT_KNOCK_BACK, on);
    elite->ApplySpellImmune(0, IMMUNITY_EFFECT, SPELL_EFFECT_KNOCK_BACK_DEST, on);
}

void JuggernautPassive(Creature* elite, EliteState const& state, AffixNumbers const& n)
{
    if (HasAffix(state, "juggernaut") && n.Enabled("Juggernaut"))
    {
        AddPace(elite, n.juggernautMove, 1.0);
        // No source gives Juggernaut a health bonus, so health_bonus
        // is 0 and this does nothing. It stays a multiplier rather than being
        // deleted, so one can be put back with `.dc affix set`.
        if (n.juggernautLife != 1.0)
            ScaleLife(elite, n.juggernautLife);
        // "permanently immune to all crowd control effects" - Blizzard 2.4.3.
        if (n.Parameter("Juggernaut|crowd_control_immune") > 0.0 && !state.juggernautPurged)
            SetJuggernautImmunities(elite, true);
    }
}
}
