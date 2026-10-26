#include "dc_barbarian_battle_rage.h"
#include "../dc_level_heal.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "Pet.h"
#include "Timer.h"
#include "dc_barbarian_call_of_the_ancients.h"

namespace DC::Combat::Abilities::BattleRage
{
    using namespace Shared;

    void OnDamageBonus(Player* p, double& result)
    {
        if (auto r = Buff(p, "Battle Rage"))
            result += Rune(*r, "Marauder's Rage") ? Numbers::Num(r->id, "damage_pct") : Numbers::Num(Base("Battle Rage")->id, "damage_bonus_pct");
    }

    void OnRefresh(Player* p, std::size_t& frayEnemies)
    {
        if (auto r = Buff(p, "Battle Rage"))
        {
            Add(p, AuraId(r->id), Stat::CritChance, Numbers::Num(Base("Battle Rage")->id, "crit_chance_pct"));
            if (Rune(*r, "Ferocity"))
                Add(p, AuraId(r->id), Stat::MovementSpeed, Numbers::Num(r->id, "movement_speed_pct"), Bucket::Uncapped);
            if (Rune(*r, "Into the Fray"))
            {
                frayEnemies = Nearby(p, p, Numbers::Num(r->id, "radius_yards")).size();
                Add(p, AuraId(r->id), Stat::CritChance,
                    Numbers::Num(Base("Battle Rage")->id, "crit_chance_pct")
                        + Numbers::Num(r->id, "crit_chance_pct") * frayEnemies);
            }
        }
    }

    void OnCast(Player* p, uint32 id, Row const* r, Row const* b)
    {
        double duration = 0;
        duration = Combat::ModifiedDurationSeconds(p, id, Numbers::Num(b->id, "duration_seconds"));
        Mark(p, p, *r, duration);
    }

    void OnCritical(Player* p, double damage)
    {
        if (auto r = Buff(p, "Battle Rage"))
        {
            if (Rune(*r, "Swords to Ploughshares"))
            {
                Heal(p, p, r->id, Classes::HealAtLevel(Numbers::Num(r->id, "heal_life"), p->GetLevel()));
                Classes::Ancients::HealAll(p, r->id, Classes::HealAtLevel(Numbers::Num(r->id, "heal_life"), p->GetLevel()));
                if (auto pet = p->GetPet())
                    Heal(p, pet, r->id, Classes::HealAtLevel(Numbers::Num(r->id, "heal_life"), p->GetLevel()));
            }
            if (Rune(*r, "Bloodshed"))
                states[p->GetGUID().GetRawValue()].criticals.emplace_back(getMSTime(), damage);
        }
    }

    void OnUpdate(Player* p, State& s, uint32 diff)
    {
        if (auto buff = Buff(p, "Battle Rage"); buff && Rune(*buff, "Bloodshed"))
        {
            s.bloodshedClock += diff;
            if (s.bloodshedClock >= Numbers::Num(buff->id, "interval_seconds") * 1000)
            {
                s.bloodshedClock = std::fmod(s.bloodshedClock, Numbers::Num(buff->id, "interval_seconds") * 1000);
                double window = Tune("battle_rage_recent_crit_window_seconds");
                std::erase_if(s.criticals, [window](auto const& hit)
                              { return window <= 0 || getMSTimeDiff(hit.first, getMSTime()) > window * 1000; });
                Hit h;
                h.school = SPELL_SCHOOL_MASK_NORMAL;
                for (auto const& hit : s.criticals)
                    h.total += hit.second * Numbers::Num(buff->id, "damage_bonus_pct") / 100;
                for (auto u : Nearby(p, p, Numbers::Num(buff->id, "radius_yards")))
                    DealHit(p, u, buff->id, h);
            }
        }
        else
        {
            s.criticals.clear();
            s.bloodshedClock = 0;
        }
    }

    void OnSignature(Player* p, uint64& signature)
    {
        auto fray = Buff(p, "Battle Rage");
        if (fray && Rune(*fray, "Into the Fray"))
            signature = signature * 131 + Nearby(p, p, Numbers::Num(fray->id, "radius_yards")).size();
    }
} // namespace DC::Combat::Abilities::BattleRage
