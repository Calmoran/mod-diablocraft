#include "dc_barbarian_sprint.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>

namespace DC::Combat::Abilities::Sprint
{
    using namespace Shared;

    void OnRefresh(Player* p)
    {
        if (auto r = Buff(p, "Sprint"))
        {
            auto b = Base("Sprint");
            Add(p, AuraId(r->id), Stat::MovementSpeed, Rune(*r, "Marathon") ? Numbers::Num(r->id, "movement_speed_pct") : Numbers::Num(b->id, "movement_speed_pct"), Bucket::Uncapped);
            // Dodge is applied in the incoming melee/spell path, outside the stat enum.
        }
    }

    void OnRefreshAllied(Player* p)
    {
        if (auto r = Buff(p, "Sprint");
            r && Rune(*r, "Forced March") && p->GetAura(AuraId(r->id))->GetCasterGUID() != p->GetGUID())
            Add(p, AuraId(r->id), Stat::MovementSpeed, Numbers::Num(r->id, "movement_speed_pct"), Bucket::Uncapped);
    }

    void OnDodge(Player const* p, double& chance)
    {
        if (auto r = Buff(p, "Sprint"); r && Rune(*r, "Rush"))
            chance += Numbers::Num(r->id, "dodge_pct");
    }

    void OnCast(Player* p, Row const* r, Row const* b)
    {
        double duration = 0;
        duration = Rune(*r, "Marathon") ? Numbers::Num(r->id, "duration_seconds") : Numbers::Num(b->id, "duration_seconds");
        Mark(p, p, *r, duration);
        if (Rune(*r, "Forced March"))
            for (auto u : Nearby(p, p, Numbers::Num(r->id, "radius_yards"), true))
                if (u != p)
                {
                    Mark(p, u, *r, Numbers::Num(r->id, "duration_seconds"));
                    if (auto ally = u->ToPlayer())
                        Refresh(ally);
                }
    }

    void OnUpdate(Player* p, State& s, uint32 diff)
    {
        if (auto sprint = Buff(p, "Sprint"); sprint && Rune(*sprint, "Run Like the Wind"))
        {
            double interval = Tune("sprint_tornado_interval_seconds");
            s.tornadoClock += diff;
            if (interval > 0 && s.tornadoClock >= interval * 1000 && p->isMoving())
            {
                s.tornadoClock = std::fmod(s.tornadoClock, interval * 1000);
                ZoneStart(p, *sprint, p->GetPosition(), Numbers::Num(sprint->id, "duration_seconds"), Tune("sprint_tornado_radius_yards"));
            }
        }
        else
            s.tornadoClock = 0;
    }
} // namespace DC::Combat::Abilities::Sprint
