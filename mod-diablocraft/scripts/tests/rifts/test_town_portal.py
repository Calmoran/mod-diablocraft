"""Compile production portal callbacks with focused map, player and spell doubles."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

from split_sources import rifts_text  # beside this file

ROOT = Path(__file__).resolve().parents[4]
SOURCE = (ROOT / 'mod-diablocraft/src/rifts/dc_town_portal.cpp').read_text(encoding='utf-8')


RIFTS = rifts_text()
AREAS = (ROOT / 'mod-diablocraft/src/common/dc_world_areas.cpp').read_text(encoding='utf-8')
# The Sanctum's one shared phase, read from production (dc_world.h), never typed here.
SANCTUM_PHASE = re.search(r'constexpr unsigned SanctumPhase = (\d+);',
                          (ROOT / 'mod-diablocraft/src/common/dc_world.h').read_text(encoding='utf-8')).group(1)


def definition(marker: str, source: str = SOURCE) -> str:
    start = source.index(marker)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end].replace(' override', '')


harness = r'''
#include <cassert>
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <vector>
using uint32=std::uint32_t; using uint64=std::uint64_t; using int32=std::int32_t;
enum DamageEffectType { DIRECT_DAMAGE };
// The production code reads its cast time through DC::Tunables; the harness answers
// the one row it asks for with the number the tunables sheet holds, and refuses any other.
namespace DC::Tunables {
 inline double Get(char const* category, char const* name) {
  assert(std::string(category)=="rifts" && std::string(name)=="town_portal_cast_ms");
  return @CAST_MS@;
 }
}
struct ObjectGuid {
 uint64 id=0;
 bool operator==(ObjectGuid const& b) const { return id==b.id; }
 bool operator!=(ObjectGuid const& b) const { return id!=b.id; }
 bool operator<(ObjectGuid const& b) const { return id<b.id; }
 explicit operator bool() const { return id!=0; }
 static ObjectGuid const Empty;
};
inline ObjectGuid const ObjectGuid::Empty{};
struct WorldLocation {
 uint32 map=0; float x=0,y=0,z=0,o=0;
 WorldLocation()=default;
 WorldLocation(uint32 m,float a,float b,float c,float d):map(m),x(a),y(b),z(c),o(d) {}
 uint32 GetMapId() const { return map; }
 float GetPositionX() const { return x; } float GetPositionY() const { return y; }
 float GetPositionZ() const { return z; } float GetOrientation() const { return o; }
};
struct Player; struct Spell;
struct Unit {
 Player* player=nullptr; Spell* cast=nullptr; unsigned interrupts=0;
 Player* ToPlayer() { return player; } bool IsPlayer() { return player!=nullptr; }
 Spell* GetCurrentSpell(int) { return cast; }
 void InterruptNonMeleeSpells(bool,uint32) { ++interrupts; cast=nullptr; }
};
// Homing Pads (diablocraft-9ebp6): the production reader answers from the item power table; the harness sets the factor its wearer would get.
namespace DC::Combat::ItemPowers { inline double bubble=1.0; inline unsigned asked=0; inline double TownPortalFactor(Player const*) { ++asked; return bubble; } }
struct SpellCastTimesEntry { int32 CastTime; };
struct SpellInfo { uint32 Id,Attributes=0,InterruptFlags=0; SpellCastTimesEntry const* CastTimeEntry=nullptr; };
struct Spell {
 SpellInfo info; Unit* caster; int state=0;
 SpellInfo const* GetSpellInfo() const { return &info; }
 Unit* GetCaster() { return caster; } int getState() { return state; }
};
struct CastTimes {
 SpellCastTimesEntry values[2]={{3000},{1500}};
 uint32 GetNumRows() { return 2; }
 SpellCastTimesEntry* LookupEntry(uint32 n) { return &values[n]; }
} sSpellCastTimesStore;
constexpr uint32 SPELL_ATTR0_NOT_IN_COMBAT_ONLY_PEACEFUL=0x10000000;
constexpr uint32 SPELL_INTERRUPT_FLAG_MOVEMENT=1,SPELL_INTERRUPT_FLAG_INTERRUPT=8,SPELL_INTERRUPT_FLAG_ABORT_ON_DMG=16;
constexpr int CURRENT_GENERIC_SPELL=0,SPELL_STATE_PREPARING=0,TELE_TO_SPELL=1,DUNGEON_DIFFICULTY_NORMAL=0;
using SpellCastResult=int; constexpr int SPELL_FAILED_NOT_HERE=1;
// ---- the gameobject, its AI and the map, as the core builds them (Create runs the script
// hook that gives the object its AI; AddToMap is when the create packet goes out and the
// visibility notifier asks that AI who may see it, Object.cpp:1839).
constexpr int GO_STATE_READY=0; constexpr uint32 OBELISK_ENTRY=910011;
namespace G3D { struct Quat { Quat(float,float,float,float) {} }; }
enum class HighGuid { GameObject };
struct GameObject;
struct GameObjectAI {
 GameObject* const me; explicit GameObjectAI(GameObject* go):me(go) {} virtual ~GameObjectAI() {}
 virtual bool CanBeSeen(Player const*) { return true; }
};
std::map<uint32,uint32> templateDisplay={{910012,4000},{910013,4001}};
struct ObjectMgrDouble { void const* GetGameObjectTemplate(uint32 e) { return templateDisplay.count(e)?&templateDisplay:nullptr; } } objectMgr;
ObjectMgrDouble* sObjectMgr=&objectMgr;
struct Map;
struct GameObject {
 ObjectGuid guid; uint32 entry=0,phase=1,display=0,spawnId=0; bool deleted=false;
 std::unique_ptr<GameObjectAI> ai; std::vector<std::string> log;
 // what the create packet carried, and who the notifier showed it to
 uint32 phaseAtAdd=0,displayAtAdd=0; std::set<uint64> seenBy; bool added=false;
 ObjectGuid GetGUID() const { return guid; } uint32 GetEntry() const { return entry; } uint32 GetSpawnId() const { return spawnId; }
 void SetPhaseMask(uint32 p,bool) { phase=p; log.push_back("phase"); } void Delete() { deleted=true; }
 void SetDisplayId(uint32 d) { display=d; log.push_back("display"); }
 void SetRespawnTime(int) {} void SetSpawnedByDefault(bool) {}
 bool Create(uint64 low,uint32 e,Map* map,uint32 p,float,float,float,float,G3D::Quat const&,int,int);
};
uint64 nextObject=10;
std::function<void()> duringSummon;
std::vector<Player*> everyone;
struct Map {
 uint32 id,instance; uint32 GetAreaId(uint32,float,float,float) { return 1; } bool failSpawn=false; std::map<ObjectGuid,std::unique_ptr<GameObject>> objects;
 uint32 GetId() const { return id; } uint32 GetInstanceId() const { return instance; }
 template<HighGuid H> uint64 GenerateLowGuid() { return ++nextObject; }
 bool AddToMap(GameObject* go);
 GameObject* GetGameObject(ObjectGuid guid) { auto it=objects.find(guid); return it==objects.end()?nullptr:it->second.get(); }
};
struct GroupReference { Player* member; GroupReference* link=nullptr;
 GroupReference* next() { return link; } Player* GetSource() { return member; } };
struct Group { GroupReference* first; GroupReference* GetFirstMember() { return first; } };
struct Player : Unit, WorldLocation {
 ObjectGuid guid; uint32 instance=0,phase=1,tier=10; Map* location=nullptr; Group* group=nullptr;
 bool alive=true,combat=false,transferring=false,teleportSuccess=true; unsigned teleports=0;
 WorldLocation destination;
 Player(uint64 id):guid{id} { player=this; }
 ObjectGuid GetGUID() const { return guid; } uint32 GetInstanceId() const { return instance; }
 uint32 GetPhaseMask() const { return phase; } bool IsAlive() const { return alive; } int GetDifficulty(bool) const { return 0; }
 bool IsInCombat() const { return combat; } bool IsBeingTeleported() const { return transferring; }
 Map* GetMap() { return location; } Group* GetGroup() { return group; }
 void* GetSession() { return nullptr; }
 bool TeleportTo(WorldLocation const& p,int=0) { if(!teleportSuccess) return false; ++teleports; destination=p; return true; }
};
struct ChatHandler { explicit ChatHandler(void*) {} void SendSysMessage(char const*) {} };
namespace Difficulty { unsigned CurrentTier(Player const* p) { return p->tier; } }
namespace World {
 constexpr unsigned SanctumPhase=@SANCTUM_PHASE@;
 bool HubPoint(std::string const& name,WorldLocation& out) {
  out=WorldLocation(530,name=="spawn"?10.f:20.f,30,40,1); return true;
 }
 bool IsInHub(Player* p) { return p->map==530 && !p->instance; }
}
struct Rift {};
bool currentLive=true;
bool Current(Player*,Rift&) { return currentLive; }
bool IsLiveInstance(uint32,uint32) { return currentLive; }
bool IsOpenZoneMap(uint32 map) { return map==751; } // dc_open_rift.cpp: a map a zone row names (751 is Kalimdor's copy)
struct Save { uint32 id=7; uint32 GetInstanceId() { return id; } } save;
struct Bind { Save* save; } bind{&save};
// destination: the copy the core would send the player to (the party leader's bind on the map), PlayerStorage TeleportTo's pick.
struct Manager { uint32 destination=9; Bind* PlayerGetBoundInstance(ObjectGuid,uint32,int) { return &bind; }
 uint32 PlayerGetDestinationInstanceId(Player*,uint32,int) { return destination; } } manager;
Manager* sInstanceSaveMgr=&manager;
void place(Player& p,Map& map,float x) {
 p.location=&map; p.map=map.id; p.instance=map.instance; p.x=x; p.y=60; p.z=70; p.o=2;
 // Production tier hook: phase 1 in rifts, the Sanctum's shared phase in the hub, the tier's own in the open world.
 p.phase=map.instance?1:(map.id==530?World::SanctumPhase:p.tier);
}
'''
# What the core asks about visibility is dc_rifts.cpp's own: the claim, the AI factory the core
# runs inside GameObject::Create, the AI and the per-seer answer. Extracted, not re-typed.
harness += r'''
std::mutex workMutex;
std::map<ObjectGuid,uint32> playerRun;
struct EntranceD { uint32 obeliskSpawnId=0; };
std::map<uint32,EntranceD> entrances;
'''
# struct Claim is in dc_rifts_shared.h, the thread_local itself in dc_rifts.cpp
claim_state = RIFTS[RIFTS.index('    struct Claim\n'):RIFTS.index('    };\n', RIFTS.index('    struct Claim\n')) + len('    };\n')] + '    thread_local Claim claiming;'
harness += claim_state + '\n'
harness += 'bool CanSeeHubObject(GameObject const* go, uint32 owningRun, ObjectGuid owner, Player const* seer)\n' + \
    definition('    bool CanSeeHubObject(', RIFTS)[len('    bool CanSeeHubObject(GameObject const* go, std::uint32_t owningRun, ObjectGuid owner, Player const* seer)'):].replace('std::uint32_t', 'uint32') + '\n'
harness += definition('class RiftHubObjectAI final', RIFTS).replace('std::uint32_t', 'uint32') + ';\n'
harness += r'''
struct HubObjectClaim { explicit HubObjectClaim(ObjectGuid onlyFor); ~HubObjectClaim(); };
'''
harness += definition('HubObjectClaim::HubObjectClaim(ObjectGuid onlyFor)', RIFTS) + '\n'
harness += definition('HubObjectClaim::~HubObjectClaim()', RIFTS) + '\n'
harness += 'struct RiftObelisk { ' + definition('GameObjectAI* GetGameObjectAI(GameObject* go) const override', RIFTS) + ' } riftObelisk;\n'
harness += r'''
enum class WorldSpawnKind : unsigned char { Creature, Vehicle, GameObject, StaticTransport, MotionTransport, Pet };
struct Position { float x,y,z,o; Position(float a,float b,float c,float d):x(a),y(b),z(c),o(d) {}
 float GetPositionX() const { return x; } float GetPositionY() const { return y; } float GetPositionZ() const { return z; } };
struct MapEntry { uint32 id; bool Instanceable() const { return id==558; } };
struct MapStore { MapEntry entry; MapEntry const* LookupEntry(uint32 id) { entry={id}; return &entry; } } sMapStore;
Map baseMap{0,0};
struct MapMgr { Map* CreateBaseMap(uint32) { return &baseMap; } } mapMgr; MapMgr* sMapMgr=&mapMgr;
unsigned LaunchTierCount() { return 10; }
namespace DC::Areas {
struct OwnPlacement { OwnPlacement(); ~OwnPlacement(); };
'''
harness += AREAS[AREAS.index('struct Rule '):AREAS.index('\n', AREAS.index('struct Rule '))] + '\n'
harness += AREAS[AREAS.index('thread_local unsigned ownPlacements'):AREAS.index('\n', AREAS.index('thread_local unsigned ownPlacements'))] + '\n'
harness += r'''
std::map<uint32,std::vector<Rule>> rules={{530,{Rule{1,"all",true}}}};
bool ready=true;
std::array<std::atomic<uint64>,6> denied{}, allowed{};
'''
harness += definition('bool IsOpen(', AREAS) + '\n'
harness += definition('OwnPlacement::OwnPlacement()', AREAS) + '\n' + definition('OwnPlacement::~OwnPlacement()', AREAS) + '\n'
harness += 'struct AreaFilter { ' + definition('    bool CanWorldObjectSpawn(', AREAS) + ' } filter;\n}\n'
harness += r'''
bool GameObject::Create(uint64 low,uint32 e,Map* map,uint32 p,float x,float y,float z,float o,G3D::Quat const&,int,int) {
 // GameObject.cpp Create asks the spawn filter before anything else.
 if (!DC::Areas::filter.CanWorldObjectSpawn(WorldSpawnKind::GameObject,e,spawnId,map->id,p,Position(x,y,z,o))) return false;
 if (map->failSpawn) return false;
 guid=ObjectGuid{low}; entry=e; phase=p; display=templateDisplay.at(e);
 log.push_back("create"); ai.reset(riftObelisk.GetGameObjectAI(this)); // the script hook inside Create
 return true;
}
bool Map::AddToMap(GameObject* go) {
 go->log.push_back("add"); go->added=true; go->phaseAtAdd=go->phase; go->displayAtAdd=go->display;
 for (Player* p : everyone)
  if (p->map==id && p->instance==instance && p->phase==go->phase && (!go->ai || go->ai->CanBeSeen(p))) go->seenBy.insert(p->guid.id);
 objects[go->guid].reset(go);
 if(duringSummon) { auto callback=std::move(duringSummon); duringSummon=nullptr; callback(); }
 return true;
}
'''
start = SOURCE.index('constexpr uint32 PORTAL_SPELL')
end = SOURCE.index('// Called with portalMutex held.', start)
harness += SOURCE[start:end]
harness += '\n' + definition('GameObject* PlaceOwned(')
for marker in ('void RemoveObjects(', 'void RemoveOwner(', 'void ReplacePortal(', 'bool FindPortal(',
               'bool CanUse(', 'bool ValidSource(', 'bool OpenPair(', 'void CompleteCast(', '    void OnLoadSpellCustomAttr(',
               '    void OnSpellCheckCast(', '    void OnSpellCast(', 'static bool PreparingPortal(', '    void ModifyExactDamage(', '    void OnDamage(',
               '    bool CanGameObjectGossipHello(', '    void OnMapUpdate(', '    void OnDestroyMap(',
               'void CloseInstance('):
    harness += '\n' + definition(marker)
harness += r'''
// One hit as the core delivers it (Unit::DealDamage): the exact hook first, then the 32-bit consumers on the saturated view; a
// view a consumer changed replaces the exact hit, one it left alone leaves it (core patch 0027's ApplyThroughView).
void Hit(Unit* attacker, Unit* victim, uint64& exact) {
 ModifyExactDamage(attacker,victim,exact,DIRECT_DAMAGE);
 uint32 const before=exact>0xFFFFFFFFull?0xFFFFFFFFu:uint32(exact); uint32 view=before;
 OnDamage(attacker,victim,view); if (view!=before) exact=view;
}
int main() {
 Map source{558,7},hub{530,0},world{0,0}; Player owner{1},member{2},stranger{3};
 GroupReference memberRef{&member}; Group group{&memberRef}; owner.group=&group; member.group=&group;
 everyone={&owner,&member,&stranger};
 place(owner,source,100); owner.combat=true;
 Spell spell{{PORTAL_SPELL},&owner}; int result=0;
 OnSpellCheckCast(&spell,true,result); assert(result==0); // Combat alone permits cast.
 SpellInfo info{PORTAL_SPELL,SPELL_ATTR0_NOT_IN_COMBAT_ONLY_PEACEFUL}; OnLoadSpellCustomAttr(&info);
 assert(!(info.Attributes&SPELL_ATTR0_NOT_IN_COMBAT_ONLY_PEACEFUL));
 assert(info.CastTimeEntry->CastTime==1500);
 // Town Portal no longer carries the core's damage abort: PortalDamage below is the only damage interrupt (a hit a shield absorbs in full no longer cancels it).
 assert(info.InterruptFlags==(SPELL_INTERRUPT_FLAG_MOVEMENT|SPELL_INTERRUPT_FLAG_INTERRUPT) && !(info.InterruptFlags&SPELL_INTERRUPT_FLAG_ABORT_ON_DMG));
 OnSpellCast(&spell,&owner,&spell.info,false);
 assert(owner.teleports==1 && owner.destination.map==530 && owner.destination.x==20);
 assert(portals.size()==1 && portals.at(owner.guid).source.x==100);
 auto old=portals.at(owner.guid); OnMapUpdate(&hub,1); old=portals.at(owner.guid);
 assert(old.hubObject && old.sourceObject);
 assert(hub.GetGameObject(old.hubObject)->phase==World::SanctumPhase && owner.tier!=World::SanctumPhase);
 assert(source.GetGameObject(old.sourceObject)->phase==1);
 // Damage interrupts without replacing the existing pair or teleporting.
 owner.cast=&spell; uint64 damage=1; Hit(&stranger,&owner,damage);
 assert(owner.interrupts==1 && owner.teleports==1 && portals.at(owner.guid).token==old.token);
 // Homing Pads: the wearer's cast goes on and takes 1 - N/100 of the damage, however many hits; a stranger or a zero hit changes nothing.
 DC::Combat::ItemPowers::bubble=0.5; owner.cast=&spell; damage=100; Hit(&stranger,&owner,damage);
 assert(owner.interrupts==1 && owner.cast==&spell && damage==50);
 damage=0; DC::Combat::ItemPowers::asked=0; Hit(&stranger,&owner,damage); assert(owner.interrupts==1 && damage==0 && !DC::Combat::ItemPowers::asked);
 spell.state=1; damage=100; Hit(&stranger,&owner,damage); assert(owner.interrupts==1 && damage==100); spell.state=0; // past preparing: untouched
 DC::Combat::ItemPowers::bubble=0.35; damage=3; Hit(&stranger,&owner,damage); assert(damage==1 && owner.cast==&spell);   // rounded, never negative
 damage=1; DC::Combat::ItemPowers::bubble=0.5; Hit(&stranger,&owner,damage); assert(damage==1);                       // a half rounds up, as lround did
 // diablocraft-86qcn: a hit past 2^32 takes the share of the exact hit, not of the saturated view (4,294,967,295 x 0.5 replaced a
 // 10,000,000,000 hit with 2,147,483,648), and a factor the table can only approximate still lands on the whole number.
 damage=10000000000ull; Hit(&stranger,&owner,damage); assert(damage==5000000000ull && owner.cast==&spell && owner.interrupts==1);
 DC::Combat::ItemPowers::bubble=0.35; damage=10000000000ull; Hit(&stranger,&owner,damage); assert(damage==3500000000ull);
 DC::Combat::ItemPowers::bubble=0.5; damage=18446744073709551615ull; Hit(&stranger,&owner,damage); assert(damage==9223372036854775808ull);
 DC::Combat::ItemPowers::bubble=0.0; damage=7; Hit(&stranger,&owner,damage); assert(damage==0 && owner.cast==&spell);   // a full bubble takes it all
 DC::Combat::ItemPowers::bubble=1.0; damage=100; Hit(&stranger,&owner,damage);      // without the item the same hit cancels the cast
 assert(owner.interrupts==2 && owner.cast==nullptr && damage==100);
 // Another caster may have an independent pair in the same instance.
 place(member,source,200); CompleteCast(&member); assert(portals.size()==2);
 place(owner,source,300); CompleteCast(&owner); auto replacement=portals.at(owner.guid);
 assert(replacement.token!=old.token && replacement.source.x==300 && portals.size()==2);
 OnMapUpdate(&source,1); OnMapUpdate(&hub,1);
 assert(source.GetGameObject(old.sourceObject)->deleted && hub.GetGameObject(old.hubObject)->deleted);
 replacement=portals.at(owner.guid);
 place(stranger,hub,10); auto* returnGo=hub.GetGameObject(replacement.hubObject);
 CanGameObjectGossipHello(&stranger,returnGo); assert(stranger.teleports==0);
 // A party member cannot use the owner's portal either: it is the caster's alone (ruling 2026-10-02).
 place(member,hub,10); CanGameObjectGossipHello(&member,returnGo);
 assert(member.teleports==1 && portals.count(owner.guid)); // member's own earlier cast moved it once
 place(owner,hub,10); owner.combat=false; save.id=8;
 CanGameObjectGossipHello(&owner,returnGo); assert(owner.teleports==2); // Wrong instance denied.
 save.id=7; CanGameObjectGossipHello(&owner,returnGo);
 assert(owner.teleports==3 && owner.destination.x==300 && portals.count(owner.guid));
 // The caster's return must leave a usable source portal for another round trip.
 OnMapUpdate(&source,1); OnMapUpdate(&hub,1);
 assert(!source.GetGameObject(replacement.sourceObject)->deleted && !returnGo->deleted);
 place(owner,source,300);
 CanGameObjectGossipHello(&owner,source.GetGameObject(replacement.sourceObject));
 assert(owner.teleports==4 && owner.destination.map==530 && owner.destination.x==20);
 place(owner,hub,20); CanGameObjectGossipHello(&owner,returnGo);
 assert(owner.teleports==5 && owner.destination.x==300);
 assert(portals.at(owner.guid).token==replacement.token);
 // A cast whose source object cannot spawn leaves the prior pair intact.
 place(member,source,400); auto memberToken=portals.at(member.guid).token;
 source.failSpawn=true; CompleteCast(&member); assert(portals.at(member.guid).token==memberToken);
 source.failSpawn=false;
 // Closing removes all remaining rift pairs, including their source objects.
 CloseInstance(7); assert(portals.empty()); OnMapUpdate(&source,1); OnMapUpdate(&hub,1);
 for(auto const& [id,go]:source.objects) assert(go->deleted);
 for(auto const& [id,go]:hub.objects) assert(go->deleted);
 // Replacement during hub spawning cannot publish a stale portal.
 place(owner,world,500); CompleteCast(&owner);
 auto token=portals.at(owner.guid).token;
 duringSummon=[&] { RemoveOwner(owner.guid,token); };
 OnMapUpdate(&hub,1); assert(portals.empty());
 for(auto const& [id,go]:hub.objects) assert(go->deleted);
 // Open-world return preserves coordinates too; no instance bind is required.
 CompleteCast(&owner); OnMapUpdate(&hub,1); auto openWorld=portals.at(owner.guid);
 // diablocraft-aggz6: map 0 is a closed open-world area (no open rule), as Stormwind is. The cast just above
 // opened its pair there; any other object there is still refused once the placement is over.
 assert(portals.size()==1 && portals.begin()->second.sourceObject);
 { GameObject probe; auto refused=DC::Areas::denied[2].load();
   assert(!probe.Create(1,SOURCE_OBJECT,&world,1,500,60,70,2,G3D::Quat(0,0,0,1),100,GO_STATE_READY));
   assert(DC::Areas::denied[2].load()==refused+1); }
 place(owner,hub,10); CanGameObjectGossipHello(&owner,hub.GetGameObject(openWorld.hubObject));
 assert(owner.destination.map==0 && owner.destination.x==500);
 // A stale token must not remove a newer replacement.
 place(owner,source,600); CompleteCast(&owner); token=portals.at(owner.guid).token;
 CompleteCast(&owner); RemoveOwner(owner.guid,token); assert(portals.count(owner.guid));
 OnDestroyMap(&source); assert(portals.empty());
 // ---- Town Portal is private (diablocraft-town-portal-private): who is SHOWN each half, from the
 // first create packet, and who may USE it. Three characters stand together in the source map and
 // again in the hub; the owner and a party member both stand in the same group.
 portals.clear(); removals.clear(); source.objects.clear(); hub.objects.clear();
 owner.tier=10; member.tier=5; stranger.tier=3; // three tiers share the hub phase
 place(owner,source,50); place(member,source,51); place(stranger,source,52);
 CompleteCast(&owner);
 auto mine=portals.at(owner.guid); GameObject* srcGo=source.GetGameObject(mine.sourceObject);
 assert(srcGo && srcGo->seenBy==std::set<uint64>{owner.guid.id}); // nobody else is told it exists
 assert(srcGo->phaseAtAdd==1);                                    // the phase is in the create packet
 assert(srcGo->displayAtAdd==templateDisplay.at(SOURCE_OBJECT));  // and so is the model
 assert((srcGo->log==std::vector<std::string>{"create","add"}));  // nothing is changed after the map add
 place(owner,hub,10); place(member,hub,11); place(stranger,hub,12);
 OnMapUpdate(&hub,1);
 mine=portals.at(owner.guid); GameObject* hubGo=hub.GetGameObject(mine.hubObject);
 assert(hubGo && hubGo->seenBy==std::set<uint64>{owner.guid.id});
 assert(hubGo->phaseAtAdd==World::SanctumPhase && hubGo->displayAtAdd==templateDisplay.at(HUB_OBJECT));
 assert((hubGo->log==std::vector<std::string>{"create","add"}));
 // A second player's portal in the same spot is theirs alone, and does not show up for the first.
 place(stranger,source,53); CompleteCast(&stranger);
 place(owner,hub,10); place(stranger,hub,12); OnMapUpdate(&hub,1);
 auto theirs=portals.at(stranger.guid); GameObject* theirHub=hub.GetGameObject(theirs.hubObject);
 assert(theirHub && theirHub->seenBy==std::set<uint64>{stranger.guid.id});
 assert(hubGo->seenBy==std::set<uint64>{owner.guid.id});
 // Using: only the owner, even though a modified client can click an object it cannot see.
 place(owner,hub,10); auto before=owner.teleports; CanGameObjectGossipHello(&owner,theirHub);
 assert(owner.teleports==before);                                  // the first cannot use the second's
 place(stranger,hub,12); before=stranger.teleports; CanGameObjectGossipHello(&stranger,hubGo);
 assert(stranger.teleports==before);                               // nor the second the first's
 place(member,hub,11); before=member.teleports; CanGameObjectGossipHello(&member,hubGo);
 assert(member.teleports==before);                                 // a party member is not the owner
 place(owner,hub,10); before=owner.teleports; CanGameObjectGossipHello(&owner,hubGo);
 assert(owner.teleports==before+1 && owner.destination.x==50);     // the owner uses theirs
 // Same on the rift side: the portal back to the hub.
 place(stranger,source,53); before=stranger.teleports; CanGameObjectGossipHello(&stranger,srcGo);
 assert(stranger.teleports==before);
 place(member,source,51); before=member.teleports; CanGameObjectGossipHello(&member,srcGo);
 assert(member.teleports==before);
 place(owner,source,50); before=owner.teleports; CanGameObjectGossipHello(&owner,srcGo);
 assert(owner.teleports==before+1 && owner.destination.map==530);
 // A claim never outlives the summon that made it: the next object created without one is public.
 assert(!claiming.Active());
 for (uint32 tier : {1u,10u}) {
  owner.tier=tier; place(owner,source,700); CompleteCast(&owner); OnMapUpdate(&hub,1);
  auto pair=portals.at(owner.guid);
  assert(source.GetGameObject(pair.sourceObject)->phase==1);
  assert(hub.GetGameObject(pair.hubObject)->phase==World::SanctumPhase);
  assert(owner.destination.x==20); // town_portal, not login spawn
  place(owner,hub,20); auto transfers=owner.teleports;
  CanGameObjectGossipHello(&owner,hub.GetGameObject(pair.hubObject));
  assert(owner.teleports==transfers+1 && owner.destination.x==700);
 }
 // diablocraft-revive-choices-server: OpenPair is the cast's pair without the cast's move. Revive in town opens
 // it where a character fell, then moves it itself.
 portals.clear(); removals.clear(); source.objects.clear(); hub.objects.clear(); owner.tier=10;
 place(owner,source,800); auto moved=owner.teleports;
 assert(OpenPair(&owner) && owner.teleports==moved);                          // nobody is moved
 assert(portals.size()==1 && portals.at(owner.guid).source.x==800 && portals.at(owner.guid).instance==7);
 OnMapUpdate(&hub,1); assert(hub.GetGameObject(portals.at(owner.guid).hubObject));  // the hub half follows
 auto firstToken=portals.at(owner.guid).token;
 place(owner,source,810); assert(OpenPair(&owner) && portals.at(owner.guid).token!=firstToken && portals.size()==1);
 auto keptToken=portals.at(owner.guid).token;                                  // a new pair replaces the old
 owner.alive=false; assert(!OpenPair(&owner) && portals.at(owner.guid).token==keptToken);  // the dead open none
 owner.alive=true; place(owner,hub,10); assert(!OpenPair(&owner));              // nor in the hub
 place(owner,source,820); source.failSpawn=true;
 assert(!OpenPair(&owner) && portals.at(owner.guid).token==keptToken); source.failSpawn=false;  // old pair kept
 assert(owner.teleports==moved);
 // diablocraft-q8h1w: the open-zone copy (map 751, where bounty travel lands) is the open world for Town Portal. It is an
 // instance and not a rift, so the cast opens there, and the way back goes to that copy while the core would still send
 // the player to it. Every other instance that is not a live rift keeps the refusal; a rift keeps its own rules.
 portals.clear(); removals.clear(); source.objects.clear(); hub.objects.clear(); currentLive=false;
 Map copy{751,9}, dungeon{558,12}; owner.combat=false;
 place(owner,dungeon,50); result=0; OnSpellCheckCast(&spell,true,result);
 assert(result==SPELL_FAILED_NOT_HERE && !OpenPair(&owner));                     // a plain instance: refused
 place(owner,copy,900); result=0; OnSpellCheckCast(&spell,true,result); assert(result==0);
 before=owner.teleports; CompleteCast(&owner); OnMapUpdate(&hub,1);
 assert(owner.teleports==before+1 && owner.destination.map==530 && owner.destination.x==20);
 auto trip=portals.at(owner.guid); assert(trip.instance==9 && trip.source.x==900 && trip.hubObject);
 assert(copy.GetGameObject(trip.sourceObject)->phase==owner.phase);
 place(owner,hub,10); manager.destination=11; before=owner.teleports;
 CanGameObjectGossipHello(&owner,hub.GetGameObject(trip.hubObject));
 assert(owner.teleports==before && portals.count(owner.guid));                   // the party's copy is another one now
 manager.destination=9; CanGameObjectGossipHello(&owner,hub.GetGameObject(trip.hubObject));
 assert(owner.teleports==before+1 && owner.destination.map==751 && owner.destination.x==900);  // back to the same copy
 place(owner,copy,900); CanGameObjectGossipHello(&owner,copy.GetGameObject(trip.sourceObject));
 assert(owner.teleports==before+2 && owner.destination.map==530);               // and out again: a round trip keeps it
 OnDestroyMap(&copy); assert(portals.empty());                                   // the copy gone, the pair goes
 // A rift on the copy map is still a rift: its pair dies with the run, whatever the core's pick says.
 currentLive=true; place(owner,copy,950); CompleteCast(&owner); OnMapUpdate(&hub,1); trip=portals.at(owner.guid);
 currentLive=false; place(owner,hub,10); before=owner.teleports;
 CanGameObjectGossipHello(&owner,hub.GetGameObject(trip.hubObject));
 assert(owner.teleports==before && !portals.count(owner.guid));                  // "That rift has closed."
}
'''
import csv
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import host_cmake
with (ROOT / 'mod-diablocraft/data/tunables/rifts.csv').open(newline='', encoding='utf-8') as handle:
    _row = next(row for row in csv.DictReader(handle) if row['name'] == 'town_portal_cast_ms')
harness = harness.replace('@CAST_MS@', str(float(_row['value'] or _row['d3_value']))).replace('@SANCTUM_PHASE@', SANCTUM_PHASE)
env = host_cmake.environment()
with tempfile.TemporaryDirectory(prefix='dc-town-portal-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(harness, encoding='utf-8')
    (folder / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject(portal_tests LANGUAGES CXX)\n'
        'add_executable(portal_tests test.cpp)\ntarget_compile_features(portal_tests PRIVATE cxx_std_17)\n'
        'target_compile_options(portal_tests PRIVATE ' + host_cmake.undebug() + ')\n', encoding='utf-8')
    configure, build, binary = host_cmake.commands(folder, folder / 'build', 'portal_tests')
    for command in (configure, build, [binary]):
        subprocess.run(command, env=env, check=True)
print('PASS: combat cast/damage interruption, auto-arrival, saved return position, replacement, per-caster pairs, party/instance guards, closure and stale-map work, the open-zone copy (cast, return to the same copy, refused once it changed)')
