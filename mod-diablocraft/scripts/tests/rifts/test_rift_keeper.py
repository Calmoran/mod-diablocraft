"""Compile production Rift Keeper closure callbacks against focused core doubles."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]
# DC_RIFT_KEEPER_SOURCE lets test_class_parity.py run this harness on a mutated
# copy of dc_rifts.cpp, to prove the class gate assertions can fail. The open and
# close calls live in dc_rift_open.cpp, the closure drain in dc_rift_scripts.cpp.
SOURCE = Path(os.environ.get('DC_RIFT_KEEPER_SOURCE',
                             ROOT / 'mod-diablocraft/src/rifts/dc_rifts.cpp')).read_text(encoding='utf-8') + ''.join(
    (ROOT / 'mod-diablocraft/src/rifts' / name).read_text(encoding='utf-8') for name in ('dc_rift_open.cpp', 'dc_rift_scripts.cpp'))


def definition(marker: str) -> str:
    start = SOURCE.index(marker)
    opening = SOURCE.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[start:end].replace(' override', '')


HARNESS = r'''
#include <cassert>
#include <functional>
#include <cstdint>
#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#include <mutex>
#include <set>
#include <random>
#include "FLOORS_HEADER"
using DC::Rifts::LiveRuns;
using DC::Rifts::Floor;
#define LOG_INFO(...) ((void)0)
unsigned refusalLogs=0;
#define LOG_WARN(...) (++refusalLogs)
using uint32 = std::uint32_t;
constexpr unsigned CLASS_WARRIOR=1, CLASS_MAGE=8, CLASS_MONK=12;
struct ObjectGuid {
 unsigned value;
 unsigned GetRawValue() const { return value; }
 bool operator==(ObjectGuid const& b) const { return value==b.value; }
 bool operator!=(ObjectGuid const& b) const { return !(*this==b); }
};
struct WorldLocation {};
struct Map;
struct Group;
struct Player {
 ObjectGuid guid; bool hub=true, combat=false; unsigned teleports=0; unsigned cls=CLASS_WARRIOR;
 ObjectGuid GetGUID() const { return guid; }
 unsigned getClass() const { return cls; }
 bool IsInCombat() const { return combat; }
 void* GetSession() { return nullptr; }
 void TeleportTo(WorldLocation const&) { ++teleports; }
 void TeleportTo(unsigned,float,float,float,float) { ++teleports; hub=false; }
 Group* GetGroup() { return nullptr; }
 Map* GetMap() { return nullptr; }
 bool IsInWorld() { return true; }
 char const* GetName() { return "test"; }
};
struct GroupReference {
 GroupReference* next() { return nullptr; }
 Player* GetSource() { return nullptr; }
};
struct Group {
 ObjectGuid GetLeaderGUID() { return {1}; }
 GroupReference* GetFirstMember() { return nullptr; }
};
struct ChatHandler { explicit ChatHandler(void*) {} void SendSysMessage(char const*) {} template<class... T> void PSendSysMessage(char const*,T...) {} };
namespace DC::World {
 bool IsInHub(Player const* p) { return p && p->hub; }
 bool HubLocation(WorldLocation&) { return true; }
}
namespace DC::Difficulty { unsigned CurrentTier(Player*) { return 1; } }
// The class gate is compiled real (PlayableClass below); only the class map it
// reads is a double: class_map.csv's two rows, Warrior and Mage. A Monk (WoW
// id 12) has no row, which is the "no data row" refusal.
namespace DC::Classes {
 std::map<unsigned,unsigned> classMap{{CLASS_WARRIOR,1},{CLASS_MAGE,2}};
 bool Playable(Player const* p) { return p && classMap.count(p->getClass()); }
}
struct Rift {
 unsigned instanceId=7,mapId=558,leaderGuid=1; std::string state="open";
 std::uint64_t id=0; unsigned dungeonId=0,tier=0,players=0,required=0;
 // Phase A (2026-09-17) additions, mirrored so the real OpenRun compiles here.
 unsigned progress=0,requiredUnits=0,questId=0; std::string mode="nr";
 // Greater Rift part 2 (diablocraft-0uyw): the level of the run and its shared deadline.
 unsigned grRank=0; long long deadline=0;
 // Rift floors (F1): the number of the floor a copy is seen from, and the floor the Guardian is on.
 unsigned floor=1; unsigned guardianInstance=0;
};
std::mutex riftMutex,workMutex;
// The production book (dc_rift_floors.h). live[instance] reads the run's own row from any of its floors;
// add() gives a run the id 1000 + its instance unless the creation hook already numbered it.
struct Book : LiveRuns<Rift> {
 Rift& operator[](unsigned instance) { return *FindByInstance(instance, 0); }
 Rift& add(Rift r) { if (!r.id) r.id = 1000 + r.instanceId; return Start(r); }
};
Book live;
std::vector<Rift> closingRifts;
constexpr uint32 RIFT_CLOSE_MS=30000;
// The close delay, units per kill and party cap became tunables after this
// harness was last run (it failed to compile at 2cbe671); these doubles hand
// the real code the values the assertions below were written against.
uint32 RiftCloseMs() { return RIFT_CLOSE_MS; }
namespace DC::Tunables { double Get(char const*, std::string const& key) { return key=="close_announce_first_seconds" ? 10 : 5; } }
struct PendingClose { Rift rift; uint32 started; uint32 announced=31; };
std::unordered_map<std::uint64_t,PendingClose> pendingCloses; // by run id
uint32 clockMs=1000;
uint32 getMSTime() { return clockMs; }
uint32 getMSTimeDiff(uint32 a,uint32 b) { return b-a; }
std::unordered_map<unsigned,std::vector<ObjectGuid>> riftMembers;
std::set<unsigned> resetWhenEmpty;
unsigned persisted=0,closedPortals=0;
void Persist(Rift const&) { ++persisted; }
void PersistNow(Rift const&) { ++persisted; }
void ClosePortals(std::uint64_t) { ++closedPortals; }
std::vector<std::string> announced;
void Announce(Rift const&, std::string const& text) { announced.push_back(text); }
// Phase A (2026-09-17) gave the closure path three more collaborators. The
// harness could not see them go stale because its Windows-only toolchain had
// stopped running it; these are counted, not exercised, exactly like the three
// above, so QueueClose and Close still compile against real code here.
unsigned removedQuests=0,teleported=0;
void RemoveRunQuests(Rift const&) { ++removedQuests; }
// Part 11 (Urshi): Close() asks whether a member still has tries; none does here (her own test is test_urshi.py)
std::string urshiHolds;
std::string UrshiBlocksClose(std::uint64_t run) { return run == 1007 ? urshiHolds : std::string(); }
// Runs the move, as the real one does after its dead-player guard - the
// closure evacuation is only observable through it.
void ForcedTeleport(Player* player, std::function<void(Player*)> const& move) { ++teleported; move(player); }
struct Save { unsigned instance; unsigned GetInstanceId() const { return instance; } };
using InstanceSave = Save;
struct Bind { Save* save; };
struct Manager {
 Save oldSave{7},newSave{8}; std::map<unsigned,Bind> binds{{1,{&oldSave}},{2,{&oldSave}},{3,{&newSave}}};
 Bind* PlayerGetBoundInstance(ObjectGuid guid,unsigned,int) {
  auto f=binds.find(guid.value); return f==binds.end()?nullptr:&f->second;
 }
 void PlayerUnbindInstance(ObjectGuid guid,unsigned,int,bool) { binds.erase(guid.value); }
 unsigned unbindCalls=0;
 void PlayerUnbindInstance(ObjectGuid guid,unsigned map,int diff,bool unload,Player*) {
  ++unbindCalls; PlayerUnbindInstance(guid,map,diff,unload);
 }
 Save* GetInstanceSave(unsigned) { return &newSave; }
 void PlayerBindToInstance(ObjectGuid guid,Save* save,bool,Player*) { binds[guid.value]={save}; }
} manager;
Manager* sInstanceSaveMgr=&manager;
constexpr int DUNGEON_DIFFICULTY_NORMAL=0, INSTANCE_RESET_ALL=0;
struct Map {
 unsigned instance=7,map=558,resets=0; std::vector<Player*> players;
 unsigned GetInstanceId() const { return instance; }
 unsigned GetId() const { return map; }
 bool HavePlayers() const { return !players.empty(); }
 Map* ToInstanceMap() { return this; }
 void Reset(int) { assert(!HavePlayers()); ++resets; }
 template<class F> void DoForAllPlayers(F f) { for(auto* p:players) f(p); }
};
struct Dungeon {
 unsigned mapId=558,dungeonId=1;
 float x=0,y=0,z=0,o=0; std::string name="test dungeon";
};
// Phase A moved the body of Open into OpenRun, which the extraction list now
// pulls in real. These are the collaborators it gained.
struct Reservation { Dungeon dungeon; unsigned questId=0; uint32 made=0; };
struct BarQuest { unsigned id=0, units=0; };
BarQuest nephalemQuest, greaterQuest;   // monster spawning S3: one quest per mode
// Greater Rift part 2: OpenRun's Greater branch reaches these.
struct GreaterStart { unsigned level=0; std::vector<Player*> roster; };
bool OpenRun(Player*, Reservation const*, Rift*, std::string&, GreaterStart const* = nullptr); // the default lives in dc_rifts_internal.h
struct Quest { uint32 GetTimeAllowed() const { return 900; } };
struct ObjectMgrDouble { Quest quest; Quest const* GetQuestTemplate(unsigned) { return &quest; } } objectMgr;
ObjectMgrDouble* sObjectMgr=&objectMgr;
namespace GameTime { struct Secs { long long count() const { return 5000; } }; Secs GetGameTime() { return {}; } }
unsigned deadlineWrites=0, grQuests=0;
struct Db { template<class... T> void DirectExecute(char const*, T...) { ++deadlineWrites; } } CharacterDatabase;
void GiveRunQuest(Rift const&, Player*, char const*) { ++grQuests; }
unsigned PartyCap() { return 4; }
unsigned enrolled=0,sharedQuests=0,entrances=0;
bool PartyRun(Player*,Rift&) { return false; }
void EnrollMember(Rift const&, ObjectGuid) { ++enrolled; }
void OpenEntrance(Rift const&, Player*, Dungeon const&) { ++entrances; }
void ShareRunQuest(Rift const&, Player*) { ++sharedQuests; }
std::mutex dataMutex;
bool dataReady=true;
std::vector<Dungeon> pool{Dungeon{}};
std::mt19937& Engine() { static std::mt19937 e{1}; return e; }
bool Current(Player*,Rift&) { return false; }
Rift* opening=nullptr;
struct MapManager {
 unsigned creates=0; Map map;
 Map* CreateMap(unsigned,Player*) {
  ++creates; map.instance=100+creates;
  opening->id=creates; opening->instanceId=map.instance;
  live.Start(*opening); // Production creation hook publishes before Open returns.
  manager.newSave.instance=map.instance;
  return &map;
 }
} mapManager;
MapManager* sMapMgr=&mapManager;
'''
HARNESS += '\n'.join(definition(m) for m in ('bool PlayableClass(', 'bool OwnedRift(', 'void QueueClose(', 'bool OpenRun(', 'bool Open(Player*', 'bool Close(Player*', 'void AdvanceClosure(', 'void DrainClosures('))
HARNESS += r'''
int main() {
 Player owner{{1}}, member{{2}}, anotherRun{{3}};
 live.add(Rift{}); live.add(Rift{8,558,3,"open"});
 riftMembers[7]={{1},{2},{3}};
 std::string error;
 owner.hub=false; assert(!Close(&owner,error));
 owner.hub=true; owner.combat=true; assert(!Close(&owner,error));
 owner.combat=false; assert(!Close(&member,error));
 assert(persisted==0 && closingRifts.empty());
 // Part 11: a member still holding Urshi tries keeps the rift open; the refusal names who, and no countdown starts
 urshiHolds="Your rift cannot be closed while Anna still has upgrade attempts left with Urshi.";
 assert(!Close(&owner,error) && error==urshiHolds && pendingCloses.empty());
 urshiHolds.clear();
 assert(Close(&owner,error));
 assert(live[7].state=="open" && live[8].state=="open");
 assert(persisted==0 && closedPortals==0 && pendingCloses.size()==1);
 clockMs+=10000;
 assert(!Close(&owner,error)); assert(pendingCloses[1007].started==1000);
 Map wrong; wrong.instance=8; DrainClosures(&wrong); assert(pendingCloses.size()==1);
 Map map; map.players={&member};
 clockMs=30999; DrainClosures(&map);
 assert(member.teleports==0 && live[7].state=="open" && closedPortals==0);
 clockMs=31000; DrainClosures(&map);
 assert(live[7].state=="closed" && closedPortals==1 && persisted==1);
 assert(member.teleports==1 && owner.teleports==0 && anotherRun.teleports==0);
 assert(!manager.binds.count(1) && !manager.binds.count(2) && manager.binds.count(3));
 assert(closingRifts.empty() && !riftMembers.count(7) && map.resets==0);
 DrainClosures(&map); assert(map.resets==0 && member.teleports==1);
 map.players.clear(); DrainClosures(&map); assert(map.resets==1);
 DrainClosures(&map); assert(map.resets==1); // Reset timer is never restarted each tick.

 // Millisecond clock wrap must not close early or stall closure.
 live.add(Rift{9,558,1,"open"});
 clockMs=0xfffffff0u; assert(Close(&owner,error));
 Map wrap; wrap.instance=9;
 clockMs+=29999; DrainClosures(&wrap); assert(live[9].state=="open");
 ++clockMs; DrainClosures(&wrap); assert(live[9].state=="closed");

 // Opening publishes the new run during CreateMap. It must not reject itself.
 live.Clear(); riftMembers.clear(); manager.binds.clear();
 // Nobody is auto-teleported into a Nephalem Rift (ruling 2026-09-17,
 // dc_rifts.cpp OpenRun): the opener walks through the obelisk portal.
 assert(Open(&owner,error));
 assert(mapManager.creates==1 && owner.teleports==0 && live[101].state=="open");
 owner.hub=true; // Town portal back to the hub.
 auto unbinds=manager.unbindCalls;
 assert(!Open(&owner,error));
 assert(mapManager.creates==1 && manager.unbindCalls==unbinds && owner.teleports==0);
 assert(Close(&owner,error));
 assert(!Open(&owner,error)); // A countdown still owns a live run.
 clockMs+=30000; DrainClosures(&mapManager.map);
 assert(Open(&owner,error)); // After expiry, no need to wait for old map unload.
 assert(mapManager.creates==2 && owner.teleports==0 && live[102].state=="open");

 // diablocraft-class-parity item 1: every class with a class-map row opens a
 // rift; a class without one is refused before any side effect, logged once.
 live.Clear(); riftMembers.clear(); manager.binds.clear();
 Player wizard{{4}}; wizard.cls=CLASS_MAGE;
 auto creates=mapManager.creates;
 assert(Open(&wizard,error));
 assert(mapManager.creates==creates+1 && live.FloorAt(mapManager.map.instance,0));
 Player monk{{5}}; monk.cls=CLASS_MONK;
 creates=mapManager.creates; auto persistedBefore=persisted;
 assert(!Open(&monk,error) && error=="Your class cannot open a rift yet.");
 assert(mapManager.creates==creates && monk.teleports==0 && persisted==persistedBefore);
 assert(refusalLogs==1);
 assert(!Open(&monk,error) && refusalLogs==1); // Named once, refused every time.

 // Greater Rift part 2: the run opens for the roster the ready check closed, every member
 // holds the quest and goes in together, the deadline is the quest's own 15:00 from now,
 // and no obelisk portal is made (nobody is admitted after the start).
 live.Clear(); riftMembers.clear(); manager.binds.clear();
 greaterQuest={555,65000};
 Player g1{{11}}, g2{{12}}, g3{{13}};
 GreaterStart start; start.level=7; start.roster={&g1,&g2,&g3};
 auto portals=entrances; auto writes=deadlineWrites; grQuests=0;
 Rift made;
 assert(OpenRun(&g1,nullptr,&made,error,&start));
 assert(made.mode=="gr" && made.grRank==7 && made.questId==555 && made.players==3);
 assert(made.requiredUnits==65000 && made.required==0);   // S3: the bar is the quest's own count, no kill baseline
 assert(made.deadline==5000+900);
 assert(live[made.instanceId].deadline==5000+900 && live[made.instanceId].mode=="gr");
 assert(deadlineWrites==writes+1);
 assert(grQuests==3 && g1.teleports==1 && g2.teleports==1 && g3.teleports==1);
 assert(entrances==portals);
 assert(manager.binds.count(11) && manager.binds.count(12) && manager.binds.count(13));
 // and a Nephalem Rift is still the other thing: no quest pushed to the party here, nobody moved
 live.Clear(); riftMembers.clear(); manager.binds.clear();
 Player n1{{14}}; grQuests=0; auto movedBefore=g1.teleports;
 assert(OpenRun(&n1,nullptr,&made,error) && made.mode=="nr" && made.deadline==0 && made.grRank==0);
 assert(grQuests==0 && n1.teleports==0 && entrances==portals+1 && g1.teleports==movedBefore);
 // a dungeon with no Greater variant is a refusal, not a run with no clock
 live.Clear(); riftMembers.clear(); manager.binds.clear(); greaterQuest={};
 creates=mapManager.creates; g1.hub=true; // the teleport above took them out of the hub
 assert(!OpenRun(&g1,nullptr,&made,error,&start) && error.find("no Greater Rift quest")!=std::string::npos);
 assert(mapManager.creates==creates);

 // Rift floors (F1): a run that holds two floors. The Keeper's countdown is the run's, so either floor's update advances
 // it and calls it out once for the whole run; the close queues one closure per floor, and each floor's own map update
 // sends its players home. Closing the run closes both.
 live.Clear(); riftMembers.clear(); manager.binds.clear(); closingRifts.clear(); pendingCloses.clear();
 closedPortals=0; persisted=0; announced.clear(); removedQuests=0;
 live.add(Rift{20,558,1,"open"});                                  // run 1020: floor 1 is instance 20 on map 558
 assert(live.AddFloor(1020,21,559,0)==2);                          // floor 2: instance 21 on map 559
 Player p1{{31}}, p2{{32}};
 Map floorOne; floorOne.instance=20; floorOne.map=558; floorOne.players={&p1};
 Map floorTwo; floorTwo.instance=21; floorTwo.map=559; floorTwo.players={&p2};
 owner.hub=true; owner.combat=false; clockMs=5000;
 assert(Close(&owner,error) && pendingCloses.size()==1 && pendingCloses.count(1020));
 clockMs=5000+20000;                                               // 10 s left: the first call-out, from the floor that updates first
 DrainClosures(&floorTwo); DrainClosures(&floorOne);
 assert(announced.size()==1 && announced[0]=="Rift closes in 10 seconds.");   // once for the run, not once per floor
 clockMs=5000+30000;                                               // the end: the SECOND floor's update is the one that closes the run
 DrainClosures(&floorTwo);
 assert(live[20].state=="closed" && closedPortals==1 && removedQuests==1 && persisted==1 && pendingCloses.empty());
 assert(closingRifts.size()==1 && closingRifts[0].instanceId==20 && closingRifts[0].floor==1);   // floor 2's own entry was taken by its drain
 assert(p2.teleports==1 && p1.teleports==0);                       // each floor sends home only its own players
 DrainClosures(&floorOne);
 assert(p1.teleports==1 && p2.teleports==1 && closingRifts.empty());
 DrainClosures(&floorOne); DrainClosures(&floorTwo);
 assert(closedPortals==1 && p1.teleports==1 && p2.teleports==1);    // nothing closes twice
 floorOne.players.clear(); floorTwo.players.clear();
 DrainClosures(&floorOne); DrainClosures(&floorTwo);
 assert(floorOne.resets==1 && floorTwo.resets==1);                 // and each floor resets itself once it is empty
}
'''

# Portable toolchain resolution (2026-09-17). This used to hardcode
# C:/Program Files/CMake/bin/cmake.exe and the Visual Studio generator, which
# stopped working the day the project moved to Linux and left this harness
# silently dead. cmake now comes from PATH, the generator is whatever cmake
# picks by default, and the assert-keeping flag is chosen per compiler: MSVC
# spells it /UNDEBUG, everyone else -UNDEBUG.
def _toolchain():
    found = shutil.which("cmake")
    if not found:
        raise SystemExit("cmake is not on PATH; this harness compiles a small C++ program")
    windows = os.name == "nt"
    generator = ["-G", "Visual Studio 17 2022", "-A", "x64"] if windows else []
    buildargs = ["--config", "Release", "--", "-m:1"] if windows else []
    undebug = "/UNDEBUG" if windows else "-UNDEBUG"
    return found, generator, buildargs, undebug, windows


def _binary(folder, name, windows):
    return str(folder / "build" / ("Release/" + name + ".exe" if windows else name))

env = {key.upper(): value for key, value in os.environ.items()}
cmake, _gen, _buildargs, _undebug, _win = _toolchain()
# Scratch lives under build/_agent-scratch/, never /tmp (CLAUDE.md).
SCRATCH = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
SCRATCH.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='dc-rift-keeper-', dir=SCRATCH) as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(HARNESS.replace('FLOORS_HEADER', (ROOT / 'mod-diablocraft/src/rifts/dc_rift_floors.h').as_posix()), encoding='utf-8')
    (folder / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject(rift_keeper_tests LANGUAGES CXX)\n'
        'add_executable(rift_keeper_tests test.cpp)\ntarget_compile_features(rift_keeper_tests PRIVATE cxx_std_17)\n'
        'target_compile_options(rift_keeper_tests PRIVATE ' + _undebug + ')\n', encoding='utf-8')
    subprocess.run([cmake, '-S', directory, '-B', str(folder / 'build'), ] + _gen, env=env, check=True)
    subprocess.run([cmake, '--build', str(folder / 'build'), ] + _buildargs, env=env, check=True)
    harness_env.run([_binary(folder, "rift_keeper_tests", _win)], env=env, check=True)
print('PASS: open for every mapped class (Barbarian, Wizard), unmapped class refused once-logged, refusal without side effects, 30-second close/reopen, duplicate deadline, clock wrap; closure guards, map isolation, member return, newer binds, one-time reset')
