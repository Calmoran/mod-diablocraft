#include "dc_barbarian_earthquake.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>

namespace DC::Combat::Abilities::Earthquake
{
    using namespace Shared;

    void OnCast(Player* p, Row const* r, Row const* b, Position const* center)
    {
        if (Rune(*r, "Cave-In"))
            for (auto target : Nearby(p, p, Numbers::Num(r->id, "radius_yards")))
                Pull(target, p->GetPosition());
        ZoneStart(p, *r, *center, Numbers::Num(b->id, "dot_duration_seconds"), Numbers::Num(b->id, "radius_yards"));
    }

    bool KeepsSheetDamage(std::string const& skill, std::string const& rune)
    {
        return skill == "Earthquake" && rune == "Giant's Stride";
    }

    bool DamageOverTime(std::string const& skill)
    {
        return skill == "Earthquake";
    }

    bool LaunchesNoHit(std::string const& skill)
    {
        return skill == "Earthquake";
    }
} // namespace DC::Combat::Abilities::Earthquake
