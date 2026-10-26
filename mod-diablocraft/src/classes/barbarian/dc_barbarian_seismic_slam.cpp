#include "dc_barbarian_seismic_slam.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>

namespace DC::Combat::Abilities::SeismicSlam
{
    using namespace Shared;

    void OnCast(Player* p, uint32 id, Row const* r, std::vector<Unit*> const& targets, Position const* center, double extraDamage, State& s)
    {
        if (Rune(*r, "Strength from Earth"))
            Heal(p, p, id, p->GetMaxHealth() * Numbers::Num(r->id, "heal_pct") / 100 * targets.size());
        if (Rune(*r, "Rumble") && center && extraDamage > 0)
        {
            ZoneStart(p, *r, *center, Numbers::Num(r->id, "dot_duration_seconds"), r->radius, extraDamage);
            auto& zone = s.zones.back();
            for (auto u : targets)
                zone.selected.push_back(u->GetGUID());
        }
    }

    void OnHit(Player* p, Unit* target, Row const* r)
    {
        if (Rune(*r, "Permafrost"))
            Control(p, target, *r, Numbers::Num(r->id, "chill_duration_seconds"));
    }

    bool KeepsSheetDamage(std::string const& skill, std::string const& rune)
    {
        return skill == "Seismic Slam" && rune == "Rumble";
    }

    bool SpendsEveryPoint(std::string const& skill, std::string const& rune)
    {
        return skill == "Seismic Slam" && rune == "Rumble";
    }

    void OnBegin(std::string const& skill, std::string const& rune, uint32 id, double fury, double cost, double& extraDamage)
    {
        if(skill=="Seismic Slam"&&rune=="Rumble")extraDamage=std::max(0.0,fury-cost)*Numbers::Num(id, "damage_pct");
    }
} // namespace DC::Combat::Abilities::SeismicSlam
