// Constant (21): First campaign phase identifier; Reserved phase namespace boundary; coordinate any future schema change.
// Constant (876): Spawn-filter test: GM Island area; AreaCommands::Test GM fixture only; not production placement or balance.
// Constant (448): Spawn-filter test: Creature fixture entry; AreaCommands::Test GM fixture only; not production placement or balance.
// Constant (-8949): Spawn-filter test: Closed-map X; AreaCommands::Test GM fixture only; not production placement or balance.
// Constant (-132): Spawn-filter test: Closed-map Y; AreaCommands::Test GM fixture only; not production placement or balance.
// Constant (83): Spawn-filter test: Closed-map Z; AreaCommands::Test GM fixture only; not production placement or balance.
// Constant (16224.4f): Spawn-filter test: GM Island X; AreaCommands::Test GM fixture only; not production placement or balance.
// Constant (16253.9f): Spawn-filter test: GM Island Y; AreaCommands::Test GM fixture only; not production placement or balance.
// Constant (12.8727f): Spawn-filter test: GM Island Z; AreaCommands::Test GM fixture only; not production placement or balance.
// Constant (33): Spawn-filter test: Instance map ID; AreaCommands::Test GM fixture only; not production placement or balance.
// Constant (101766): Spawn-filter test: Object/transport fixture entry; AreaCommands::Test GM fixture only; not production placement or balance.
#include "dc_world_areas.h"
#include "dc_tiers.h"
#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "GameObject.h"
#include "GridTerrainData.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ScriptMgr.h"
#include "Transport.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <map>
#include <set>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace DC::Areas
{
namespace
{
struct Rule { uint32 area = 0; std::string scope; bool open = false; };
std::map<uint32,std::vector<Rule>> rules;
std::unordered_map<uint64,uint32> spawnPhases;
std::array<std::atomic<uint64>,6> denied{}, allowed{};
bool ready = false;
thread_local unsigned ownPlacements = 0;
uint64 Key(char kind,uint32 guid) { return (uint64(kind=='g') << 32) | guid; }

class AreaWorld final : public WorldScript
{
public:
    AreaWorld() : WorldScript("dc_world_areas", {WORLDHOOK_ON_LOAD_CUSTOM_DATABASE_TABLE,WORLDHOOK_ON_STARTUP}) { }
    void OnLoadCustomDatabaseTable() override
    {
        try
        {
            auto rows=WorldDatabase.Query("SELECT map_id,area_id,phase_scope,status FROM dc_world_areas");
            if (!rows) throw std::runtime_error("Area allow-list missing or empty");
            std::set<std::pair<uint32,uint32>> seen;
            do
            {
                auto* f=rows->Fetch();
                auto map=f[0].Get<int64>(), area=f[1].Get<int64>();
                auto scope=f[2].Get<std::string>(), status=f[3].Get<std::string>();
                if (map<0 || map>UINT32_MAX || area<0 || area>UINT32_MAX ||
                    (scope!="all" && scope!="tier" && scope!="campaign") || (status!="open" && status!="closed") ||
                    !seen.emplace(uint32(map),uint32(area)).second)
                    throw std::runtime_error("Invalid or duplicate area rule");
                rules[uint32(map)].push_back({uint32(area),scope,status=="open"});
            } while(rows->NextRow());
            if (!WorldDatabase.Query("SELECT COUNT(*) FROM dc_area_source") || !WorldDatabase.Query("SELECT COUNT(*) FROM dc_area_spawn"))
                throw std::runtime_error("Area ownership migration missing");
            rows=WorldDatabase.Query("SELECT kind,source_guid,CAST(1 AS UNSIGNED) AS phase FROM dc_area_source UNION ALL SELECT kind,spawn_guid,CAST(tier AS UNSIGNED) FROM dc_area_spawn");
            if(rows) do
            {
                auto* f=rows->Fetch();
                uint64 phase=f[2].Get<uint64>();
                if(phase<1 || phase>LaunchTierCount()) throw std::runtime_error("Area copy tier outside launch range");
                auto kind=f[0].Get<std::string>();
                if(kind!="c" && kind!="g") throw std::runtime_error("Unknown area spawn kind");
                if (!spawnPhases.emplace(Key(kind[0],f[1].Get<uint32>()),uint32(phase)).second)
                    throw std::runtime_error("Duplicate source/copy ownership");
            } while(rows->NextRow());
            ready=true;
            LOG_INFO("server.loading","[DC areas] Loaded {} area rules; {} source/copy phases; unlisted open-world areas denied",seen.size(),spawnPhases.size());
        }
        catch(std::exception const& error) { LOG_ERROR("server","[DC areas] FAIL CLOSED: {}",error.what()); }
    }
    void OnStartup() override
    {
        for(unsigned i=0;i<denied.size();++i)
            LOG_INFO("server.loading","[DC areas] startup kind={} allowed={} denied={}",i,allowed[i].load(),denied[i].load());
    }
};

class AreaFilter final : public GlobalScript
{
public:
    AreaFilter() : GlobalScript("dc_area_spawn_filter",{GLOBALHOOK_CAN_WORLD_OBJECT_SPAWN}) { }
    bool CanWorldObjectSpawn(WorldSpawnKind kind,uint32,uint32,uint32 mapId,uint32 phase,Position const& position) override
    {
        auto index=static_cast<unsigned>(kind);
        auto* mapEntry=sMapStore.LookupEntry(mapId);
        if(mapEntry && mapEntry->Instanceable()) return true;
        bool permit=ownPlacements>0;
        if(!permit && ready && mapEntry)
        {
            auto found=rules.find(mapId);
            if(found!=rules.end() && std::any_of(found->second.begin(),found->second.end(),[](Rule const& rule){return rule.open;}))
            {
                // Resolves WMO overrides as well as outdoor terrain. Never trust
                // a database areaId, which is often zero on valid stock spawns.
                Map* map=sMapMgr->CreateBaseMap(mapId);
                permit=IsOpen(mapId,map->GetAreaId(phase,position.GetPositionX(),position.GetPositionY(),position.GetPositionZ()),phase);
            }
        }
        (permit?allowed[index]:denied[index]).fetch_add(1,std::memory_order_relaxed);
        return permit;
    }
};

class AreaCommands final : public CommandScript
{
public:
    AreaCommands() : CommandScript("dc_area_commands") { }
    Acore::ChatCommands::ChatCommandTable GetCommands() const override
    {
        using namespace Acore::ChatCommands;
        static ChatCommandTable commands={{"scan",Scan,SEC_ADMINISTRATOR,Console::Yes},{"audit",Audit,SEC_ADMINISTRATOR,Console::Yes},{"test",Test,SEC_ADMINISTRATOR,Console::Yes}};
        static ChatCommandTable dc={{"areas",commands}};
        static ChatCommandTable root={{"dc",dc}};
        return root;
    }
    static bool Audit(ChatHandler* handler)
    {
        for(unsigned i=0;i<denied.size();++i)
            handler->PSendSysMessage("Area filter kind {}: allowed {}, denied {}.",i,allowed[i].load(),denied[i].load());
        return true;
    }
    static bool Test(ChatHandler* handler)
    {
        if (!ready || !IsOpen(1,876,1) || rules.count(0))
        {
            handler->SendSysMessage("This smoke test requires the initial GM Island-only allow-list.");
            return false;
        }
        bool passed=true;
        for (unsigned i=0;i<6;++i)
        {
            auto kind=static_cast<WorldSpawnKind>(i);
            passed &= !sScriptMgr->CanWorldObjectSpawn(kind,448,0,0,1,Position(-8949,-132,83,0));
            passed &= sScriptMgr->CanWorldObjectSpawn(kind,448,0,1,10,Position(16224.4f,16253.9f,12.8727f,0));
            passed &= sScriptMgr->CanWorldObjectSpawn(kind,448,0,33,1,Position(0,0,0,0));
        }
        // Exercise actual early failure/cleanup, without adding objects to a map.
        // Both creature entry and object entry exist in the stock world database.
        Map* closed=sMapMgr->CreateBaseMap(0);
        {
            Creature creature;
            passed &= !creature.Create(1,closed,1,448,0,-8949,-132,83,0);
        }
        {
            Creature vehicle;
            passed &= !vehicle.Create(1,closed,1,448,1,-8949,-132,83,0);
        }
        {
            GameObject object;
            passed &= !object.Create(1,101766,closed,1,-8949,-132,83,0,G3D::Quat(0,0,0,1),0,GO_STATE_READY);
        }
        {
            StaticTransport transport;
            passed &= !transport.Create(1,101766,closed,1,-8949,-132,83,0,G3D::Quat(0,0,0,1),0,GO_STATE_READY);
        }
        handler->PSendSysMessage("Area smoke test: {} (six kinds, open/closed/instance policy; four real creation vetoes).",passed?"PASS":"FAIL");
        LOG_INFO("server.loading","[DC areas] smoke test {}",passed?"PASS":"FAIL");
        return passed;
    }
    static bool Scan(ChatHandler* handler,uint32 mapId,uint32 areaId)
    {
        // Three different failures used to share one message that read like a
        // closed area, which sent us looking for the wrong thing.
        if(!ready) { handler->SendSysMessage("Area scan is unavailable: the area subsystem is not ready yet."); return false; }
        if(!mapId || !areaId) { handler->SendSysMessage("Usage: .dc areas scan <map id> <area id>."); return false; }
        if(!IsOpen(mapId,areaId,1)) { handler->PSendSysMessage("Map {} area {} is not an open area that includes launch tiers.",mapId,areaId); return false; }
        auto* mapEntry=sMapStore.LookupEntry(mapId);
        auto* area=sAreaTableStore.LookupEntry(areaId);
        if(!mapEntry || mapEntry->Instanceable() || !area || area->mapid!=mapId) return false;
        bool wmoArea=false;
        for(uint32 i=0;i<sWMOAreaTableStore.GetNumRows();++i)
            if(auto* wmo=sWMOAreaTableStore.LookupEntry(i)) if(wmo->areaId==areaId) { wmoArea=true; break; }
        Map* map=sMapMgr->CreateBaseMap(mapId);
        auto transaction=WorldDatabase.BeginTransaction();
        transaction->Append("DELETE FROM dc_area_source WHERE map_id={} AND area_id={}",mapId,areaId);
        unsigned count=0;
        for(auto const& [kind,table]:{std::pair{"c","creature"},std::pair{"g","gameobject"}})
        {
            // MySQL's text protocol shortens FLOAT output. Cast to DOUBLE so the
            // exact stored float survives reading, area resolution and snapshotting.
            auto rows=WorldDatabase.Query("SELECT s.guid,s.id,s.phaseMask,CAST(s.position_x AS DOUBLE),CAST(s.position_y AS DOUBLE),"
                "CAST(s.position_z AS DOUBLE),CAST(s.orientation AS DOUBLE) FROM {} s "
                "LEFT JOIN dc_area_spawn copy ON copy.kind='{}' AND copy.spawn_guid=s.guid "
                "WHERE s.map={} AND (s.phaseMask&1)<>0 AND copy.spawn_guid IS NULL",table,kind,mapId);
            if(!rows) continue;
            do
            {
                auto* f=rows->Fetch();
                float x=float(f[3].Get<double>()),y=float(f[4].Get<double>()),z=float(f[5].Get<double>()),o=float(f[6].Get<double>());
                // Terrain-only prefilter avoids loading collision geometry across
                // a whole continent when opening an outdoor area. WMO areas are
                // checked at every source position so an indoor area isn't missed.
                auto* terrain=map->GetGridTerrainData(x,y);
                uint32 outdoor=terrain?terrain->getArea(x,y):0;
                if(!wmoArea && outdoor!=areaId && (!area->zone || outdoor!=area->zone)) continue;
                if(map->GetAreaId(1,x,y,z)!=areaId) continue;
                transaction->Append("INSERT INTO dc_area_source VALUES ({},{},'{}',{},{},{},{},{},{},{})",
                    mapId,areaId,kind,f[0].Get<uint32>(),f[1].Get<uint32>(),f[2].Get<uint32>(),x,y,z,o);
                ++count;
            } while(rows->NextRow());
        }
        WorldDatabase.DirectCommitTransaction(transaction);
        handler->PSendSysMessage("Area {}:{} snapshot: {} sources. Run generate_area_copies.py while worldserver is stopped, then restart.",mapId,areaId,count);
        LOG_INFO("server.loading","[DC areas] scanned map={} area={} sources={}",mapId,areaId,count);
        return true;
    }
};
}
bool Ready() { return ready; }
bool IsOpen(uint32 map,uint32 area,uint32 phase)
{
    if(!ready) return false;
    auto found=rules.find(map);
    if(found==rules.end()) return false;
    for(auto const& rule:found->second) if(rule.area==area)
        return rule.open && (rule.scope=="all" || (rule.scope=="tier" && phase>=1 && phase<=LaunchTierCount()) || (rule.scope=="campaign" && phase>=21));
    return false;
}
uint32 SpawnPhase(WorldObject const* object,uint32 requested)
{
    uint64 key;
    if(auto* c=object->ToCreature()) key=Key('c',c->GetSpawnId());
    else if(auto* g=object->ToGameObject()) key=Key('g',g->GetSpawnId());
    else return requested;
    auto found=spawnPhases.find(key);
    return found==spawnPhases.end()?requested:found->second;
}
OwnPlacement::OwnPlacement() { ++ownPlacements; }
OwnPlacement::~OwnPlacement() { --ownPlacements; }
void RegisterScripts() { new AreaWorld(); new AreaFilter(); new AreaCommands(); }
}
