#include "dc_barbarian_whirlwind.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "Unit.h"
#include <cmath>
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_passives.h"
#include "Spell.h"
#include "SpellMgr.h"

namespace DC::Combat::Abilities::Whirlwind
{
    using namespace Shared;

    void OnUpdate(Player* p, State& s, uint32 diff)
    {
        if (s.whirlwind)
        {
            auto current=p->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
            auto row=Shells::FindAbility(s.whirlwind);
            if(!current || current->GetSpellInfo()->Id!=s.whirlwind || !row)
                StopWhirlwind(p);
            else
            {
                // D3's own cadence:
                // floor(40 frames / attacks per second) of 60 for the
                // hand about to swing, which retired the
                // whirlwind_tick_interval_seconds tunable - it was still
                // a 0 placeholder, so the channel had never ticked at
                // all. Dual wielding alternates the hands and each tick
                // costs and lands on its own hand's speed; one weapon is
                // always the main hand. Read every update, so an
                // attack-speed change moves the next tick; a sheet that
                // cannot answer still disables the ticks rather than
                // guessing one.
                double interval=WhirlwindTickSeconds(p,row->id,s.whirlwindOffhand);
                s.whirlwindClock+=diff;
                while(interval>0 && s.whirlwind && s.whirlwindClock>=interval*1000)
                {
                    s.whirlwindClock-=interval*1000;
                    bool const hand=s.whirlwindOffhand;
                    if(!PayWhirlwindTick(p,row->id,hand)) {StopWhirlwind(p);break;}
                    // The next tick is the other hand's, and its own
                    // speed sets both what it costs and when it lands.
                    s.whirlwindOffhand=DualWielding(p) && !hand;
                    interval=WhirlwindTickSeconds(p,row->id,s.whirlwindOffhand);
                    if(Rune(*row,"Hurricane"))
                        for(auto target:Nearby(p,p,Numbers::Num(row->id, "radius_yards"))) Pull(target,p->GetPosition());
                    bool connected=false;
                    for(auto target:Nearby(p,p,row->radius))
                    {
                        auto info=sSpellMgr->GetSpellInfo(row->id);
                        if(!info || target->IsImmunedToDamage(p,info))continue;
                        Hit hit;
                        if(!ComputeHit(p,target,row->id,hit))continue;
                        DealHit(p,target,row->id,hit);
                        if(hit.total<=0)continue;
                        connected=true;
                        Passives::Hit(p,target,row->id,hit.school);
                        if(Rune(*row,"Wind Shear")) Fury(p,Numbers::Num(row->id, "gain_resource"));
                        if(hit.critical)
                        {
                            CriticalHit(p,target,row->id,hit.total);
                            if(Rune(*row,"Blood Funnel")) Heal(p,p,row->id,p->GetMaxHealth()*Numbers::Num(row->id, "heal_pct")/100);
                        }
                        if(hit.areaDamage>0)
                        {
                            Hit splash=hit;splash.total=hit.areaDamage;splash.areaDamage=0;splash.critical=false;
                            for(auto nearby:Nearby(p,target,10))if(nearby!=target)DealHit(p,nearby,row->id,splash);
                        }
                    }
                    if(connected)Connected(p,row->id);
                    if(auto devils=s.whirlwind ? RuneRow(p,*row,"Dust Devils") : nullptr)
                    {
                        auto period=Tune("whirlwind_dust_interval_seconds");
                        s.devilClock+=interval*1000;
                        while(period>0 && s.devilClock>=period*1000)
                        {
                            s.devilClock-=period*1000;
                            Hit hit;
                            if(ComputeHit(p,nullptr,row->id,hit) && hit.skill>0)
                            {
                                hit.total*=Numbers::Num(devils->id, "damage_pct")/(hit.skill*100);hit.skill=Numbers::Num(devils->id, "damage_pct")/100;
                                hit.areaDamage=0;
                                s.devils.push_back({p->GetPosition(),p->GetOrientation(),0,devils->id,hit,{}});
                            }
                        }
                    }
                }

            }
        }
        for(auto& devil:s.devils)
        {
            auto life=Tune("whirlwind_dust_lifetime_seconds");
            auto speed=Tune("whirlwind_dust_speed_yards_per_second");
            auto radius=Tune("whirlwind_dust_radius_yards");
            auto elapsed=std::min(double(diff)/1000,std::max(0.0,life-devil.elapsed));
            devil.elapsed+=elapsed;
            if(life<=0 || speed<=0 || radius<=0)continue;
            Position previous=devil.center;
            devil.center.Relocate(previous.GetPositionX()+std::cos(devil.direction)*speed*elapsed,
                                  previous.GetPositionY()+std::sin(devil.direction)*speed*elapsed,
                                  previous.GetPositionZ());
            if(!p->IsWithinLOS(devil.center.GetPositionX(),devil.center.GetPositionY(),devil.center.GetPositionZ()))
                {devil.elapsed=life;continue;}
            Position middle=previous;
            middle.Relocate((previous.GetPositionX()+devil.center.GetPositionX())/2,
                            (previous.GetPositionY()+devil.center.GetPositionY())/2,previous.GetPositionZ());
            auto length=speed*elapsed;
            for(auto target:At(p,middle,radius+length/2))
            {
                auto dx=target->GetPositionX()-previous.GetPositionX();
                auto dy=target->GetPositionY()-previous.GetPositionY();
                auto along=std::clamp(dx*std::cos(devil.direction)+dy*std::sin(devil.direction),0.0,length);
                auto distance=std::hypot(dx-along*std::cos(devil.direction),dy-along*std::sin(devil.direction));
                if(distance>radius || std::find(devil.hit.begin(),devil.hit.end(),target->GetGUID())!=devil.hit.end())continue;
                auto info=sSpellMgr->GetSpellInfo(devil.spell);
                if(!info || target->IsImmunedToDamage(p,info))continue;
                devil.hit.push_back(target->GetGUID());
                DealHit(p,target,devil.spell,devil.snapshot);
            }
        }
        std::erase_if(s.devils,[](auto const& devil){return devil.elapsed>=Tune("whirlwind_dust_lifetime_seconds");});
    }

    bool PaysByTick(std::string const& skill)
    {
        return skill == "Whirlwind";
    }

    bool KeepsSheetDamage(std::string const& skill, std::string const& rune)
    {
        return skill == "Whirlwind" && rune == "Dust Devils";
    }

    bool OnToggle(Player* p, uint32 id)
    {
        auto row = Shells::FindAbility(id);
        if (row && std::string(row->skill)=="Whirlwind" && WhirlwindActive(p))
        {
            StopWhirlwind(p);
            return true;
        }
        return false;
    }
} // namespace DC::Combat::Abilities::Whirlwind

namespace DC::Combat::Abilities
{
    using namespace Shared;

    bool WhirlwindActive(Player* p)
    {
        auto current=p ? p->GetCurrentSpell(CURRENT_CHANNELED_SPELL) : nullptr;
        auto row=current ? Shells::FindAbility(current->GetSpellInfo()->Id) : nullptr;
        return row && std::string(row->skill)=="Whirlwind";
    }
    void StopWhirlwind(Player* p)
    {
        if (!p) return;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        auto found=states.find(p->GetGUID().GetRawValue());
        // The channel's one swing starts when it ends, and
        // only if it was running: this is also called on death, a map change and a logout.
        uint32 const ended = found!=states.end() ? found->second.whirlwind : 0;
        if(found!=states.end()) {found->second.whirlwind=0;found->second.whirlwindClock=0;found->second.devilClock=0;found->second.whirlwindOffhand=false;}
        if(ended) ItemPowers::ChannelEnded(p,"Whirlwind");
        if (WhirlwindActive(p)) p->InterruptSpell(CURRENT_CHANNELED_SPELL);
        if (ended && p->IsAlive()) StartSwingRecovery(p, ended);
    }
    void StartWhirlwind(Player* p, uint32 id)
    {
        auto row=Shells::FindAbility(id);
        if (!p || !row || std::string(row->skill)!="Whirlwind") return;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        auto& state=states[p->GetGUID().GetRawValue()];
        state.whirlwind=id;state.whirlwindClock=state.devilClock=0;state.whirlwindOffhand=false;
        ItemPowers::ChannelStarted(p,"Whirlwind");
    }
} // namespace DC::Combat::Abilities
