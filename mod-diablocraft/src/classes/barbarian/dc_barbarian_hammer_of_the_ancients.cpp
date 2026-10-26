#include "dc_barbarian_hammer_of_the_ancients.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_item_powers.h"

namespace DC::Combat::Abilities::Hammer
{
    using namespace Shared;

    void OnHit(Player* p, Unit* target, Row const* r)
    {
        if (Rune(*r, "The Devil's Anvil"))
            ZoneStart(p, *r, target->GetPosition(), Numbers::Num(r->id, "duration_seconds"), Tune("devils_anvil_radius_yards"), 0, true);
        if (Rune(*r, "Thunderstrike") && !target->IsAlive())
            for (auto u : Nearby(p, target, Numbers::Num(r->id, "radius_yards")))
                Control(p, u, *r, Numbers::Num(r->id, "stun_duration_seconds") * ItemPowers::StunFactor(p));
    }

    void OnCritical(Player* p, uint32 spellId)
    {
        if (auto r = Shells::FindAbility(spellId);
            r && std::string(r->skill) == "Hammer of the Ancients" && Rune(*r, "Birthright"))
            Heal(p, p, spellId, p->GetMaxHealth() * Numbers::Num(r->id, "heal_pct") / 100);
    }

    double OnCritBonus(std::string const& skill, double fury)
    {
        double skillCrit=0;
        if(skill=="Hammer of the Ancients") {auto mechanics=Shells::FindAbility(81007);if(mechanics)skillCrit=fury/Numbers::Num(mechanics->id, "per_trigger_resource")*Numbers::Num(mechanics->id, "crit_chance_pct");}
        return skillCrit;
    }
} // namespace DC::Combat::Abilities::Hammer
